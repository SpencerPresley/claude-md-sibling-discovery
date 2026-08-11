---
name: prompt-engineering
description: Use when drafting, revising, or diagnosing an LLM system prompt, message layout, tool description, tool schema, or structured-output contract.
---

# Prompt Engineering

Do not fill a generic prompt template. Make the intended task easier to infer
than the plausible wrong tasks.

## Locate the target

For a deployed system, identify the model/package, inference engine, framework
adapter, effective chat template, tool/schema render points, decoder
constraints, and parser. If rendering, template selection, or prefix-cache
behavior is part of the problem, use the `context-engineering` skill to
establish the effective rendered input. If that skill is unavailable, inspect
the model package, inference engine, framework adapter, effective chat template,
rendered segment order, decoder constraints, and output parser directly before
proceeding.

If the user wants a standalone prompt and no target exists, state the assumed
model class. Do not invent a harness.

## Build a boundary ledger

Before writing prose, list decisions the model can plausibly get wrong:

```text
must distinguish <A> from <B>
must choose <X> when <condition>, otherwise <Y>
must treat <value> as <meaning>, not <plausible alternate>
```

Spend prompt space on the separators. Boilerplate such as “be an expert,”
“think carefully,” and “produce high-quality work” supplies no decision rule.

Put semantics on the surface nearest the decision:

| Decision | Likely surface |
| --- | --- |
| Stable run behavior | system/developer instruction |
| Current task and supplied facts | user message |
| Why to choose one tool over another | tool description |
| Argument meaning and valid combinations | parameter schema |
| Output-field meaning | visible field descriptions or prompt text |
| JSON shape/token language | decoder constraint |
| Permissions, validation, irreversible policy | application code |

“Likely” is deliberate. Confirm rendered order before relying on adjacency,
role authority, or prefix stability.

## Compose the instruction

1. Name the requested artifact in its consumer's vocabulary.
2. Encode the high-entropy boundaries and real precedence rules.
3. Put variable data in semantic containers. Nested XML is a strong default for
   scoped natural-language regions; the target model's trained idiom wins.
4. Add examples only when they resolve a boundary prose does not. Prefer a
   contrastive pair over several average examples.
5. Put output semantics where the model can see them. A decoder grammar may
   expose shape without descriptions.
6. Remove accidental duplication across prompt, schema, and tool descriptions.

A run of same-level `# Objective`, `# Inputs`, `# Rules`, `# Tools`, and
`# Output` headings is not prompt architecture.

Read [instruction design](references/instruction-design.md) for semantic
structure and examples. Read
[tools and structured output](references/tools-and-structured-output.md) before
changing tool policy, schemas, citations, or constrained decoding.

## Inspect the compiled artifact

For a deployed prompt, render the actual sequence and ask:

- Did framework conversion preserve the intended role?
- Where did native tools and response schemas land?
- Is the schema visible text, a synthetic tool, or only a decoder constraint?
- Did middleware inject, replace, or duplicate instructions?
- Did the source prompt manually add control tokens the template already owns?
- Is task data still distinguishable from instructions after rendering?

Fix the owning layer. Do not add prose to compensate for an ignored
`tool_choice`, invisible schema, parser retry loop, or wrong chat template.

## Return the artifact

Provide the exact messages/schema edits, the observed or assumed placement, the
boundaries encoded, and the remaining model- or engine-dependent behavior.

Small contrastive probes can falsify a wording or placement idea. Do not replace
the requested prompt with an eval program or enter a rewrite loop when the
remaining failure belongs to model capability or application code.
