# using-codex-cli

A reference skill for driving the OpenAI Codex CLI (`codex`) non-interactively — from Claude Code's Bash tool, scripts, or CI.

Every core claim in the skill was verified by actually executing codex-cli 0.149.1 (headless `exec`, `exec resume --last`, `--json` event stream, `exec review --uncommitted`, non-TTY behavior of bare `codex`), not just by reading `--help`. The gotcha table exists because each entry either failed a real run or was confidently asserted wrong by a baseline agent working from training data.

## Relationship to the spencer-codex plugin

This skill deliberately lives **outside** the [codex-plugin-cc](https://github.com/SpencerPresley/codex-plugin-cc) fork. That plugin routes all Codex work through its companion runtime for job tracking, and its internal contract tells agents to prefer the runtime over raw CLI strings — baking raw-CLI instructions into the same plugin would hand agents license to bypass the runtime that `/codex:status`, `/codex:result`, and `/codex:cancel` depend on. The skill's precedence note points plugin-shaped work (reviews, delegated fixes) back at `/codex:*`.

## Contents

- `skills/using-codex-cli/SKILL.md` — rules, quick reference, output contract, sandbox/approvals, gotchas.
- `skills/using-codex-cli/references/headless-details.md` — JSONL event shapes, review output format, config surface, session-management and misc subcommands.
