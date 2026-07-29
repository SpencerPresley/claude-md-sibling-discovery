# Instruction Design

The useful design question is:

> What task might the model infer, and what signal makes the intended task less
> ambiguous than each plausible alternative?

## Boundary ledger

Sketch this before writing the prompt:

| Decision | Plausible wrong inference | Separating signal | Surface |
| --- | --- | --- | --- |
| fact vs hypothesis | domain association counts as evidence | define the evidence predicate | instruction or field semantics |
| no match vs missing data | absence was established | name the observed scope | current task |
| search vs answer | every question warrants a tool | state the information need | global/tool policy |
| two output fields | both request the same summary | give each a distinct consumer | schema and prompt |

The ledger is design work, not a template to paste into the prompt.

## Define an artifact, not a persona

A role is useful when it selects a real standard, vocabulary, audience, or
scope:

```xml
<analytical_standard>
Assess the indicator as an incident responder deciding what an analyst should
verify next. Separate supplied observations from threat-intelligence
hypotheses.
</analytical_standard>
```

“You are a world-class expert” supplies style without a decision rule.

## Use semantic structure

```xml
<task>
For each <candidate_claim>, classify its relationship to
<packet_observations>.
</task>

<evidence_policy>
  <supported>Explicitly established by the supplied observations.</supported>
  <inferred>Supported by named observations but not directly stated.</inferred>
  <unresolved>Requires evidence absent from the supplied observations.</unresolved>
</evidence_policy>

<packet_observations>
...
</packet_observations>
```

Tag names carry semantics and nesting carries scope. Tags do not create
authority or security. Use Markdown or a model-native idiom when its training
format makes that a better fit.

Do not manually add `[INST]`, `<|assistant|>`, `[AVAILABLE_TOOLS]`, or similar
control tokens to ordinary messages. The deployed chat template owns them.

## Use examples to disambiguate

Examples also teach label vocabulary, input distribution, output register,
ordering, and shortcuts. Prefer examples on a contested boundary:

- one changed fact flips the correct class;
- an ambiguous case remains unresolved;
- an available tool is inappropriate;
- an empty result is valid rather than a failed lookup.

Render tool examples through the real message roles and tool-call protocol. A
prose sentence saying “the assistant called X” is not equivalent to native
tool-call and tool-result messages.

Example order can change behavior and may not transfer between models. Preserve
material ordering as part of the prompt version.

## Resolve collisions

Common collisions include:

- “use only supplied facts” versus “use domain knowledge”;
- “never ask questions” versus “do not assume missing values”;
- “be concise” versus “be comprehensive”;
- “always use tools” versus “avoid unnecessary calls.”

State the boundary:

```xml
Use domain knowledge to propose hypotheses and next checks. Do not present a
domain association as observed unless the supplied record states it.
```

Repeating both sides in uppercase does not resolve the conflict.

## Give fields different jobs

Weak:

```text
analysis: analytical observations
detailed_assessment: detailed analytical assessment
```

Distinct:

```text
observations: supplied facts that affect the decision
hypotheses: interpretations plus missing confirming evidence
actions: checks the consumer can perform next
```

If the product requires overlapping fields, partition them explicitly or merge
them. Prompting cannot maintain a distinction the schema does not express.

## Research that informs these mechanisms

- [Prompt-format sensitivity](https://arxiv.org/abs/2310.11324) shows that
  meaning-preserving formatting changes can have large, model-specific effects.
- [The language of prompting](https://aclanthology.org/2023.findings-emnlp.618/)
  reports poor transfer of prompt phrasings across models and datasets.
- [Rethinking demonstrations](https://arxiv.org/abs/2202.12837) shows that
  examples communicate label space, distribution, and format—not only labels.
- [Few-shot order sensitivity](https://arxiv.org/abs/2104.08786) shows why
  example order belongs to the versioned artifact.

Use the mechanisms, not the papers' benchmark percentages.
