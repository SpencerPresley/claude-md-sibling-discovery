# tests

Tests for this repo's plugin hooks.

- **`test-langchain-tool-hook.sh`** — deterministic assertions for the
  `fix-docstrings` LangChain hook (no live model). Feeds crafted payloads and
  checks the injected context: the `UserPromptExpansion` upfront scan of a
  file/directory target lists exactly the `@tool` files, pre-seeded files stay
  silent on `Read`, and the Read-detector fallback is graduated (FULL → LIGHT →
  silent-on-re-read). Run it directly; exits non-zero on any failure.
- **`test_llm_input_engineering.py`** — contract checks for the public
  `llm-input-engineering` plugin: marketplace registration, narrow skill
  triggers, portable content, working relative links, and the exact
  engine-specific Devstral ordering recorded by the case study.
- **`run-hook-capture-test.sh`** — instrumentation for discovering the exact
  stdin payloads Claude Code hands to hook events, used to validate the hook
  design against reality instead of guessing undocumented fields.

## Capture harness

```bash
tests/run-hook-capture-test.sh
```

Two headless `claude -p` scenarios (haiku, low effort) exercise both ways a skill
gets activated. Hooks are loaded only for the run via
`--settings .claude/hooks.json` (Claude Code does **not** auto-load
`.claude/hooks.json` — only `settings.json` / `settings.local.json` — so this
config stays inert in normal sessions). Captured payloads land in
`tests/outputs/` (gitignored).

Pieces:
- `.claude/hooks.json` — hooks-only settings file; `tests/capture-hook-input.py`
  records each payload. The `UserPromptExpansion` matcher is empty on purpose so
  it fires on every slash command and reveals the real `command_name`.
- `.claude/skills/internal-plugin-testing/` — a minimal project skill that reads
  `scripts/hello.py` (to fire `PostToolUse[Read]`) and prints a canary.

## What it confirmed

| Activation | `UserPromptExpansion` | `PostToolUse[Skill]` | `PostToolUse[Read]` |
|---|---|---|---|
| `/skill` typed manually | ✅ fires | ❌ does **not** fire | ✅ fires |
| Model invokes the skill | ❌ does not fire | ✅ fires | ✅ fires |

- `UserPromptExpansion.command_name` depends on where the skill lives, and this
  bit us:
  - **project** skill (`command_source: projectSettings`) → **bare** name
    (`internal-plugin-testing`).
  - **plugin** skill (`command_source: plugin`) → **namespaced** `plugin:skill`,
    e.g. `fix-docstrings:fix-docstrings`. (The docs example showing a bare plugin
    `command_name` is misleading — installed plugins namespace it.)
- `command_args` holds the rest of the prompt; `cwd` is present (used by the
  upfront directory scan to resolve the typed target).
- `PostToolUse[Skill].tool_input.skill` carries the skill name; `[Read]`'s
  `tool_input.file_path` is an **absolute** path.

### Matcher semantics (verified by probe)

A hook `matcher` is a **`re.fullmatch` regex against the whole `command_name`**,
not a substring test (empty string `""` is special-cased to match everything):

| matcher | `fix-docstrings:fix-docstrings` |
|---|---|
| `fix-docstrings` | ❌ (not a full match) |
| `^fix-docstrings$` | ❌ |
| `fix-docstrings:fix-docstrings` | ✅ |
| `fix-.*` / `.*fix-docstrings.*` | ✅ |

So `fix-docstrings` needs **both** a `UserPromptExpansion` hook (manual
`/fix-docstrings` — namespaced command, so the matcher must be
`.*fix-docstrings.*`, **not** `fix-docstrings`) **and** a `PostToolUse[Skill]`
hook (model invocation, matched on the tool name `Skill`). Neither path covers
the other. The original `fix-docstrings` matcher silently never fired for the
installed plugin; only an end-to-end run against the installed copy caught it.
