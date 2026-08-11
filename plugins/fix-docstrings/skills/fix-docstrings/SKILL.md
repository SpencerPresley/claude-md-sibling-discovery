---
name: fix-docstrings
description: Use when Python docstrings need to follow Google style — audits modules, classes, functions, and methods and fixes formatting violations.
argument-hint: <file or directory path>
---

# Fix Docstrings

Scan the target for Google-style docstring violations and fix them. Review the Style Reference below, read the target files, then check every module, class, function, and method.

## Target

$ARGUMENTS

## Style Reference: Google Style Docstrings

### General structure

```python
"""Short one-line summary ending in a period.

Longer description that can span multiple lines. Explains the purpose
and documents any important behavior or side effects.

Args:
    param_name: Description of the parameter. If it is too long to
        fit on one line, continue with a hanging indent.
    another_param: Another parameter description.

Returns:
    Description of the return value.

Raises:
    ValueError: When this exception is raised.
"""
```

### Sections

- **Args** — `param_name: description`. Omit the type; it comes from the annotation. Add `(type)` only when the parameter has no annotation. Continuation lines use a 4-space hanging indent (not alignment to the description). Mention default values in the description.
- **Returns** — `description` only: no type prefix, no variable name. The type comes from the return annotation; add it only when the annotation doesn't convey it. Document the structure of tuple returns.
- **Raises** — `ExceptionType: when it is raised`. List exceptions the function explicitly raises; inherited ones only if relevant.
- **Yields** — use instead of Returns for generators.
- **Attributes** — document class-level attributes, same `name: description` form.
- **Examples** — must be the LAST section. Nest a `.. code-block:: python` directive so it renders with syntax highlighting.

### Class and module placement

```python
class DataProcessor:
    """Handles batch processing of incoming data streams.

    Manages connection pooling, retry logic, and result aggregation.

    Attributes:
        batch_size: Number of items processed per batch.
        max_retries: Maximum retry attempts for failed items.

    Examples:
        .. code-block:: python

            processor = DataProcessor(batch_size=100)
            results = processor.run(data_stream)
    """
```

```python
"""Utilities for data transformation and validation.

Helpers for normalizing, validating, and transforming data structures.

Examples:
    .. code-block:: python

        from utils import normalize_record

        clean_data = normalize_record(raw_record)
"""
```

### Rules

- Summary is one line ending in a period, with a blank line before the longer description and before the first section.
- Section order: Args, Returns, Yields, Raises, Examples (Examples last).
- Backticks for inline code and references: `None`, `True`, `SomeClass`.
- No trailing whitespace.

## What to document

- Every module, class, function, and method — **public and private**. Docstrings are for the developer reading and calling the code, and private methods get called like anything else.
- Gate on triviality, not visibility: a self-evident one-liner (public or private) can keep just a summary line; non-obvious logic gets full Args/Returns/Raises.
- Skip magic methods except `__init__`.
- **Properties** — describe what the property represents.
- **Overrides** — reference the parent's docstring or provide their own.
- Types live in annotations, not the docstring. If an annotation is missing, document the type with lowercase generics (`list`, `dict`).

## Process

1. Read the target files.
2. If any target file defines functions decorated with LangChain `@tool`, read
   the [LangChain tool docstring rules](references/langchain-tool-docstrings.md)
   before editing any `@tool` functions in this run. Do not load that reference
   when the target contains no LangChain `@tool` functions.
3. Scan each module, class, function, and method against the Style Reference.
4. Fix each violation with the minimal change: preserve existing content, add missing sections, infer descriptions from the code. If intent is unclear, ask.
5. Re-read modified files to confirm the fixes.

For a directory, process `__init__.py` first, then modules, then tests (lighter — basic summaries on test functions). Batch large directories and confirm before continuing.

## Report

- Files changed; for each, the location (line, entity), what you fixed, and a before/after for non-trivial changes.
- A one-line count of issues fixed per file.
