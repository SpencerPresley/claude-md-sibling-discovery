# Tools, Retrieval, and Memory

## Tool visibility is three contracts

1. **Model visibility:** rendered input describes the tool.
2. **Protocol admissibility:** template/decoder/parser can represent the call.
3. **Execution registration:** the harness can route and authorize the call.

A schema pasted into a tool result supplies visibility, not native parsing or
executor registration.

### Catalog architectures

| Architecture | Mechanism | Tradeoff |
| --- | --- | --- |
| Static formal catalog | bind the complete curated set once | native schemas and no discovery turn; recurring tokens and selection collisions |
| Formal dynamic reveal | mutate formal tools after routing/search | native visibility; changes rendered prefix and requires executor registration |
| Fixed dispatcher | stable search + generic executor | stable formal prefix and large pools; extra step and application-side validation |

A fixed dispatcher looks like:

```text
tool_search(query) -> matching names, descriptions, argument schemas
call_deferred_tool(tool_name, arguments) -> validate and execute active tool
```

Use formal reveal when it is early, coarse, and reused long enough to repay
re-prefill. Use a dispatcher when the pool is large/user-authored and the model
can follow indirection. Keep a static catalog when it already works.

### Tool-result transitions

| Mechanism | Retention claim |
| --- | --- |
| raw result | full returned content remains model-visible |
| spill + handle | exact external copy; model sees preview and retrieval path |
| deterministic truncate | predictable omission |
| extractive selection | selected spans verbatim; omission remains possible |
| abstractive summary | compact model-derived replacement |
| delete | deterministic loss |

Do not invisibly rewrite a committed result. If middleware intercepts before
commit, say that the visible result is a preview, where the original lives, and
how to retrieve it.

## Retrieval is a concrete selector

| Mechanism | Useful when | Characteristic miss |
| --- | --- | --- |
| metadata/key lookup | IDs, paths, time ranges, known fields | key absent or metadata wrong |
| BM25/lexical | identifiers, exact error text, rare terms | paraphrase shares few tokens |
| dense bi-encoder | semantic paraphrase | fine lexical distinction collapses |
| hybrid rank fusion | exact terms and paraphrase both matter | source absent from every candidate pool |
| cross-encoder reranker | top-k precision justifies model compute | relevant item absent from first-stage k |
| LLM reranker | nuanced, small candidate set | cost, variance, positional bias |
| agentic search | need changes after reading results | extra calls, loops, weak generated queries |

Reciprocal-rank fusion combines rankings without score calibration:

```text
score(document) = sum(1 / (k + rank_in_retriever))
```

It cannot recover a source absent from every list.

Index a small unit and return its parent when matching and comprehension need
different granularity. Preserve query, filters, candidate IDs/ranks, selected
spans, packed context, and raw completion to locate the miss.

If the model fails on a minimal input containing the exact evidence a human
would use, retrieval and packing are no longer the leading explanation.

## Memory and compaction are loss policies

| Mechanism | Retention | Boundary |
| --- | --- | --- |
| append-only log | committed entries exact | unbounded growth |
| sliding window | recent entries exact | old entries unavailable |
| spill + handle | external bytes can be exact | recovery requires surviving handle/tools |
| extractive handoff | selected spans verbatim | omission |
| abstractive handoff | model-derived belief state | omission/distortion/invention |
| typed application state | exact when code writes authoritative values | model extraction remains probabilistic |
| replay | re-derived from authority | latency and source drift |

There is no prompt that makes abstractive summarization deterministic. If a
later operation needs an exact ID, permission, version, or artifact, capture it
in code-owned state at the authoritative point and retain provenance.

Eviction can replace the current result before it enters history:

```text
tool result -> external raw storage -> preview + handle in transcript
```

Compaction replaces already committed history:

```text
prior transcript -> selector/summarizer -> replacement -> old input removed
```

Keeping the old transcript in an audit store does not expose it to the next
model call.

## Citations are not grounding

Code-assigned source IDs plus an enum constraint can establish that a citation
belongs to the supplied source set. Exact quote validation can establish
substring membership. Neither proves source truth, relevance, or entailment.

## Research starting points

- [Sentence-BERT](https://arxiv.org/abs/1908.10084)
- [Reciprocal rank fusion](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/)
- [BEIR](https://arxiv.org/abs/2104.08663)
- [Lost in the Middle](https://arxiv.org/abs/2307.03172)
- [RULER](https://arxiv.org/abs/2404.06654)
- [LLMLingua](https://arxiv.org/abs/2310.05736)

These establish mechanisms and tested limits, not portable thresholds or
compression ratios.
