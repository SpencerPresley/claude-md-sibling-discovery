---
name: context-engineering
description: Use when designing or diagnosing how an LLM application assembles, renders, mutates, retrieves, caches, evicts, or compacts model-visible context.
---

# Context Engineering

Treat context as the output of a compiler plus a sequence of state
transformations. A prompt string, `messages` array, model card, or advertised
context length is not the token stream.

## Draw the render card

Fill this from source or live inspection:

```text
weights/model:
model package:
inference engine and version:
framework and adapter:
effective template and override source:
rendered segment order:
decoder constraints:
output parser and retry behavior:
per-turn mutations:
persistent state outside the transcript:
prefix-cache boundary and observability:
opaque layers:
```

“Uses Devstral,” “OpenAI-compatible,” and “uses LangChain” are not render
descriptions. Read [rendering and cache](references/rendering-and-cache.md) and
the [Devstral/LangChain case study](references/devstral-langchain-case-study.md)
when the stack is unclear.

## Name the transformation

| Operation | Required detail |
| --- | --- |
| append | segment, producer, insertion point |
| replace | old/new segment and earliest changed token |
| delete/window | history made unavailable |
| spill | external location and model-visible replacement |
| retrieve/select | candidate source, selector, omission boundary |
| summarize | source span, derived representation, lost guarantees |
| mutate schema set | old/new formal schemas and render point |

If a provider transform cannot be inspected, label it opaque.

## Choose the retention guarantee

- Use an append-only transcript when exact conversational provenance matters
  and growth is affordable.
- Put exact values in code-owned state when later correctness depends on them.
- Spill an artifact intact and leave a visible, usable handle when exact
  recovery may be needed.
- Select verbatim spans when omission is acceptable but paraphrase is not.
- Use an abstractive summary only when a lossy model-produced belief state is
  acceptable.
- Replay authoritative artifacts when recomputation is affordable.

These guarantees do not combine upward. A summary plus a pointer remains lossy
until something follows the pointer. A typed value extracted by a model remains
model-derived.

Read [tools, retrieval, and memory](references/tools-retrieval-and-memory.md)
before changing formal tool visibility, tool results, retrieval, eviction, or
compaction.

## Treat layout as behavior

Rendered order controls adjacency, context position, and reusable prefix
length. Before moving or dynamically changing a segment, find the earliest
rendered token that can change. Block granularity may force cache reuse to end
even earlier.

Do not call a mutation “cache-stable” merely because the API objects look
similar. Do not call it “cache-busting” as though every earlier token is lost.
Measure the running engine's prefill/cache signal.

## Diagnose the owning layer

Use the smallest counterfactual that separates causes:

- render the same payload through two suspected templates/adapters;
- move one discriminating fact between controlled positions;
- compare fixed and changed formal tool sets;
- give the model a minimal input containing the exact evidence a human would
  use;
- compare raw completion with parsed output.

If the minimal evidence condition still fails, retrieval and packing are no
longer the leading explanation. If an adapter ignores a control field, system
prose does not restore it.

## Report honestly

Return the render card, transformation and owner, model-visible versus external
state, retention guarantee, earliest-token/cache consequence, and opaque or
model-dependent behavior.

Do not claim that a summary deterministically preserves a checklist, that a
citation proves entailment, or that delimiters secure retrieved instructions.
