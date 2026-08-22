# pyrefly-lsp

Python code intelligence for Claude Code backed by [Pyrefly](https://pyrefly.org)
rather than Pyright.

## Why

Use the same checker for Claude Code navigation and a pyrefly-based type-check
gate. Definitions, references, and diagnostics then come from the same analysis
engine instead of two tools with different inference behavior.

Pyrefly's LSP implements every operation Claude Code's `Lsp` tool issues:
definition, references, hover, documentSymbol, workspaceSymbol, implementation,
and call hierarchy.

## Requirements

`uv` on `PATH`. Nothing else.

The plugin runs its bundled adapter with `uv run --no-project`, then the adapter
starts `uvx pyrefly@1.2.0 lsp --indexing-mode lazy-blocking`. Pyrefly does **not**
need to be a declared project dependency, and starting the adapter never syncs or
prunes the project's environment. Pyrefly discovers the project's own interpreter
and site-packages:

```
Using interpreter: <project>/.venv/bin/python3
Site package path: [<project>/.venv/lib/python3.12/site-packages, ...]
```

so analysis runs against the project's real environment, not uvx's. Verified
identical to running pyrefly from inside the venv.

The alternative — `"command": "uv", "args": ["run", "--quiet", "pyrefly", "lsp"]`
— uses whatever version the project pins, but fails with `Failed to spawn:
pyrefly` in any checkout whose venv hasn't synced the group declaring it. Only
use it if every venv is guaranteed to have pyrefly.

## Complete first results

Claude Code includes the workspace folder in its LSP `initialize` request but
advertises `capabilities.workspace.workspaceFolders = false`. Pyrefly 1.2.0
therefore ignores the supplied folder and indexes only the nearest configured
project. Its default non-blocking indexing mode can also answer a workspace-wide
request before the index finishes.

The adapter changes only that capability to `true`; the folder URI and every
other initialization field remain untouched. Blocking indexing then processes
the `didOpen` that Claude sends before its navigation request, so the first
`findReferences` answer includes the workspace rather than growing across later
calls. The protocol regression test also covers Claude's preceding `$/setTrace`
notification so initialization is still the message that gets rewritten.

## Monorepos

One server covers the workspace. Pyrefly discovers config per file by walking up
to the nearest `[tool.pyrefly]`, so a repo with several configured packages
resolves each file against its own, and files under no config fall back to
defaults. No server-per-package needed.

## Known limitation: gitignored working copies

Pyrefly's ignore-file search walks **up** from the project root and applies any
`.gitignore` it finds. If your checkout sits inside a path an ancestor
`.gitignore` excludes, workspace-wide operations degrade *silently* — 
`findReferences` and `workspaceSymbol` return a small, plausible, wrong answer
rather than an error. Per-file operations (diagnostics, hover, goToDefinition)
are unaffected.

This bites git worktrees created under `.claude/worktrees/`, since that path is
commonly gitignored. `use-ignore-files = false` is a valid config key but does
not restore it; a `.ignore` negation at the working-copy root only partially
does. Check before trusting reference counts in such a checkout.

## Preflight

A `SessionStart` hook checks the two things that make this plugin fail *quietly*
and reports them as a transcript error notice (exit 2), which the user sees and
the model does not — so a warning costs no context:

- `uv` missing from `PATH`. The server can't spawn; Claude Code logs
  `Executable not found in $PATH` in the `/plugin` Errors tab, which is easy to
  miss because everything else keeps working.
- A linked worktree matched by a rule in `.git/info/exclude`. Pyrefly then
  indexes only the open file, and `findReferences`/`workspaceSymbol` under-report
  with no error at all.

It uses no subprocesses and costs ~0.4ms over bash's own startup, measured
across main checkouts, worktrees, and non-git directories.

Note it deliberately does *not* warn when a main checkout's `.gitignore` matches
a worktree path — that's normal and harmless, because pyrefly resolves the
worktree's own `.gitignore` relative to the worktree root, where those patterns
don't match. Only `.git/info/exclude`, which is shared across worktrees, breaks
indexing.

## Diagnostics

Claude Code injects diagnostics after edits, capped per file and overall, errors
first. Pyrefly also emits IDE-only hints (`unused-parameter`, `unused-variable`)
that its CLI doesn't; those sort last. Add `"diagnostics": false` to the server
config to keep navigation but suppress injection.
