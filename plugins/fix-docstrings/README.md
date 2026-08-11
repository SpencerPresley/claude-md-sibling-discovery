# fix-docstrings

Audits Python files for [Google-style](https://google.github.io/styleguide/pyguide.html) docstring compliance and fixes the violations — missing summaries, wrong section order, undocumented parameters, malformed `Args`/`Returns`/`Raises` sections.

Types are intentionally omitted from `Args` and `Returns`: they come from the function's annotations, and the IDE already surfaces the signature on hover. A type is only written into the docstring when the parameter or return value has no annotation — matching the Google style guide's own rule.

## How it works

- The `fix-docstrings` skill is the entry point. Point it at a file or directory; it scans every module, class, function, and method and applies the style reference inline.
- A hook (`hooks/scripts/langchain_tool_context.py`) adds the one conditional rule the skill body leaves out: **LangChain can parse a tool's Google-style `Args` section when `parse_docstring=True`.** Colon-bearing continuation entries such as `- mode:` can then be mistaken for argument names and make tool construction fail.

  Rather than carry that caveat in every run, the hook injects it only when it is relevant:

  1. When the skill is invoked — whether you type `/fix-docstrings` (a `UserPromptExpansion` hook) or the model invokes the skill itself (a `PostToolUse` hook on the `Skill` tool) — a fresh invocation generation is recorded. On `/fix-docstrings <target>`, the hook scans the target up front and lists files whose AST explicitly passes `parse_docstring=True` through a decorator or LangChain tool factory.
  2. For files the upfront scan cannot see, a `PostToolUse` hook on `Read` applies the same AST check. Aliased and re-exported decorators and `StructuredTool.from_function(..., parse_docstring=True)` are covered; the default `@tool` is intentionally ignored because parsing defaults to false.
  3. Each injected reminder contains the actual continuation-line hazard and the reference path, so it does not depend on an earlier reminder remaining in context. Files are deduplicated within one invocation, and `Stop`/`SessionEnd` disarm the hook afterward.

  When no tool enables docstring parsing, the reference is never loaded and the caveat never enters context.

## Usage

```
/fix-docstrings <file or directory path>
```

Or in conversation: "fix the docstrings in `src/tools/`".

For a directory it processes `__init__.py` files first, then modules, then tests (with lighter requirements), batching large directories and confirming before continuing.

## Layout

```
fix-docstrings/
  skills/fix-docstrings/
    SKILL.md                              # style reference + execution process
    references/langchain-tool-docstrings.md  # parser-safe rules (loaded by the hook)
  hooks/
    hooks.json
    scripts/langchain_tool_context.py     # detects @tool files, injects the reference
```

## Requirements

The hook runs on `python3` (standard library only) and is silent if it isn't present.
