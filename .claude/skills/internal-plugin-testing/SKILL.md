---
name: internal-plugin-testing
description: Use when running the internal hook-input capture test for this repo's plugins — exercises slash-command expansion, Skill-tool invocation, and the Read tool so the capture hooks record their payloads.
disable-model-invokation: true
---

# Internal Plugin Testing

This skill exists only to drive the hook-input capture test in `tests/`. Sentinel for confirming activation: the canary string is BLUE-OTTER-42.

When this skill is invoked, do exactly the following, then stop:

1. Read the file `.claude/skills/internal-plugin-testing/scripts/hello.py` using the Read tool. This deliberately triggers the `PostToolUse` capture hook on `Read`.
2. Reply with one short line that (a) confirms the skill was invoked, (b) states the canary string above, and (c) states the single top-level value printed by the file you read.

Do not do anything else. Do not edit files. Do not explore the repo.
