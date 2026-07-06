"""Shared state and discovery logic for the claude-md-discovery-extended hooks.

The plugin keeps one append-only JSONL ledger per session recording every
memory file (CLAUDE.md / AGENTS.md) whose content is known, keyed by path
with a content hash. Discovery suppresses any candidate whose content hash
matches something already known, which is what makes duplicated files (git
worktrees, multiple clones, copied templates) not re-flag.

Ledger entry kinds:
    - ``context``: content is in the model's context via Claude Code's own
      loading (ancestor walk at startup, global user memory, cwd-subtree
      files loaded on demand as the model accesses them).
    - ``flagged``: content entered context through the transcript (the
      plugin flagged it, or the model read/cat'd it directly). These are
      dropped after compaction because the transcript no longer carries them.
    - ``equiv``: content exists inside the project tree (found by the
      session-start scan) but has not necessarily been loaded. Used only to
      suppress byte-identical copies outside the project.
"""

import hashlib
import json
import os
import re
import subprocess
import time

MEMORY_BASENAMES = ("CLAUDE.md", "AGENTS.md")

KIND_CONTEXT = "context"
KIND_FLAGGED = "flagged"
KIND_EQUIV = "equiv"

_KIND_RANK = {KIND_EQUIV: 0, KIND_CONTEXT: 1, KIND_FLAGGED: 1}

SEEDED_MARKER = "__seeded__"

# Directories never worth descending into during the project scan.
SCAN_PRUNE_NAMES = {
    "node_modules",
    "__pycache__",
    "venv",
    "env",
    "dist",
    "build",
    "target",
    "vendor",
    "coverage",
}
SCAN_MAX_DIRS = 3000
SCAN_TIME_BUDGET_SECS = 1.5
GIT_TIMEOUT_SECS = 3

STATE_MAX_AGE_DAYS = 30
LEGACY_MAX_AGE_DAYS = 7

_HASH_READ_CAP = 4 * 1024 * 1024

LOG_MAX_BYTES = 1024 * 1024


def agents_md_enabled() -> bool:
    """Return whether AGENTS.md files participate in discovery.

    Returns:
        bool: `True` unless `CLAUDE_MD_DISCOVERY_AGENTS_MD` is set to a
              falsy value (`0`, `false`, `no`, `off`).
    """
    raw = os.environ.get("CLAUDE_MD_DISCOVERY_AGENTS_MD", "1")
    return raw.strip().lower() not in ("0", "false", "no", "off")


def memory_basenames() -> tuple[str, ...]:
    """Return the instruction-file basenames currently in scope.

    Returns:
        tuple[str, ...]: `("CLAUDE.md", "AGENTS.md")` or just
                         `("CLAUDE.md",)` when AGENTS.md discovery is off.
    """
    if agents_md_enabled():
        return MEMORY_BASENAMES
    return (MEMORY_BASENAMES[0],)


def ignored_prefixes() -> tuple[str, ...]:
    """Parse `CLAUDE_MD_DISCOVERY_IGNORE` into normalized path prefixes.

    The variable holds `os.pathsep`-separated absolute (or `~`-prefixed)
    paths. Anything under an ignored prefix is fully invisible to the
    plugin: never flagged, never recorded, never used for suppression.
    `/` works as a kill switch that disables the plugin entirely.

    Returns:
        tuple[str, ...]: Canonicalized path prefixes, possibly empty.
    """
    raw = os.environ.get("CLAUDE_MD_DISCOVERY_IGNORE", "")
    prefixes = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if part.startswith("~"):
            part = os.path.expanduser(part)
        if part.startswith("/"):
            prefixes.append(os.path.realpath(part).rstrip("/") or "/")
    return tuple(prefixes)


def is_ignored(path: str, prefixes: tuple[str, ...]) -> bool:
    """Return whether a path falls under any ignored prefix.

    Args:
        path (str): Absolute path to test.
        prefixes (tuple[str, ...]): Output of `ignored_prefixes`.
    """
    for prefix in prefixes:
        if prefix == "/" or path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def config_dir() -> str:
    """Return the Claude Code config directory, canonicalized.

    Honors `CLAUDE_CONFIG_DIR`, falling back to `~/.claude`. Everything
    inside this tree is Claude Code's own config and installed plugins;
    its `CLAUDE.md` is the global user memory that Claude Code always loads
    at startup. Discovery must never resurface files from here, or touching
    any config/plugin path (which happens constantly) would nag the model
    to re-read instructions already in context.

    Returns:
        str: The absolute, symlink-resolved config directory path.
    """
    raw = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )
    return os.path.realpath(raw).rstrip("/") or "/"


