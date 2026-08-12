#!/usr/bin/env python3
"""Inject LangChain's parsed-docstring constraints during fix-docstrings.

LangChain only parses Google-style argument descriptions when a tool is built
with ``parse_docstring=True``. This hook finds that explicit opt-in on known
LangChain decorators and tool factory calls, including aliased imports and
``StructuredTool.from_function``.

State is scoped to one skill invocation. A trigger writes a fresh generation;
files are deduplicated only within that generation, and Stop/SessionEnd remove
the active marker. Every injected reminder is self-contained so it never relies
on an earlier reference surviving context compaction.

Modes (argv[1]):
  trigger  Mark the skill active for this session. Fired both by
           UserPromptExpansion (direct `/fix-docstrings ...`) and by PostToolUse
           on the Skill tool (when the model invokes the skill itself), so every
           invocation route arms the detector. On the UserPromptExpansion path
           the typed target is available in command_args, so trigger also scans
           the named files/dirs up front and injects the exact list of files that
           enable docstring parsing (pre-seeding state so Read won't repeat them).
  detect   Fired by PostToolUse on Read. If the skill is active and the file just
           read explicitly enables parsed tool docstrings, emit the parser rule
           and reference as additionalContext once per invocation.
  cleanup  Fired by Stop and SessionEnd. Disarm detection for the session.

argv[2] is CLAUDE_PLUGIN_ROOT, used to resolve the reference file path.

State lives in per-session marker files under the temp dir. ``.active`` and each
``.seen-<hash>`` contain an invocation generation. A seen marker suppresses a
file only when its generation matches the current active generation.
"""
import ast
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid

REFERENCE_REL = "skills/fix-docstrings/references/langchain-tool-docstrings.md"

LANGCHAIN_MODULES = ("langchain", "langchain_core")
PARSER_CALL_SUFFIXES = (
    ".StructuredTool.from_function",
    ".create_schema_from_function",
    ".tool",
)


