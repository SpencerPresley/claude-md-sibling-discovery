# Adversarial Review Plugin — As-Built

> Built inline on 2026-05-24. This records the final design (it supersedes an earlier two-skill draft). Structural validation passed; the behavioral smoke test below is the only step that must be run by a human (it needs a plugin install + session restart).

**Goal:** A Claude Code plugin whose adversarial reviewer challenges a code change or a plan — surfacing the strongest reasons *not* to ship — and reviews **only the exact slice it is given**.

**Architecture:** One dual-mode subagent owns the adversarial persona as its system prompt (reliable stance, context isolation, tool-level read-only). One skill (`review`) is the sole entry point: it determines mode, pins the exact slice (mode-specific detail lives in progressively-disclosed reference files), captures intent, and dispatches via the Agent tool. The agent fetches and verifies the diff/plan itself in its own window. No hook — the skill is the door and the agent's input self-check is the backstop.

## Design decisions (locked)

- **One agent, dual-mode.** The adversarial *stance* is shared; `code` vs `plan` differ only in attack surface (two labeled sections).
- **One skill, not two.** Usage is prose-driven ("run the adversarial reviewer on the plan") → Claude invokes the skill and sets mode. The user's mental model is one reviewer + a mode; `/`-menu autocomplete (the only real two-skill perk) is moot for prose invocation.
- **Progressive disclosure for scope detail.** `SKILL.md` holds the shared flow; `code.md` / `plan.md` hold the mode-specific slice-pinning, `Read` only for the active mode.
- **Explicit slice, never a base-branch default.** Scope is one of: working tree / staged / a named commit / `A..B` range / specific files (code), or a plan file/section (plan). Modeled on the precision of the superpowers code-review request, with **no runtime dependency** on that plugin. The agent reviews exactly the slice and never widens.
- **Persona in the system prompt**, never in the skill template. The template is task scaffold only (mode + slice + how-to-see-it + intent + focus).
- **Read-only enforced at the tool level** (`tools: [Read, Grep, Glob, Bash]`).
- **No hook in v1.** The agent's "Input contract" self-check turns a stray/thin dispatch into a graceful "tell me the scope" bounce.

## Files (as built)

```
plugins/adversarial-review/
├── .claude-plugin/plugin.json          # manifest (name, description, version, author)
├── agents/adversarial-reviewer.md      # persona system prompt; mode/scope contract; read-only tools; opus/high
├── skills/adversarial-review/          # skill name matches the plugin → invoked as /adversarial-review
│   ├── SKILL.md                        # shared flow: determine mode + intent → route to mode file → dispatch → relay
│   ├── code.md                         # pin the exact diff slice + command (working tree/staged/commit/range/files)
│   └── plan.md                         # pin the exact plan/section
└── README.md
```
Also: registered in repo-root `.claude-plugin/marketplace.json`; added to repo-root `README.md` table.

## Verification

**Structural (done, passing):**
- `jq -e . plugins/adversarial-review/.claude-plugin/plugin.json` → OK
- `jq -e . .claude-plugin/marketplace.json` → OK; `adversarial-review` entry present, `source` resolves to an existing dir
- Agent frontmatter has `name/description/model/effort/tools`; skill frontmatter has `name/description/argument-hint`
- `SKILL.md` references `${CLAUDE_SKILL_DIR}/code.md` and `/plan.md`, both present

**Behavioral smoke test (must be run by a human — needs install + restart):**

- [ ] Install + restart:
  ```text
  /plugin marketplace add SpencerPresley/everyday-engineering-skills
  /plugin install adversarial-review@everyday-engineering-skills
  ```
  Restart the session. Confirm via `/agents` that `adversarial-reviewer` is registered and `/adversarial-review` exists (matching how your `hack-skills-router` resolves to `/hack-skills-router`).
- [ ] **Code mode, explicit slice:** make a small deliberately-flawed edit (e.g., drop a null check), then say *"adversarially review my working tree changes."* Expect: the skill reads `code.md`, pins the working-tree slice, dispatches; the agent returns a **Verdict** line + prioritized findings with `path:line` and confidence, proposes no edits, and stays within the slice.
- [ ] **Slice narrowing:** with two unrelated edits staged, say *"review only `<one file>`."* Expect: findings about that file only; anything else appears at most under an "Out of scope" line.
- [ ] **Missing-scope bounce:** `@`-mention the agent directly with a vague prompt. Expect: it returns a short request for mode + slice + intent instead of reviewing.
- [ ] **Plan mode:** *"run the adversarial reviewer on `docs/superpowers/plans/2026-05-24-adversarial-review-plugin.md`."* Expect: approach/assumption/sequencing challenges, not line nits.
- [ ] If the agent reviews instead of bouncing in the missing-scope case, strengthen "Input contract"; if findings feel soft, strengthen "Operating stance".
