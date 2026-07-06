# claude-md-discovery-extended

A Claude Code plugin that fills a gap in `CLAUDE.md` auto-discovery. Claude Code has built-in discovery for some directory relationships but not all. This plugin covers what Claude Code doesn't: sibling directories, cousin directories, or completely unrelated trees. Discovery happens on demand when the model accesses files in those directories, is deduplicated by **content hash** (so git worktrees, extra clones, and copied templates never re-flag instructions already known), and nudges the model to re-read an instruction file when it changes on disk mid-session.

**Example directory relationships:**

```text
grandparent/
  parent/
    projectA/  ← your project
    projectB/  ← sibling
  tools/
    linter/    ← cousin
other-team/
  services/
    api/       ← unrelated tree
```

## Background

Claude Code loads `CLAUDE.md` files from three sources:

1. **Ancestor directories**: at launch, Claude Code walks up from the working directory and loads every `CLAUDE.md` it finds.
2. **Child directories**: when the model reads a file in a subdirectory, Claude Code loads any `CLAUDE.md` along that subdirectory's path.
3. **Explicit directories**: passing `--add-dir` at launch with `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` loads `CLAUDE.md` files from specified directories at startup.

See the [CLAUDE.md docs](https://code.claude.com/docs/en/memory) for full details.

None of these cover directories outside the ancestor/child path discovered mid-session. If you launch in `projectA`:

```text
grandparent/
  CLAUDE.md           <- loaded (ancestor)
  parent/
    projectA/         <- your project (cwd)
      CLAUDE.md       <- loaded (project root)
      src/
        CLAUDE.md     <- loaded (child, on demand)
    projectB/
      CLAUDE.md       <- NOT loaded
    projectC/
      CLAUDE.md       <- NOT loaded
  tools/
    linter/
      CLAUDE.md       <- NOT loaded
other-team/
  services/
    api/
      CLAUDE.md       <- NOT loaded
```

Every `CLAUDE.md` outside the ancestor/child path won't be auto-loaded. The model can still read them manually, but it almost never will on its own, so you'd have to stop it and tell it to. This plugin handles that automatically.

`--add-dir` can solve this, but it loads everything at startup. You need to know which directories matter ahead of time, specify them every session, and their `CLAUDE.md` contents occupy the context window from the start whether they end up being relevant or not. This plugin takes a [progressive disclosure](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) approach instead: `CLAUDE.md` files are discovered and loaded on demand as the model accesses files in those directories, keeping the context window lean until the instructions are actually needed.

## How It Works

Each session keeps a ledger of every instruction file whose content is known, recorded as a path plus a SHA-256 content hash:

- **Ancestor `CLAUDE.md` files** and the **global user memory** (`~/.claude/CLAUDE.md`), loaded by Claude Code at startup.
- **Project-subtree `CLAUDE.md` files** as Claude Code loads them on demand.
- **Every instruction file inside the project tree**, found by a scan at session start (via `git ls-files` when available, so it's fast and respects `.gitignore`; a bounded directory walk otherwise). These count as "known content" for deduplication even before they're loaded.
- **Files the plugin flagged** and **files the model read or wrote directly** (`Read`, `Write`, `Edit`, or a Bash `cat`).

When the model accesses a path outside the project tree, the plugin walks up the directory tree collecting instruction files and flags only the ones whose **content hash matches nothing in the ledger**. Suppression is by content, not path, which handles:

- **Git worktrees** — a session in `repo/.worktrees/foo` that touches the main checkout won't be told to re-read `CLAUDE.md` files byte-identical to the worktree's own. If a copy diverged (different branch, different rules), it still flags — the instructions genuinely differ.
- **Multiple clones** of the same repository.
- **Copied templates** — identical `CLAUDE.md` files stamped across sibling projects flag once, not N times.

### Change detection

Claude Code loads memory files once and never reloads them mid-session. The plugin tracks content hashes, so when a previously-loaded instruction file changes on disk — you edited the project `CLAUDE.md` while the model worked — the model gets a single nudge to re-read it. Changes the model itself makes via `Write`/`Edit` don't trigger the nudge (that content is already in its context). An ancestor `CLAUDE.md` created after session start (which the startup walk never saw) is flagged as a fresh discovery.

### Context lifecycle awareness

- **`/clear`** wipes the context, so the session ledger is reset and discovery starts fresh.
- **Compaction** drops content that only lived in the transcript. Files the plugin flagged are demoted so they re-flag on next relevant access; natively-loaded files (which Claude Code re-injects or reloads on demand) stay suppressed.
- **Resume** keeps the ledger, so a resumed session doesn't get re-nagged about files already in its restored context.

### AGENTS.md

Claude Code does **not** natively load `AGENTS.md`. For directories outside the project tree, the plugin flags `AGENTS.md` when there's no `CLAUDE.md` beside it, so repos that standardized on `AGENTS.md` still surface their instructions. Inside your own project tree the plugin stays out of the way (that setup is your call — use `@AGENTS.md` imports there). Set `CLAUDE_MD_DISCOVERY_AGENTS_MD=0` to disable.

### Hooks

Three [hooks](https://code.claude.com/docs/en/hooks):

- **PostToolUse** (matcher: `Read|Glob|Grep|Edit|Write|Bash`): updates the ledger and reports new or changed instruction files. For the Bash tool, paths are extracted from the command string using `shlex` tokenization.
- **SessionStart**: verifies `python3` is available, seeds the ledger (ancestors, global memory, project scan), handles `/clear` and compaction, and garbage-collects stale state.
- **SessionEnd**: deletes the ledger on `/clear`; keeps it otherwise so resumed sessions don't re-flag.

State lives under `~/.claude/plugin-state/claude-md-discovery-extended/` (one small JSONL file per session) rather than `/tmp`, so it survives reboots and macOS's periodic tmp cleanup. Files from sessions that never ended cleanly are garbage-collected after 30 days.

### Imports

`@path` imports inside memory files are only auto-resolved by Claude Code for files it loads natively. A flagged file is read by the model directly, so its imports don't expand — the discovery message explicitly tells the model to follow any `@path` references it finds.

## Configuration

Environment variables (set them in your shell or via `env` in settings):

- `CLAUDE_MD_DISCOVERY_AGENTS_MD=0` — disable AGENTS.md discovery.
- `CLAUDE_MD_DISCOVERY_IGNORE=/path/one:/path/two` — path prefixes (separated by `:`, `~` allowed) the plugin treats as invisible: never flagged, never tracked for changes, never used for suppression. `CLAUDE_MD_DISCOVERY_IGNORE=/` disables the plugin entirely.
- `CLAUDE_MD_DISCOVERY_STATE_DIR=/path` — override the state directory.

## Diagnostics

Each session writes an event log beside its ledger (`~/.claude/plugin-state/claude-md-discovery-extended/<session>.log`, JSONL, reaped by the same 30-day GC). Logging is event-driven — steady-state tool calls write nothing — and stops at 1&nbsp;MB per session as a runaway guard. Events:

- `seed` — what was seeded and how: ancestor/project-file counts, scan method (`git`/`walk`/`skipped`), and whether the walk was truncated by its bounds (a truncated scan means missing suppression hashes, which is the likely explanation for a later unexpected flag).
- `flag` — every discovery message emitted, with the triggering tool and target.
- `suppress` — every hash-match suppression, naming the ledger path whose content matched (answers "why didn't it flag X?").
- `compact_drop`, `clear_reset` / `clear_delete`, `gc` — lifecycle actions.
- `error` — hooks must never break a session, so unexpected exceptions exit 0 — but the traceback lands here instead of vanishing.

## Requirements

- **Python 3.10+**: runs all hooks. Typically pre-installed on macOS and most Linux distributions.

## Limitations

- **Bash path extraction is best-effort**: paths are extracted from Bash commands via `shlex` tokenization. This handles common patterns (`cat /path/to/file`, `ls /some/dir`, quoted paths) but won't catch paths in redirects, pipes, or subshells.
- **Suppression assumes the project copy is reachable**: a byte-identical copy inside the project tree suppresses the outside one on the theory that Claude Code's own discovery covers the project copy. If the model only ever touches the outside copy and never works in the corresponding project directory, those instructions don't enter context. This is deliberate: the worktree/clone case (where the content is the same and the session's real work happens inside the project) is overwhelmingly more common, and false nags are worse than a rare miss.
- **Grep content matches**: `Grep` triggers discovery for its search root, but files surfaced purely as content matches deep in the tree don't trigger discovery until the model actually reads one.

## License

MIT