def flag_path(kind, session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    return os.path.join(tempfile.gettempdir(), f"fix-docstrings-{safe}.{kind}")


def seen_marker(session_id, file_path):
    digest = hashlib.sha1(file_path.encode("utf-8")).hexdigest()[:16]
    return flag_path(f"seen-{digest}", session_id)


def read_marker(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def write_marker(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(value)


def is_langchain_module(module):
    """Whether an import path belongs to a LangChain Python package."""
    return any(module == root or module.startswith(f"{root}.") for root in LANGCHAIN_MODULES)


def import_bindings(tree):
    """Map local import names to fully qualified LangChain symbols."""
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not is_langchain_module(alias.name):
                    continue
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    root = alias.name.split(".", 1)[0]
                    bindings[root] = root
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not is_langchain_module(module):
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                bindings[alias.asname or alias.name] = f"{module}.{alias.name}"
    return bindings


def resolve_reference(node, bindings):
    """Resolve a name or attribute chain through known LangChain imports."""
    if isinstance(node, ast.Name):
        return bindings.get(node.id, "")
    if isinstance(node, ast.Attribute):
        base = resolve_reference(node.value, bindings)
        if base:
            return f"{base}.{node.attr}"
    return ""


def enables_docstring_parsing(call):
    """Whether a call contains the literal opt-in ``parse_docstring=True``."""
    return any(
        keyword.arg == "parse_docstring"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def is_langchain_parser_call(call, bindings):
    """Whether a call is a known LangChain tool/parser construction path."""
    reference = resolve_reference(call.func, bindings)
    return bool(reference) and reference.endswith(PARSER_CALL_SUFFIXES)


def source_has_parsed_tool(source):
    """Whether source explicitly enables LangChain-style docstring parsing."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    bindings = import_bindings(tree)
    return any(
        isinstance(node, ast.Call)
        and enables_docstring_parsing(node)
        and is_langchain_parser_call(node, bindings)
        for node in ast.walk(tree)
    )


def is_tool_file(path):
    """True if the file explicitly enables parsed LangChain tool docstrings."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            source = handle.read()
    except OSError:
        return False
    return source_has_parsed_tool(source)


# Guard so a pathological directory tree can't stall the hook past its timeout.
MAX_SCAN_FILES = 1000


def scan_targets(command_args, cwd):
    """Find parser-enabled tool files in paths named by command_args.

    Each whitespace token is resolved against cwd; a leading `@` (Claude's
    file-mention syntax) and trailing slashes/commas are stripped. Files are
    checked directly; directories are walked. Returns sorted absolute paths,
    bounded by MAX_SCAN_FILES.
    """
    found = set()
    budget = MAX_SCAN_FILES
    for token in (command_args or "").split():
        candidate = token.lstrip("@").rstrip("/,")
        if not candidate:
            continue
        path = candidate if os.path.isabs(candidate) else os.path.join(cwd or "", candidate)
        if os.path.isfile(path):
            if path.endswith(".py") and is_tool_file(path):
                found.add(os.path.abspath(path))
        elif os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in files:
                    if not name.endswith(".py"):
                        continue
                    budget -= 1
                    if budget < 0:
                        return sorted(found)
                    fpath = os.path.join(root, name)
                    if is_tool_file(fpath):
                        found.add(os.path.abspath(fpath))
    return sorted(found)


def read_event():
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def mode_trigger(event, plugin_root):
    """Arm the detector and list parser-enabled files in a typed target.

    The upfront scan needs the typed target, which only the slash-command
    (UserPromptExpansion) path carries in command_args. Model invocation via the
    Skill tool has no target, so it just arms the per-file Read detector.
    """
    session_id = event.get("session_id", "")
    is_expansion = event.get("hook_event_name") == "UserPromptExpansion"
    if is_expansion:
        name = event.get("command_name", "") or ""
    else:  # PostToolUse on the Skill tool
        name = (event.get("tool_input") or {}).get("skill", "") or ""
    if "fix-docstrings" not in name:
        return
    generation = uuid.uuid4().hex
    write_marker(flag_path("active", session_id), generation)

    if not is_expansion:
        return
    tool_files = scan_targets(event.get("command_args", ""), event.get("cwd", ""))
    if not tool_files:
        return

    # Pre-seed this invocation so the Read detector won't repeat the upfront
    # self-contained warning for the same files.
    for fpath in tool_files:
        write_marker(seen_marker(session_id, fpath), generation)

    reference = os.path.join(plugin_root, REFERENCE_REL)
    listed = "\n".join(f"  - {fpath}" for fpath in tool_files)
    context = (
        f"The `/fix-docstrings` target enables LangChain docstring parsing with "
        f"`parse_docstring=True` in these files:\n{listed}\n\nRead the LangChain "
        f"tool docstring rules at `{reference}` before editing them. Parenthesized "
        f"types are accepted by LangChain for annotated parameters. "
        f"Every documented `Args` parameter requires a signature annotation; a "
        f"docstring `(type)` does not substitute for one. "
        f"The parser-specific hazard is a colon-bearing continuation under `Args` "
        f"(for example, `- mode:`), which becomes a bogus argument name. Rewrite "
        f"such nested entries as prose."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptExpansion",
            "additionalContext": context,
        }
    }))


def mode_detect(event, plugin_root):
    """Flag a just-read file with parser-enabled LangChain tool docstrings."""
    session_id = event.get("session_id", "")
    generation = read_marker(flag_path("active", session_id))
    if not generation:
        return

    file_path = (event.get("tool_input") or {}).get("file_path", "") or ""
    if not file_path.endswith(".py"):
        return
    seen = seen_marker(session_id, file_path)
    if read_marker(seen) == generation:
        return
    if not is_tool_file(file_path):
        return

    write_marker(seen, generation)
    reference = os.path.join(plugin_root, REFERENCE_REL)
    context = (
        f"`{file_path}` enables LangChain docstring parsing with "
        f"`parse_docstring=True`. Before editing its parsed tool docstrings, read "
        f"`{reference}`. Parenthesized types are accepted by LangChain for annotated "
        f"parameters. "
        f"Every documented `Args` parameter requires a signature annotation; a "
        f"docstring `(type)` does not substitute for one. The parser-specific hazard "
        f"is a colon-bearing "
        f"continuation under `Args` (for example, `- mode:`), which becomes a bogus "
        f"argument name. Rewrite such nested entries as prose."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }))


def mode_cleanup(event):
    """Disarm detection when the skill invocation or session ends."""
    try:
        os.unlink(flag_path("active", event.get("session_id", "")))
    except FileNotFoundError:
        pass


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    plugin_root = (
        sys.argv[2] if len(sys.argv) > 2 else os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    )
    event = read_event()
    if mode == "trigger":
        mode_trigger(event, plugin_root)
    elif mode == "detect":
        mode_detect(event, plugin_root)
    elif mode == "cleanup":
        mode_cleanup(event)


if __name__ == "__main__":
    main()
