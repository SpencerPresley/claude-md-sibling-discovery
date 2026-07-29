# LLM Input Engineering

Two Claude Code skills for problems routinely misdiagnosed as “prompt
wording.”

- `prompt-engineering` makes the intended task easier to infer than plausible
  wrong tasks.
- `context-engineering` traces the compiler and state transformations that
  determine what the model actually receives.

The distinction matters because an application prompt is not just a string:

```text
source artifacts
  -> framework and middleware
  -> provider adapter
  -> inference-engine/model-package template
  -> rendered tokens
  -> decoder constraints
  -> parser and retry loop
```

Changing prose cannot repair an ignored adapter field, an invisible schema, an
engine-specific tool position, or a lossy history replacement.

## Install

```text
/plugin install llm-input-engineering@spencer-and-claude-sitting-in-a-tree
```

The skills remain model-visible and can also be invoked explicitly:

```text
/llm-input-engineering:prompt-engineering
/llm-input-engineering:context-engineering
```

Their descriptions are deliberately narrow to keep ordinary coding work outside
their intended trigger.

## What is different here

This is not a catalog of named prompting techniques or benchmark claims. The
skills require concrete artifacts:

- a boundary ledger for prompt decisions the model may confuse;
- a render card for the deployed model/package/engine/adapter stack;
- an explicit context transformation such as append, replace, spill, select,
  summarize, or mutate-schema-set;
- an honest retention claim: exact, verbatim-but-selected, code-derived,
  model-derived, or opaque;
- the earliest rendered token changed by cache-sensitive mutations.

[The Devstral case study](skills/context-engineering/references/devstral-langchain-case-study.md)
shows why this matters: the same model's embedded GGUF template and an Ollama
derived model place tools differently, while LangChain structured-output modes
put schema semantics on different control surfaces.

## Scope

The plugin can improve task inference and expose runtime mistakes. It cannot
make prompt injection safe, turn citations into entailment, make a summary
lossless, or prompt a model beyond its capability.
