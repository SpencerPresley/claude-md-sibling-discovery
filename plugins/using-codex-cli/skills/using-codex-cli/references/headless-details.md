# Codex CLI headless details

Verified against codex-cli 0.149.1 unless marked otherwise.

## `--json` event stream (verified by execution)

JSONL on stdout, one event per line:

```json
{"type":"thread.started","thread_id":"01a03df5-da92-7cf1-b2ca-2bb813828abd"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"..."}}
{"type":"turn.completed","usage":{"input_tokens":18333,"cached_input_tokens":9984,"cache_write_input_tokens":0,"output_tokens":6,"reasoning_output_tokens":0}}
```

- Capture `thread_id` from `thread.started` to target `codex exec resume <thread_id>` or `codex exec fork <thread_id>` later.
- The final answer is the last `item.completed` with `item.type == "agent_message"`.
- Even a trivial prompt costs ~20k input tokens (system prompt + repo context) — don't script chatty loops of tiny exec calls; batch into one prompt or resume a session.

## Review output shape (verified by execution)

`codex exec review --uncommitted` prints prose findings (stdout and `-o` file), priority-tagged with file/line:

```
- [P1] Remove the unconditional offset from `avg` — /path/stats.py:2-2
  For every non-empty input, this returns the arithmetic mean plus one; ...
```

No JSON schema for review findings at this version — parse the `[P0-3]` prose or keep it human-read.
`--title <t>` labels the review summary; `-m` overrides the review model.

Custom prompt with **no** scope flag = model-determined scope (verified probe: it reviewed both the
HEAD commit and an untracked file). When you need custom focus, state the scope inside the prompt
("Review only the uncommitted changes; focus on error handling") and accept that it's honored, not
enforced; only the scope flags guarantee scope — and they forbid a custom prompt.

`-o` and `--json` are declared `global = true` in exec's clap definition (codex-rs/exec/src/cli.rs),
so they apply identically to `exec resume`, `exec fork`, and `exec review`.

## Config and model selection

- `-c key=value` — override any `~/.codex/config.toml` key; value parsed as TOML, dotted paths for nesting (`-c 'sandbox_workspace_write.network_access=true'`).
- `-p <profile>` — layer `$CODEX_HOME/<name>.config.toml` on top of base config.
- `-m <model>` — model override. `--oss --local-provider lmstudio|ollama` for local models.
- `--enable <feature>` / `--disable <feature>`; `codex features` lists flags and their stability.
- `--ignore-user-config` (skip config.toml, keep auth), `--ignore-rules` (skip execpolicy `.rules`), `--strict-config` (error on unknown keys).
- `-i <file>` attaches images to the prompt.

## Session management beyond `exec resume`

| Command | Purpose |
|---|---|
| `codex resume` / `codex fork` | Interactive (TUI) counterparts — picker UI; not for agents |
| `codex queue --thread <uuid\|name> --message <text>` | Queue a message for an existing session |
| `codex agents` | Browse sessions on the shared app-server daemon (TUI) |
| `codex archive` / `unarchive` / `delete <id>` | Session lifecycle |
| `codex apply <task_id>` | `git apply` the latest diff a Codex agent produced |
| `codex cloud exec\|status\|list\|diff\|apply` | Codex Cloud tasks (experimental) |

## Other surface (one-liners; `codex <cmd> --help` for detail)

- `codex sandbox <cmd>...` — run an arbitrary command under Codex's seatbelt sandbox.
- `codex mcp` — manage MCP servers Codex can call; `codex mcp-server` — expose Codex itself as an MCP server (stdio).
- `codex login --with-api-key` (reads key from stdin), `codex login status`, `codex logout`.
- `codex doctor [--json]` — install/config/auth/runtime health; `codex update`.
- `codex completion <shell>` — shell completions.

## Auth note

`codex login status` prints e.g. `Logged in using ChatGPT`. ChatGPT-plan auth draws from the plan's usage quota; API-key auth bills per token. Preflight with `login status` before scripted runs — an unauthenticated run fails rather than prompting usefully in headless mode (failure mode not exercised; inferred from headless never-prompt policy).
