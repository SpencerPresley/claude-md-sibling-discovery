# Case Study: Devstral, Ollama, and LangChain

This case demonstrates why model name and application prompt are insufficient
descriptions of model input.

The observations below were captured on 2026-07-29 using Ollama 0.31.1 and the
local model tag `devstral-small-2:24b`. Treat the excerpts as a versioned case,
not a claim about every package of these weights.

## Same weights, different tool placement

The embedded GGUF Jinja for
`Devstral-Small-2-24B-Instruct-2512` emits the tools block before iterating over
conversation messages:

```jinja2
{{- bos_token }}
... optional [SYSTEM_PROMPT] ...
{{- '[AVAILABLE_TOOLS]' + (tools | tojson) + '[/AVAILABLE_TOOLS]' }}
{% for message in loop_messages %}
  ...
{% endfor %}
```

Rendered order:

```text
BOS -> system -> tools -> conversation
```

An Ollama derived model for the same weights can override that template.
Inspect it:

```sh
ollama show devstral-small-2:24b --modelfile
```

The observed Go template found the final user index and emitted tools inside
that user branch, immediately before the user's `[INST]`:

```gotemplate
{{ if and (eq $lastUserIndex $index) $.Tools }}
[AVAILABLE_TOOLS]{{ $.Tools }}[/AVAILABLE_TOOLS]
{{ end }}
[INST]{{ .Content }}[/INST]
```

Rendered order:

```text
system / earlier conversation -> tools -> final user
```

The Ollama template does **not** put tools after the final user content. It puts
them after earlier history and before the final user instruction. This still
changes adjacency and the earliest token affected by formal tool mutation
relative to the GGUF template.

Neither template is “Devstral's universal template.” The running model package
and inference engine decide which is authoritative.

## LangChain structured output changes the schema channel

The following behavior was source-inspected with:

```text
langchain          1.3.1
langchain-core     1.4.0
langchain-ollama   1.1.0
```

At those versions:

- `create_agent(..., response_format=ToolStrategy(...))` appends synthetic
  output tools to the final tool list at model-call time and selects
  `tool_choice="any"` when structured-output tools exist.
- `ChatOllama.bind_tools(...)` converts tools to OpenAI-style schemas but
  explicitly ignores its `tool_choice` argument.
- `with_structured_output(..., method="function_calling")` uses a model-visible
  tool schema.
- `method="json_schema"` sends the JSON Schema through Ollama's `format=`
  decoder constraint.
- `method="json_mode"` sends `format="json"` without field semantics.

The observed Devstral Ollama template renders `.Tools`; it does not render the
`format` schema. Consequently:

```text
function_calling:
  schema descriptions can be model-visible through AVAILABLE_TOOLS

json_schema:
  schema constrains generation but descriptions are not automatically prompt text
```

Grammar-constrained output can make top-level prose impossible while leaving
field meaning under-specified. ToolStrategy can expose field descriptions while
failing to force tool selection if the downstream adapter ignores
`tool_choice`.

## What this changes operationally

Before editing prompt prose:

1. inspect the derived Ollama Modelfile;
2. capture the final LangChain request after middleware;
3. identify whether the schema is in `tools`, `format`, or prompt text;
4. render the effective message/tool order;
5. inspect the raw completion and retry/parser path.

The correct repair may be prompt text, a field description, adapter choice,
structured-output method, executor/parser behavior, or model selection.

## Reproduction and sources

GGUF template inspection:

```sh
uv run --with gguf python - <<'PY'
from gguf import GGUFReader

reader = GGUFReader("/absolute/path/model.gguf", "r")
print(reader.fields["tokenizer.chat_template"].contents())
PY
```

Implementation sources:

- [Ollama Modelfile reference](https://github.com/ollama/ollama/blob/main/docs/modelfile.mdx)
- [LangChain agent factory at the reviewed commit](https://github.com/langchain-ai/langchain/blob/a6612179da9626f46a1eea3ac04371e30719eb80/libs/langchain_v1/langchain/agents/factory.py)
- [LangChain Ollama adapter at the reviewed commit](https://github.com/langchain-ai/langchain/blob/a6612179da9626f46a1eea3ac04371e30719eb80/libs/partners/ollama/langchain_ollama/chat_models.py)

Re-run the inspection when the model package, engine, framework, or adapter
version changes.
