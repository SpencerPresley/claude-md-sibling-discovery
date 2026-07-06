#!/usr/bin/env python3
"""UserPromptSubmit hook: catch instruction-file changes at the turn boundary.

PostToolUse change detection only fires when the model touches a path. If
the user edits a CLAUDE.md while the model idles and the next turn is
answered from pure reasoning (no tool call), the stale-rules window stays
open for the whole turn. This hook closes it: on each prompt it re-hashes
the ancestor chain, the global user memory, and every in-project
instruction file already known to be loaded, and injects a re-read nudge
when content changed.

Deliberately NOT re-checked here: outside-the-project flagged files. Those
are only re-checked when the model actually touches their tree again
(PostToolUse) — a changed file in a tree the model is no longer working in
is not worth a nudge on every prompt.

Output semantics: on UserPromptSubmit, stdout with exit 0 is injected as
context. Exit 2 would BLOCK the user's prompt — never used here.
"""

import json
import os
import sys
import traceback

from claude_md_lib import (
    KIND_CONTEXT,
    Ledger,
    hash_file,
    ignored_prefixes,
    is_ignored,
    log_event,
)
from check_claude_md import build_message, refresh_ancestors


def check_project_entries(
    ledger: Ledger,
    cwd: str,
    ignored: tuple[str, ...],
    changed: list[str],
) -> None:
    """Re-hash in-project instruction files the ledger says were loaded.

    Covers subtree CLAUDE.mds recorded by the PostToolUse mirror. Runs
    after `refresh_ancestors`, which already updates ancestor entries —
    their hashes then match and are skipped here, so nothing is reported
    twice.

    Args:
        ledger (Ledger): The session ledger.
        cwd (str): Canonicalized project working directory.
        ignored (tuple[str, ...]): Ignored path prefixes.
        changed (list[str]): Output list for changed files.
    """
    for path, meta in list(ledger.entries.items()):
        if meta["k"] != KIND_CONTEXT:
            continue
        if not (path == cwd or path.startswith(cwd + "/")):
            continue
        if is_ignored(path, ignored):
            continue
        h = hash_file(path)
        if not h or h == meta["h"]:
            continue
        if h not in ledger.known_hashes():
            changed.append(path)
        ledger.record(path, h, KIND_CONTEXT)


def main() -> None:
    """Entry point that wraps `_main` with a logging exception guard."""
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
            script="user_prompt_check",
            trace=traceback.format_exc(),
        )
        sys.exit(0)


def _main(data: dict) -> None:
    """Run the turn-boundary staleness check for one prompt.

    Args:
        data (dict): Parsed hook input.
    """
    os.umask(0o077)

    session_id: str = data.get("session_id", "")
    cwd: str = data.get("cwd", "")

    if not session_id or not cwd:
        sys.exit(0)

    cwd = os.path.realpath(cwd).rstrip("/") or "/"

    ledger = Ledger(session_id)
    if not ledger.seeded:
        # Seeding (and its project scan) is SessionStart's job; keep the
        # prompt path fast.
        sys.exit(0)

    ignored = ignored_prefixes()
    new: list[str] = []
    changed: list[str] = []

    refresh_ancestors(ledger, cwd, ignored, new, changed)
    check_project_entries(ledger, cwd, ignored, changed)
    ledger.flush()

    if not new and not changed:
        sys.exit(0)

    log_event(
        session_id, "flag",
        tool="UserPromptSubmit", target="", new=new, changed=changed,
    )
    print(build_message(new, changed))
    sys.exit(0)


if __name__ == "__main__":
    main()