def state_dir() -> str:
    """Return the directory holding per-session ledgers, creating it if needed.

    Lives under the config dir rather than `TMPDIR` so state survives
    reboots and tmp reapers (macOS purges `/tmp` files unused for 3 days,
    which would make long or resumed sessions re-flag everything).
    `CLAUDE_MD_DISCOVERY_STATE_DIR` overrides the location (used by tests).

    Returns:
        str: The absolute state directory path.
    """
    path = os.environ.get("CLAUDE_MD_DISCOVERY_STATE_DIR") or os.path.join(
        config_dir(), "plugin-state", "claude-md-discovery-extended"
    )
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _safe_id(session_id: str) -> str:
    """Sanitize a session id for use as a filename.

    Args:
        session_id (str): The Claude Code session identifier.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)


def ledger_path(session_id: str) -> str:
    """Return the ledger file path for a session.

    Args:
        session_id (str): The Claude Code session identifier.

    Returns:
        str: Absolute path of the session's JSONL ledger.
    """
    return os.path.join(state_dir(), f"{_safe_id(session_id)}.jsonl")


def log_path(session_id: str) -> str:
    """Return the diagnostic log path for a session.

    Args:
        session_id (str): The Claude Code session identifier.

    Returns:
        str: Absolute path of the session's JSONL event log.
    """
    return os.path.join(state_dir(), f"{_safe_id(session_id)}.log")


def log_event(session_id: str, event: str, **fields) -> None:
    """Append a diagnostic event to the session's log file.

    Event-driven, not per-call: steady-state hook invocations log
    nothing, so a session's log stays small (seeds, flags, suppressions,
    lifecycle actions, and swallowed exceptions). The log lives beside
    the ledger and is reaped by the same GC. Writing stops past
    `LOG_MAX_BYTES` so a pathological event loop can't fill the disk.
    Never raises: diagnostics must not break the hook.

    Args:
        session_id (str): The Claude Code session identifier.
        event (str): Short event name (e.g. `seed`, `flag`, `error`).
        **fields: JSON-serializable event details.
    """
    try:
        path = log_path(session_id or "unknown")
        try:
            if os.path.getsize(path) > LOG_MAX_BYTES:
                return
        except OSError:
            pass
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": event,
            **fields,
        }
        with open(path, "a") as fh:
            fh.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
        os.chmod(path, 0o600)
    except Exception:
        pass


def hash_file(path: str) -> str | None:
    """Return a content hash for a file, or `None` if unreadable.

    Reads at most `_HASH_READ_CAP` bytes and mixes in the file size so
    a pathological multi-megabyte file still hashes deterministically
    without stalling the hook.

    Args:
        path (str): File to hash.

    Returns:
        str | None: Hex digest, or `None` when the file cannot be read.
    """
    try:
        size = os.path.getsize(path)
        digest = hashlib.sha256(str(size).encode() + b"\x00")
        with open(path, "rb") as fh:
            digest.update(fh.read(_HASH_READ_CAP))
        return digest.hexdigest()
    except OSError:
        return None


def load_ledger(path: str) -> tuple[dict[str, dict], bool]:
    """Load a ledger file into a path-keyed mapping.

    Later lines win for the same path, so appends act as updates.
    Malformed lines (e.g. a torn concurrent write) are skipped.

    Args:
        path (str): Ledger file path.

    Returns:
        tuple[dict[str, dict], bool]: Mapping of file path to
            `{"h": hash, "k": kind}`, and whether the session has
            been seeded.
    """
    entries: dict[str, dict] = {}
    seeded = False
    try:
        with open(path, "r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get(SEEDED_MARKER):
                    seeded = True
                    continue
                p, h, k = obj.get("p"), obj.get("h"), obj.get("k")
                if p and h and k in _KIND_RANK:
                    entries[p] = {"h": h, "k": k}
    except OSError:
        pass
    return entries, seeded


def append_entries(path: str, records: list[dict]) -> None:
    """Append records to the ledger as JSONL.

    Written as a single `write()` of small lines so concurrent hook
    invocations (parallel tool calls) interleave at line granularity
    at worst, which `load_ledger` tolerates.

    Args:
        path (str): Ledger file path.
        records (list[dict]): JSON-serializable records to append.
    """
    if not records:
        return
    payload = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records)
    with open(path, "a") as fh:
        fh.write(payload)
    os.chmod(path, 0o600)


def rewrite_ledger(path: str, entries: dict[str, dict], seeded: bool) -> None:
    """Atomically rewrite a ledger from a folded entry mapping.

    Args:
        path (str): Ledger file path.
        entries (dict[str, dict]): Mapping of file path to `{"h", "k"}`.
        seeded (bool): Whether to preserve the seeded marker.
    """
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        if seeded:
            fh.write(json.dumps({SEEDED_MARKER: True}) + "\n")
        for p, meta in entries.items():
            record = {"p": p, "h": meta["h"], "k": meta["k"]}
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class Ledger:
    """In-memory view of a session ledger with pending-append buffering."""

    def __init__(self, session_id: str):
        """Load the ledger for a session.

        Args:
            session_id (str): The Claude Code session identifier.
        """
        self.path = ledger_path(session_id)
        self.entries, self.seeded = load_ledger(self.path)
        self._pending: list[dict] = []
        self._hashes: set[str] | None = None

    def known_hashes(self) -> set[str]:
        """Return the set of every content hash in the ledger."""
        if self._hashes is None:
            self._hashes = {meta["h"] for meta in self.entries.values()}
        return self._hashes

    def path_for_hash(self, content_hash: str) -> str | None:
        """Return some ledger path holding the given hash, for diagnostics.

        Args:
            content_hash (str): Content hash to look up.
        """
        for path, meta in self.entries.items():
            if meta["h"] == content_hash:
                return path
        return None

    def get(self, path: str) -> dict | None:
        """Return the entry for a path, or `None`.

        Args:
            path (str): Memory-file path to look up.
        """
        return self.entries.get(path)

    def record(self, path: str, content_hash: str, kind: str) -> None:
        """Record a path/hash/kind, buffering an append if it changes state.

        No-ops when the ledger already holds the same hash at an equal or
        higher kind rank, so steady-state hook runs append nothing.

        Args:
            path (str): Memory-file path.
            content_hash (str): Content hash of the file.
            kind (str): One of the ledger kinds.
        """
        existing = self.entries.get(path)
        if (
            existing
            and existing["h"] == content_hash
            and _KIND_RANK[existing["k"]] >= _KIND_RANK[kind]
        ):
            return
        self.entries[path] = {"h": content_hash, "k": kind}
        self.known_hashes().add(content_hash)
        self._pending.append({"p": path, "h": content_hash, "k": kind})

    def mark_seeded(self) -> None:
        """Buffer the seeded marker."""
        if not self.seeded:
            self.seeded = True
            self._pending.append({SEEDED_MARKER: True})

    def flush(self) -> None:
        """Write any buffered records to disk."""
        append_entries(self.path, self._pending)
        self._pending = []


def scan_project(cwd: str) -> tuple[list[str], str, bool]:
    """Enumerate memory files under a project tree.

    Uses `git ls-files` when available (fast, respects .gitignore, and in
    a worktree lists exactly that worktree's checkout). Falls back to a
    bounded `os.walk` that prunes hidden and dependency directories and
    gives up past `SCAN_MAX_DIRS` directories or the time budget.

    Args:
        cwd (str): Project root to scan.

    Returns:
        tuple[list[str], str, bool]: Absolute paths of memory files found
            under `cwd`, the scan method (`git`, `walk`, or `skipped`),
            and whether the walk was truncated by its bounds (a truncated
            scan means missing suppression hashes, which shows up later
            as unexpected flags — worth surfacing in diagnostics).
    """
    if cwd == "/":
        return [], "skipped", False

    names = set(memory_basenames())

    found = _scan_via_git(cwd, names)
    if found is not None:
        return found, "git", False

    found, truncated = _scan_via_walk(cwd, names)
    return found, "walk", truncated


def _scan_via_git(cwd: str, names: set[str]) -> list[str] | None:
    """List memory files via git, or `None` when git can't answer.

    Args:
        cwd (str): Project root to scan.
        names (set[str]): Memory-file basenames to match.
    """
    patterns = [f"*{name}" for name in names]
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "ls-files", "-z", "--cached", "--others",
             "--exclude-standard", "--", *patterns],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None

    found = []
    for rel in proc.stdout.decode("utf-8", "replace").split("\0"):
        if rel and os.path.basename(rel) in names:
            path = os.path.join(cwd, rel)
            if os.path.isfile(path):
                found.append(path)
    return found


def _scan_via_walk(cwd: str, names: set[str]) -> tuple[list[str], bool]:
    """List memory files via a bounded directory walk.

    Args:
        cwd (str): Project root to scan.
        names (set[str]): Memory-file basenames to match.

    Returns:
        tuple[list[str], bool]: Paths found and whether the walk stopped
            early on the directory cap or time budget.
    """
    found: list[str] = []
    deadline = time.monotonic() + SCAN_TIME_BUDGET_SECS
    visited = 0
    truncated = False
    for root, dirs, files in os.walk(cwd):
        visited += 1
        if visited > SCAN_MAX_DIRS or time.monotonic() > deadline:
            truncated = True
            break
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in SCAN_PRUNE_NAMES
        ]
        for name in names:
            if name in files:
                found.append(os.path.join(root, name))
    return found, truncated


def seed_session(ledger: Ledger, cwd: str) -> dict:
    """Seed a fresh ledger with everything already known at session start.

    Records ancestor CLAUDE.md files (loaded by Claude Code's startup walk)
    and the global user memory as ``context``, and every memory file found
    under `cwd` as ``equiv`` so byte-identical copies outside the project
    (worktrees, sibling clones) never flag.

    Args:
        ledger (Ledger): The session ledger.
        cwd (str): Canonicalized project working directory.

    Returns:
        dict: Seed statistics for diagnostics (ancestor and project-file
            counts, scan method, truncation).
    """
    ignored = ignored_prefixes()
    ancestors = 0
    project_files = 0

    for path in ancestor_memory_files(cwd):
        h = hash_file(path)
        if h and not is_ignored(path, ignored):
            ledger.record(path, h, KIND_CONTEXT)
            ancestors += 1

    global_memory = os.path.join(config_dir(), "CLAUDE.md")
    h = hash_file(global_memory)
    if h and not is_ignored(global_memory, ignored):
        ledger.record(global_memory, h, KIND_CONTEXT)

    scanned, method, truncated = scan_project(cwd)
    for path in scanned:
        h = hash_file(path)
        if h and not is_ignored(path, ignored):
            ledger.record(path, h, KIND_EQUIV)
            project_files += 1

    ledger.mark_seeded()
    return {
        "cwd": cwd,
        "ancestors": ancestors,
        "project_files": project_files,
        "scan_method": method,
        "scan_truncated": truncated,
    }


def ancestor_memory_files(cwd: str) -> list[str]:
    """Return existing CLAUDE.md paths at `cwd` and every ancestor.

    Only CLAUDE.md participates: it is what Claude Code's startup walk
    actually loads.

    Args:
        cwd (str): Canonicalized project working directory.

    Returns:
        list[str]: Existing ancestor CLAUDE.md paths, nearest first.
    """
    found = []
    current = cwd
    while True:
        candidate = os.path.join(current, "CLAUDE.md")
        if os.path.isfile(candidate):
            found.append(candidate)
        if current == "/":
            break
        current = os.path.dirname(current) or "/"
    return found


def gc_state(now: float | None = None) -> tuple[int, int]:
    """Delete stale session state (ledgers and logs) and legacy files.

    Sessions that crash or never fire SessionEnd leave state behind;
    anything untouched for `STATE_MAX_AGE_DAYS` is dead. Also sweeps the
    pre-0.3 `claude-md-seen-*` files out of `TMPDIR`.

    Args:
        now (float | None): Current epoch seconds, injectable for tests.

    Returns:
        tuple[int, int]: Count of state files and legacy files removed.
    """
    now = time.time() if now is None else now
    state_removed = 0
    legacy_removed = 0

    sdir = state_dir()
    cutoff = now - STATE_MAX_AGE_DAYS * 86400
    try:
        for name in os.listdir(sdir):
            path = os.path.join(sdir, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.unlink(path)
                    state_removed += 1
            except OSError:
                continue
    except OSError:
        pass

    tmpdir = os.environ.get("TMPDIR", "/tmp")
    legacy_cutoff = now - LEGACY_MAX_AGE_DAYS * 86400
    try:
        for name in os.listdir(tmpdir):
            if not name.startswith("claude-md-seen-"):
                continue
            path = os.path.join(tmpdir, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < legacy_cutoff:
                    os.unlink(path)
                    legacy_removed += 1
            except OSError:
                continue
    except OSError:
        pass

    return state_removed, legacy_removed
