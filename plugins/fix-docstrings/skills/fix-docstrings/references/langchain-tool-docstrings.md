# LangChain Parsed Tool Docstrings

Apply these rules only when LangChain is asked to parse a function's Google-style
docstring, for example:

- `@tool(parse_docstring=True)` (including imported aliases or re-exports)
- `StructuredTool.from_function(fn, parse_docstring=True)`
- a call that passes `parse_docstring=True` through to
  `create_schema_from_function`

Both `@tool` and `StructuredTool.from_function` default to
`parse_docstring=False`. A default `@tool` therefore does not need this special
handling.

## What LangChain actually parses

LangChain turns entries in `Args` into schema descriptions and validates the
parsed names against the function signature.

In particular, parenthesized types are accepted: `query (str): ...` is parsed as the argument
`query`, not `query (str)`. Keep following the base fix-docstrings style rule:
omit a type when the signature is annotated and include it when the annotation
is missing. There is no additional LangChain rule forbidding `(type)`.

The parser-specific hazard is a colon-bearing continuation line under an
argument. LangChain can interpret that continuation as another argument name;
tool construction then fails because the invented name is absent from the
function signature.

### Unsafe

```python
@tool(parse_docstring=True)
def process_data(mode: str, limit: int = 10) -> dict:
    """Process data with the specified mode.

    Args:
        mode: The processing mode.
            - fast: Skip validation.
            - strict: Perform full validation.
        limit: Maximum number of results.
    """
```

The nested lines can be parsed as arguments named `- fast` and `- strict`.

### Safe

```python
@tool(parse_docstring=True)
def process_data(mode: str, limit: int = 10) -> dict:
    """Process data with the specified mode.

    Args:
        mode: The processing mode. Use "fast" to skip validation or
            "strict" to perform full validation.
        limit: Maximum number of results. Defaults to 10.
    """
```

Keep continuation lines as prose belonging to the current argument. Rewrite
nested fields, bullets, or table rows only when their colon-bearing shape can be
mistaken for a new `name: description` entry; rich formatting is not itself a
schema-corruption mechanism.
