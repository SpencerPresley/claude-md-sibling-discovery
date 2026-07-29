# spencer-and-claude-sitting-in-a-tree

Focused Claude Code plugins that each solve one specific problem. Simple but powerful, like how you feel when you're sitting high up in a tree with Claude and y'all are... well, ya know. Small enough to actually use, sharp enough to actually help.

## Installation

```text
/plugin marketplace add SpencerPresley/spencer-and-claude-sitting-in-a-tree
```

Then install individual plugins:

```text
/plugin install <plugin-name>@spencer-and-claude-sitting-in-a-tree
```

## Plugins

| Plugin | What it does |
|--------|-------------|
| [claude-md-discovery-extended](plugins/claude-md-discovery-extended/) | Auto-discovers and loads CLAUDE.md files from any directory outside your project tree when the model accesses files there. |
| [codex-context-loader](plugins/codex-context-loader/) | Injects a detailed Codex-plugin briefing into your session — but only when the Codex plugin is actually enabled, so it costs zero context tokens when you're not using Codex. |
| [adversarial-review](plugins/adversarial-review/) | Adversarial code/plan reviewer that uses a Codex-style review contract while reviewing only the exact slice you name. |
| [fix-docstrings](plugins/fix-docstrings/) | Audits Python files for Google-style docstring compliance and fixes violations. A hook injects parser-safe rules just-in-time when the files being fixed define LangChain `@tool` functions, so the skill stays lean for the common case. |
| [llm-input-engineering](plugins/llm-input-engineering/) | Designs and diagnoses prompts as compiled model input: rendered chat templates, tool/schema placement, structured decoding, prefix reuse, retrieval, and lossy context transitions. |

## License

MIT
