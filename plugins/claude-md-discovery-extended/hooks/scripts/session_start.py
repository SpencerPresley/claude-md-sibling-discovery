#!/usr/bin/env python3
"""SessionStart hook: seed the session ledger and maintain plugin state.

Responsibilities per `source`:
    - `startup` / `resume`: seed the ledger (ancestor CLAUDE.md files, the
      global user memory, and a scan of the project tree for
      byte-identical-copy suppression).
    - `clear`: the context was wiped, so any prior ledger for this session
      id is invalid — delete it and seed fresh.
    - `compact`: entries that lived only in the transcript (plugin-flagged
      or model-read files) were lost to compaction; drop them so they
      re-flag on next access. Natively loaded files survive or reload on
      demand, so they stay.

Also garbage-collects state from sessions that never fired SessionEnd.
"""

import json
import os
import sys
import traceback

from claude_md_lib import (
    Ledger,
    gc_state,
    ledger_path,
    load_ledger,
    log_event,
    rewrite_ledger,
    seed_session,
)


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
            script="session_start",
            trace=traceback.format_exc(),
        )
        sys.exit(0)


def _main(data: dict) -> None:
    """Prepare session state for one SessionStart event.

    Args:
        data (dict): Parsed hook input.
    """
    os.umask(0o077)

    session_id: str = data.get("session_id", "")
    cwd: str = data.get("cwd", "")
    source: str = data.get("source", "")

    if not session_id or not cwd:
        sys.exit(0)

    state_removed, legacy_removed = gc_state()
    if state_removed or legacy_removed:
        log_event(
            session_id, "gc",
            state_removed=state_removed, legacy_removed=legacy_removed,
        )

    cwd = os.path.realpath(cwd).rstrip("/") or "/"
    lpath = ledger_path(session_id)

    if source == "clear":
        try:
            os.unlink(lpath)
            log_event(session_id, "clear_reset")
        except OSError:
            pass
    elif source == "compact":
        # Flagged entries lived in transcripts: the main transcript was
        # just compacted, and any subagent transcripts are gone entirely.
        entries, flagged, seeded = load_ledger(lpath)
        if flagged:
            rewrite_ledger(lpath, entries, {}, seeded)
            dropped = sorted({p for (p, _) in flagged})
            log_event(session_id, "compact_drop", dropped=dropped)

    ledger = Ledger(session_id)
    if not ledger.seeded:
        stats = seed_session(ledger, cwd)
        ledger.flush()
        log_event(session_id, "seed", trigger=source or "startup", **stats)

    sys.exit(0)


if __name__ == "__main__":
    main()
