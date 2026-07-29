# Rendering and Prefix Reuse

## Trace the compiler

```text
prompt/state artifacts
  -> framework and middleware transformations
  -> provider-adapter payload
  -> inference-engine/model-package template
  -> rendered tokens
  -> decoder constraints
  -> output parser/retry loop
```

The model input is produced through the rendered-token layer. Decoder and
parser behavior then determine what can be generated and accepted.

For hosted providers, preserve the wire payload and label server-side rendering
opaque. API object order does not prove token order.

## Inspect the effective template

### Ollama

Inspect the derived model, not only its base:

```sh
ollama show MODEL --modelfile
ollama show MODEL --template
```

Record `messages`, `tools`, `format`, raw/template mode, and parameters sent by
the client.

### GGUF

```sh
uv run --with gguf python - <<'PY'
from gguf import GGUFReader

reader = GGUFReader("/absolute/path/model.gguf", "r")
print(reader.fields["tokenizer.chat_template"].contents())
PY
```

This is package metadata, not proof the server selected it.

### llama.cpp

Inspect the live `/props` response and launch arguments. Explicit
chat-template flags can supersede metadata. Record slot/cache settings for
prefix work.

### Transformers

```python
rendered = tokenizer.apply_chat_template(
    messages,
    tools=tools,
    tokenize=False,
    add_generation_prompt=True,
)
```

Render with tokenization enabled for exact boundaries. This represents the
deployment only when its tokenizer, template, arguments, and special-token
policy match.

### Framework adapter

Trace the request after middleware:

- Were tools appended, filtered, or converted to synthetic output tools?
- Did `tool_choice` reach the provider?
- Did structured output become a tool, visible schema text, or `format=`?
- Did parsing failure create another rendered turn?

## Reason from the first changed token

For two rendered requests:

```text
request A: [ common token prefix ][ old suffix ]
request B: [ common token prefix ][ new suffix ]
                                 ^
                          first changed token
```

An engine can reuse only a prefix ending no later than that point; cache-block
granularity may force reuse to end earlier.

| Mutation | Likely prefix consequence |
| --- | --- |
| append turn | old request can remain a prefix |
| replace current result before commit | prior transcript can remain a prefix |
| rewrite old message | reuse ends inside that message |
| rebuild mutable system text | reuse ends near the beginning |
| change formal `tools=` | reuse ends where the template renders tools |
| change grammar only | prompt may stay stable; decoder/cache behavior is engine-specific |

Append-only does not mean free: appended tokens still require prefill and the
cache may be evicted or assigned to another slot.

## Measure the deployment

Compare:

1. cold request;
2. identical repeat;
3. append-only growth;
4. proposed mutation;
5. identical repeat after mutation.

Hold model, process, sampler, context length, slot policy, and concurrency
constant. Warm-up and ordering contaminate short tests.

Use the engine metric that reports prefill or reused tokens. In the documented
Ollama case study, `prompt_eval_duration` was informative;
`prompt_eval_count` reported logical prompt size rather than reuse.

## Sources

- [Ollama Modelfile](https://github.com/ollama/ollama/blob/main/docs/modelfile.mdx)
- [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [SGLang/RadixAttention](https://arxiv.org/abs/2312.07104)
- [vLLM automatic prefix caching](https://docs.vllm.ai/en/latest/design/prefix_caching/)
