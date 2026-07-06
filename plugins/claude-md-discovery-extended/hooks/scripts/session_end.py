#!/usr/bin/env python3
"""SessionEnd hook: remove session state that can never be useful again.

Only `/clear` (reason `"clear"`) wipes the context while ending the
session record, so only then is the ledger deleted. On every other
reason the ledger is kept: the docs don't guarantee whether a resumed
session keeps its session id, and if it does, deleting state here would
make a resume re-flag every file already in the restored context. Stale
ledgers are garbage-collected by the SessionStart hook instead.
"""

import json
import os
import re
import sys
import traceback

from claude_md_lib import ledger_path, log_event


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
            script="session_end",
            trace=traceback.format_exc(),
        )
        sys.exit(0)


def _main(data: dict) -> None:
    """Delete the ledger when the context was wiped.

    Args:
        data (dict): Parsed hook input.
    """
    session_id: str = data.get("session_id", "")
    reason: str = data.get("reason", "")

    if not session_id or reason != "clear":
        sys.exit(0)

    try:
        os.unlink(ledger_path(session_id))
        log_event(session_id, "clear_delete")
    except OSError:
        pass

    # Pre-0.3 versions tracked state in TMPDIR; clean that up too.
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    legacy = os.path.join(
        os.environ.get("TMPDIR", "/tmp"), f"claude-md-seen-{safe_id}"
    )
    try:
        os.unlink(legacy)
    except OSError:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
