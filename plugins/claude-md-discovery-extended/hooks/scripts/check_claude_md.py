#!/usr/bin/env python3
"""Discover instruction files (CLAUDE.md / AGENTS.md) outside the project tree.

Claude Code PostToolUse hook that reads JSON hook input from stdin.
Outputs discovery messages to stderr and exits 2 to feed them back
to Claude.

Suppression is content-aware: a candidate file whose hash matches any
instruction content already known this session (ancestors loaded at
startup, files loaded on demand inside the project, files previously
flagged or read, or byte-identical copies found inside the project tree)
is never flagged. The same ledger powers change detection: when a file
whose content was loaded earlier changes on disk, the model gets one
nudge to re-read it.
"""

import json
import os
import shlex
import sys
import traceback

from claude_md_lib import (
    KIND_CONTEXT,
    KIND_EQUIV,
    KIND_FLAGGED,
    Ledger,
    config_dir,
    hash_file,
    ignored_prefixes,
    is_ignored,
    log_event,
    memory_basenames,
    seed_session,
)

BASH_READ_COMMANDS = {"cat", "bat"}


def extract_structured_path(tool_name: str, tool_input: dict) -> str | None:
    """Extract target path from tools with structured path fields.

    Args:
        tool_name (str): Name of the tool (e.g. `Read`, `Edit`, `Glob`).
        tool_input (dict): The tool's input payload.

    Returns:
        str | None: The file path from the tool input, or `None` if the
                    tool is not recognized or the field is missing.
    """
    if tool_name in ("Read", "Edit", "Write"):
        return tool_input.get("file_path") or None
    if tool_name in ("Glob", "Grep"):
        return tool_input.get("path") or None
    return None


def extract_paths_from_bash(command: str) -> list[str]:
    """Extract candidate file paths from a bash command string.

    Uses a pipeline of extraction strategies. Add new `_extract_*`
    functions and append their results to `candidates` to expand
    coverage without rewriting existing logic.

    Args:
        command (str): The raw bash command string to parse.

    Returns:
        list[str]: Absolute paths found in the command tokens.
    """
    candidates: list[str] = []
    candidates.extend(_extract_token_paths(command))
    return candidates


