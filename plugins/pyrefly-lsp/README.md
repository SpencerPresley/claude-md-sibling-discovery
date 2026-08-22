# pyrefly-lsp

Python code intelligence for Claude Code backed by [Pyrefly](https://pyrefly.org)
rather than Pyright.

## Why

On a Django codebase Pyright needs heavy suppression to be usable — it can't see
FK `<field>_id` accessors, managers, or `DoesNotExist`, so real findings drown in
false positives. Pyrefly reports what a pyrefly-based type-check gate reports,
which is the point: diagnostics Claude can't trust are worse than none.

Pyrefly's LSP implements every operation Claude Code's `Lsp` tool issues:
definition, references, hover, documentSymbol, workspaceSymbol, implementation,
and call hierarchy.

## Requirements

`uv` on `PATH`. Nothing else.

The server runs as `uvx pyrefly@1.2.0 lsp`, so pyrefly does **not** need to be a
declared dependency of the project — uvx fetches and caches the pinned build.
Pyrefly then discovers the project's own interpreter and site-packages:

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

## Diagnostics

Claude Code injects diagnostics after edits, capped per file and overall, errors
first. Pyrefly also emits IDE-only hints (`unused-parameter`, `unused-variable`)
that its CLI doesn't; those sort last. Add `"diagnostics": false` to the server
config to keep navigation but suppress injection.
