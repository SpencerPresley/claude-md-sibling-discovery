# Tools and Structured Output

Tool calling and structured output can begin from the same JSON Schema while
using different model-visible and enforced channels.

## Locate the schema channel

| Mechanism | Model may see | Enforced |
| --- | --- | --- |
| Native tool calling | template-rendered tool schema | provider/parser-specific tool-call shape |
| Synthetic output tool | response schema added to tool catalog | tool-shaped answer parsed as output |
| Grammar-constrained schema | sometimes no descriptive schema text | allowed token language/shape |
| JSON mode | often only a JSON decoding constraint | JSON syntax |
| Prompt-only format | instruction and examples | application parser, if any |
| Hosted structured output | provider-specific and partly opaque | provider-specific schema subset |

Inspect the final adapter payload and rendered template. A Pydantic model in
application code does not establish schema visibility.

## Tool definitions are instruction surfaces

The model experiences the rendered name, description, argument names/types,
enums, defaults, descriptions, and call grammar—not the Python function.

Encode a selection boundary:

```text
resolve_indicator
Use when the input is already a normalized IP, domain, URL, or hash and current
enrichment is needed. Do not use to extract indicators from a document; use
extract_indicators first.
```

“Resolves an indicator” adds nothing to the name.

For arguments:

- prefer domain names such as `indicator`, `sha256`, and `case_id` over
  `value` or `data`;
- represent mutually exclusive modes in the schema when possible;
- remove choices the model cannot make from available information;
- split tools whose schema contains unrelated decisions;
- merge tools when their distinction is artificial and repeatedly misselected.

Put cross-catalog behavior in global instructions. Keep local selection and
argument semantics in the tool definition so they travel with the schema.

## Use the real tool protocol in examples

A tool example is:

1. user-role request;
2. assistant-role native tool call;
3. tool-role result with correct name and call ID;
4. assistant continuation.

Compile it through the target template. ChatML, Mistral, Hermes, and Harmony
transcripts are not interchangeable prose conventions.

## Separate visible semantics from grammar

Constrained decoding guarantees only what the grammar represents. It can
require an integer or URL-shaped string without making that value justified.
Property names and enum values still act as generated instruction tokens.

If field descriptions are not rendered, put only the required field semantics
in visible prompt text; do not blindly duplicate the entire JSON Schema.

Some open models reason poorly while simultaneously satisfying a strict output
grammar. A two-pass design can separate analysis from constrained
transformation, at the cost of another generation and possible error
propagation. This is a model/task branch, not a default.

## Citations without pretending

To prevent invented source identities:

1. assign source IDs in code;
2. expose only those IDs;
3. constrain `source_id` to that set;
4. resolve IDs outside the model.

This proves set membership, not source truth, relevance, or entailment. An
exact quote can be checked for substring membership; that still does not prove
the associated claim.

## Retry loops change the system

Inspect the exact validation error, whether invalid output remains in history,
retry count, and whether a synthetic output tool competes with real tools. A
prompt that succeeds after hidden retries is a different system from one that
produces a valid result in one decode.

## Implementation sources

- [Hugging Face chat templates](https://huggingface.co/docs/transformers/chat_templating)
- [Writing Hugging Face templates](https://huggingface.co/docs/transformers/en/chat_templating_writing)
- [llama.cpp function calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)
- [LangChain agent factory at the reviewed commit](https://github.com/langchain-ai/langchain/blob/a6612179da9626f46a1eea3ac04371e30719eb80/libs/langchain_v1/langchain/agents/factory.py)
- [LangChain Ollama adapter at the reviewed commit](https://github.com/langchain-ai/langchain/blob/a6612179da9626f46a1eea3ac04371e30719eb80/libs/partners/ollama/langchain_ollama/chat_models.py)

Recheck the deployed versions; adapter behavior can change without model
weights changing.