def _extract_token_paths(command: str) -> list[str]:
    """Find absolute paths appearing as command tokens via shlex.

    Args:
        command (str): The raw bash command string to parse.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []

    paths: list[str] = []
    for token in tokens:
        if token.startswith("/"):
            paths.append(token)
        elif token.startswith("~"):
            paths.append(os.path.expanduser(token))
    return paths


def resolve_target_path(candidates: list[str]) -> str | None:
    """Return the first candidate whose path (or parent dir) exists on disk.

    Args:
        candidates (list[str]): Absolute paths to check for existence.

    Returns:
        str | None: The first path that exists or whose parent directory
                    exists, or `None` if no candidate qualifies.
    """
    for path in candidates:
        if os.path.exists(path):
            return path

    # Fallback: accept paths whose parent exists (globs, new files, etc.)
    for path in candidates:
        parent = os.path.dirname(path)
        if parent and os.path.isdir(parent):
            return path

    return None


def get_target_directory(tool_name: str, tool_input: dict) -> str | None:
    """Determine the target directory for a tool invocation.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): The tool's input payload.

    Returns:
        str | None: The directory containing the target path, or `None`
                    if no valid path can be determined.
    """
    target = extract_structured_path(tool_name, tool_input)

    if target is None and tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            return None
        candidates = extract_paths_from_bash(command)
        target = resolve_target_path(candidates)

    if not target:
        return None

    if os.path.isdir(target):
        return target
    return os.path.dirname(target)


def _kind_for(path: str, cwd: str) -> str:
    """Return the ledger kind for content the model just saw at `path`.

    Inside the project tree Claude Code's own on-demand loading carries
    the content (survives compaction); outside, only the transcript does.

    Args:
        path (str): Memory-file path.
        cwd (str): Canonicalized project working directory.
    """
    if path == cwd or path.startswith(cwd + "/"):
        return KIND_CONTEXT
    return KIND_FLAGGED


def mark_direct_access(
    tool_name: str,
    tool_input: dict,
    cwd: str,
    ledger: Ledger,
) -> None:
    """Record memory files whose content the model just saw or wrote.

    A `Read`, `Write`, or `Edit` targeting a CLAUDE.md/AGENTS.md — or a
    Bash `cat` of one — puts its content in the transcript, so flagging
    it afterwards would nag the model to read what it already read. A
    partial `Read` (offset/limit) does not count.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): The tool's input payload.
        cwd (str): Canonicalized project working directory.
        ledger (Ledger): The session ledger.
    """
    names = memory_basenames()
    targets: list[str] = []

    if tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path") or ""
        if tool_name == "Read" and (
            tool_input.get("offset") or tool_input.get("limit")
        ):
            path = ""
        if path and os.path.basename(path) in names:
            targets.append(path)
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        try:
            tokens = set(shlex.split(command))
        except ValueError:
            tokens = set()
        if tokens & BASH_READ_COMMANDS:
            targets.extend(
                p for p in extract_paths_from_bash(command)
                if os.path.basename(p) in names
            )

    for path in targets:
        path = os.path.realpath(path)
        h = hash_file(path)
        if h:
            ledger.record(path, h, _kind_for(path, cwd))


def refresh_ancestors(
    ledger: Ledger,
    cwd: str,
    ignored: tuple[str, ...],
    new: list[str],
    changed: list[str],
) -> None:
    """Re-check ancestor CLAUDE.md files and the global user memory.

    Claude Code loads these once at startup and never reloads them, so a
    mid-session edit goes stale silently. A hash mismatch against the
    ledger produces one re-read nudge; an ancestor CLAUDE.md created
    after the session started (which the startup walk never saw) is
    flagged as a fresh discovery.

    Args:
        ledger (Ledger): The session ledger.
        cwd (str): Canonicalized project working directory.
        ignored (tuple[str, ...]): Ignored path prefixes.
        new (list[str]): Output list for newly discovered files.
        changed (list[str]): Output list for changed files.
    """
    paths = []
    current = cwd
    while True:
        paths.append(os.path.join(current, "CLAUDE.md"))
        if current == "/":
            break
        current = os.path.dirname(current) or "/"
    paths.append(os.path.join(config_dir(), "CLAUDE.md"))

    for path in paths:
        if is_ignored(path, ignored):
            continue
        h = hash_file(path)
        if not h:
            continue
        entry = ledger.get(path)
        if entry is None:
            if h in ledger.known_hashes():
                ledger.record(path, h, KIND_EQUIV)
            else:
                new.append(path)
                ledger.record(path, h, KIND_FLAGGED)
        elif entry["h"] != h:
            if h not in ledger.known_hashes():
                changed.append(path)
            ledger.record(path, h, KIND_CONTEXT)


def mirror_subtree(
    ledger: Ledger,
    directory: str,
    cwd: str,
    ignored: tuple[str, ...],
    changed: list[str],
) -> None:
    """Track memory files Claude Code just loaded inside the project tree.

    Mirrors the built-in on-demand loading: accessing a file under `cwd`
    makes Claude Code load every CLAUDE.md between that directory and the
    project root. Recording their hashes is what lets byte-identical
    copies elsewhere (the worktree case) stay silent. A hash mismatch on
    a previously-loaded file is reported as changed.

    Args:
        ledger (Ledger): The session ledger.
        directory (str): Canonicalized accessed directory under `cwd`.
        cwd (str): Canonicalized project working directory.
        ignored (tuple[str, ...]): Ignored path prefixes.
        changed (list[str]): Output list for changed files.
    """
    current = directory
    while current != cwd and current != "/":
        for name in memory_basenames():
            path = os.path.join(current, name)
            if is_ignored(path, ignored):
                continue
            h = hash_file(path)
            if not h:
                continue
            entry = ledger.get(path)
            loaded_before = entry and entry["k"] in (KIND_CONTEXT, KIND_FLAGGED)
            if (
                loaded_before
                and entry["h"] != h
                and h not in ledger.known_hashes()
            ):
                changed.append(path)
            if name == "CLAUDE.md":
                # Claude Code itself loads these on demand.
                ledger.record(path, h, KIND_CONTEXT)
            elif loaded_before:
                ledger.record(path, h, entry["k"])
            else:
                # AGENTS.md is not natively loaded; known content only.
                ledger.record(path, h, KIND_EQUIV)
        current = os.path.dirname(current) or "/"


def discover_outside(
    ledger: Ledger,
    directory: str,
    cwd: str,
    ignored: tuple[str, ...],
    new: list[str],
    changed: list[str],
    suppressed: list[tuple[str, str]],
) -> None:
    """Walk up from an outside directory collecting files worth flagging.

    Stops at ancestors of `cwd` (already loaded at startup by Claude
    Code). Per directory, CLAUDE.md takes precedence over AGENTS.md. A
    candidate is suppressed when its content hash matches anything the
    ledger already knows.

    Args:
        ledger (Ledger): The session ledger.
        directory (str): Canonicalized starting directory.
        cwd (str): Canonicalized project working directory.
        ignored (tuple[str, ...]): Ignored path prefixes.
        new (list[str]): Output list for newly discovered files.
        changed (list[str]): Output list for changed files.
        suppressed (list[tuple[str, str]]): Output list of
            (candidate, matched ledger path) hash-match suppressions,
            for diagnostics.
    """
    current = directory
    while current != "/":
        if cwd == current or cwd.startswith(current + "/"):
            break

        path = None
        for name in memory_basenames():
            candidate = os.path.join(current, name)
            if os.path.isfile(candidate):
                path = candidate
                break

        if path and is_ignored(path, ignored):
            path = None

        if path:
            h = hash_file(path)
            if h:
                entry = ledger.get(path)
                if entry is None:
                    if h in ledger.known_hashes():
                        suppressed.append((path, ledger.path_for_hash(h) or ""))
                        ledger.record(path, h, KIND_EQUIV)
                    else:
                        new.append(path)
                        ledger.record(path, h, KIND_FLAGGED)
                elif entry["h"] != h:
                    if h in ledger.known_hashes():
                        suppressed.append((path, ledger.path_for_hash(h) or ""))
                        ledger.record(path, h, entry["k"])
                    elif entry["k"] == KIND_EQUIV:
                        new.append(path)
                        ledger.record(path, h, KIND_FLAGGED)
                    else:
                        changed.append(path)
                        ledger.record(path, h, KIND_FLAGGED)

        current = os.path.dirname(current)


def build_message(new: list[str], changed: list[str]) -> str:
    """Build the feedback message for discovered and changed files.

    Args:
        new (list[str]): Newly discovered instruction file paths.
        changed (list[str]): Previously loaded files that changed on disk.

    Returns:
        str: The message to feed back to the model.
    """
    sections = []

    if new:
        if len(new) == 1:
            sections.append(
                "An instruction file was discovered that you have not read "
                "this session.\n"
                "\n"
                "IMPORTANT: You MUST read it immediately.\n"
                "\n"
                f"**File Path**: {new[0]}"
            )
        else:
            file_list = "\n".join(f"  - {path}" for path in new)
            sections.append(
                f"{len(new)} instruction files were discovered that you have "
                "not read this session.\n"
                "\n"
                "IMPORTANT: You MUST read each immediately.\n"
                "\n"
                "**File Paths**:\n"
                f"{file_list}"
            )

    if changed:
        file_list = "\n".join(f"  - {path}" for path in changed)
        plural = "files have" if len(changed) > 1 else "file has"
        sections.append(
            f"The following instruction {plural} changed on disk since "
            "their content was loaded this session.\n"
            "\n"
            "IMPORTANT: You MUST re-read them immediately — the version "
            "in your context is stale.\n"
            "\n"
            "**File Paths**:\n"
            f"{file_list}"
        )

    body = "\n\n".join(sections)
    return (
        "<claude-md-discovery-extended>\n"
        f"{body}\n"
        "\n"
        "If a file references other files via @path imports, read those "
        "too (imports are only auto-resolved for natively loaded memory "
        "files, not for files you read yourself).\n"
        "\n"
        "Once you have read them, continue working on your current task. "
        "IMPORTANT: Do NOT stop to inform the user you have read them.\n"
        "</claude-md-discovery-extended>"
    )


def main() -> None:
    """Entry point that wraps `_main` with a top-level exception guard.

    Hooks must never break the session, so any unexpected exception is
    swallowed — but logged first, with a traceback, or crash-bugs would
    silently disable the plugin with no trace to debug from.
    """
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)

    try:
        _main(data)
    except SystemExit:
        raise
    except Exception:
        log_event(
            data.get("session_id", ""),
            "error",
            script="check_claude_md",
            tool=data.get("tool_name", ""),
            trace=traceback.format_exc(),
        )
        sys.exit(0)


def _main(data: dict) -> None:
    """Update the ledger for one hook invocation and emit discoveries.

    Args:
        data (dict): Parsed hook input.
    """
    os.umask(0o077)

    tool_name: str = data.get("tool_name", "")
    session_id: str = data.get("session_id", "")
    cwd: str = data.get("cwd", "")
    tool_input: dict = data.get("tool_input", {})
    # Subagent tool calls carry an agent id; their transcript is separate
    # from the main agent's, so flagged knowledge is scoped to it.
    scope: str = data.get("agent_id") or ""

    if not tool_name or not session_id or not cwd:
        sys.exit(0)

    # Canonicalize to resolve symlinks and ".." components
    cwd = os.path.realpath(cwd).rstrip("/") or "/"

    ledger = Ledger(session_id, scope)
    if not ledger.seeded:
        # Normally done by the SessionStart hook; cover sessions where it
        # didn't run (e.g. the plugin was enabled mid-session).
        stats = seed_session(ledger, cwd)
        log_event(session_id, "seed", trigger="lazy", **stats)

    new: list[str] = []
    changed: list[str] = []
    suppressed: list[tuple[str, str]] = []
    ignored = ignored_prefixes()

    mark_direct_access(tool_name, tool_input, cwd, ledger)
    refresh_ancestors(ledger, cwd, ignored, new, changed)

    directory = get_target_directory(tool_name, tool_input)
    if directory:
        directory = os.path.realpath(directory).rstrip("/") or "/"
        config = config_dir()
        if directory == cwd or directory.startswith(cwd + "/"):
            mirror_subtree(ledger, directory, cwd, ignored, changed)
        elif not (directory == config or directory.startswith(config + "/")):
            # Never discover inside the Claude Code config dir: its
            # CLAUDE.md is the global user memory (always loaded at
            # startup) and any plugin CLAUDE.md under it is config, not a
            # project the user is working in.
            discover_outside(
                ledger, directory, cwd, ignored, new, changed, suppressed
            )

    ledger.flush()

    for candidate, matched in suppressed:
        log_event(
            session_id, "suppress",
            path=candidate, matched=matched, tool=tool_name, agent=scope,
        )

    if not new and not changed:
        sys.exit(0)

    log_event(
        session_id, "flag",
        tool=tool_name, target=directory or "", new=new, changed=changed,
        agent=scope,
    )
    print(build_message(new, changed), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
