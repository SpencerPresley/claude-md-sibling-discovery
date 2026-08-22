# Everyday Engineering Skills

Agent Skills, Claude Code plugins, and hooks that each solve one specific
engineering problem. Small enough to actually use, sharp enough to actually
help.

## Installation

### Claude Code plugins

```text
/plugin marketplace add SpencerPresley/everyday-engineering-skills
```

Then install individual plugins:

```text
/plugin install <plugin-name>@everyday-engineering-skills
```

### Agent skills

The standalone skills can also be installed with the
[Vercel Skills CLI](https://github.com/vercel-labs/skills) using the GitHub
`owner/repo` shorthand:

```sh
# Prompt and context engineering are designed to be installed together.
npx skills add SpencerPresley/everyday-engineering-skills --skill context-engineering prompt-engineering

# The core docstring skill, without the Claude Code plugin's hook.
npx skills add SpencerPresley/everyday-engineering-skills --skill fix-docstrings
```

Add `--global` to install for your user instead of the current project, or list
the available skills before installing:

```sh
npx skills add SpencerPresley/everyday-engineering-skills --list
```

## Plugins

| Plugin | What it does |
|--------|-------------|
| [claude-md-discovery-extended](plugins/claude-md-discovery-extended/) | Auto-discovers and loads CLAUDE.md files from any directory outside your project tree when the model accesses files there. |
| [codex-context-loader](plugins/codex-context-loader/) | Injects a detailed Codex-plugin briefing into your session — but only when the Codex plugin is actually enabled, so it costs zero context tokens when you're not using Codex. |
| [adversarial-review](plugins/adversarial-review/) | Adversarial code/plan reviewer that uses a Codex-style review contract while reviewing only the exact slice you name. |
| [fix-docstrings](plugins/fix-docstrings/) | Audits Python files for Google-style docstring compliance and fixes violations. A hook injects the extra continuation-line rule only when a LangChain tool explicitly enables docstring parsing. |
| [llm-input-engineering](plugins/llm-input-engineering/) | Designs and diagnoses prompts as compiled model input: rendered chat templates, tool/schema placement, structured decoding, prefix reuse, retrieval, and lossy context transitions. |
| [pyrefly-lsp](plugins/pyrefly-lsp/) | Python code intelligence for Claude Code backed by pinned Pyrefly. Adapts Claude's LSP initialization and uses blocking workspace indexing so the first cross-file result is complete; needs only `uv` on PATH. |

## License

MIT
