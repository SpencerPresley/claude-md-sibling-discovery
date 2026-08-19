---
name: writing-google-docstrings
description: Use when writing or modifying Python code and Google-style docstrings should be maintained throughout the current task.
---

# Writing Google Docstrings

Treat accurate docstrings as part of the Python code you are writing, not as a
separate cleanup pass. Once this skill is invoked, apply it throughout the
current task.

Write a Google-style docstring when you create a module, class, function, or
method. When you change existing Python code, update its docstring if the
signature, behavior, return value, raised exceptions, or important side effects
changed. Keep unrelated existing docstrings out of scope; use `fix-docstrings`
when the task is to audit a file or directory.

## Write the Contract

Describe what callers need to know, not how the implementation happens:

- Start with a one-line summary ending in a period.
- Add a longer description only when behavior, constraints, or side effects are
  not obvious from the summary and signature.
- Add only the sections the callable needs, in this order: `Args`, `Returns` or
  `Yields`, `Raises`, then `Examples`.
- In `Args`, write `name: description`. Types belong in annotations; include a
  type only when the parameter has no annotation. Mention meaningful defaults
  and constraints in the description.
- In `Returns`, describe the value's semantics. When the return annotation
  supplies the type, do not repeat it. When there is no return annotation,
  include the missing type before the description.
- Do not use an implementation variable as a return label; local names are not
  part of the calling contract. For a tuple, describe the tuple as one return
  value and give its components descriptive names, such as "A tuple
  `(name, revision)`, where ...".
- In `Raises`, document exceptions the callable explicitly raises and the
  conditions that cause them.
- Use `Attributes` for class-level attributes. Describe a property as the value
  it represents.
- Use backticks for code values and symbols such as `None`, `True`, and
  `SomeClass`. Put `Examples` last.

A self-evident callable can use only its summary. Non-obvious behavior needs the
sections that expose its calling contract. Document public and private code by
the same standard. Skip magic methods other than `__init__` unless their
behavior needs explanation.

## Complete Example

Use a summary, a blank line, and a longer description when callers need more
than the signature tells them. Keep `Examples` last:

```python
def reserve_capacity(job_id: str, units: int = 1) -> Reservation:
    """Reserve capacity for a queued job.

    Persists the reservation before returning it. Reservations expire after
    ten minutes unless the worker starts the job.

    Args:
        job_id: Identifier of the job receiving the reservation.
        units: Number of capacity units to reserve. Must be positive.

    Returns:
        The persisted reservation, including its expiration time.

    Raises:
        CapacityUnavailableError: If the requested capacity is unavailable.
        ReservationStoreError: If the reservation cannot be persisted.

    Examples:
        .. code-block:: python

            reservation = reserve_capacity("job-42", units=2)
            print(reservation.expires_at)
    """
```

## Keep Types in Annotations

Make annotations precise enough that docstrings can focus on semantics. In
modules that use forward references or type-only imports, put
`from __future__ import annotations` immediately after the module docstring.
Then import names used only for static analysis behind `TYPE_CHECKING`:

```python
"""Schedule queued jobs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Job


def schedule(jobs: Sequence[Job]) -> list[Job]:
    """Schedule jobs in execution order."""
```

Do not quote `Job` when postponed annotations are active. Do not guard an import
that runtime code uses. A name imported under `TYPE_CHECKING` is absent at
runtime, so decorators, serializers, dependency-injection frameworks, and code
that evaluates annotations may fail to resolve it. Keep those imports available
at runtime or use the framework's supported annotation-resolution mechanism.

Use the most precise useful shape:

| Need | Use | Avoid |
|---|---|---|
| Concrete mutable collection | `list[Job]`, `dict[str, int]` | Bare `list`, bare `dict` |
| Read-only input contract | `Sequence[Job]`, `Mapping[str, int]` | Requiring `list` or `dict` unnecessarily |
| One of several real alternatives | `FileEvent | NetworkEvent` | `object`, `Any`, or a generic type parameter |
| Dictionary with known keys | `TypedDict` | `dict[str, object]` |
| Repeated complex domain shape | A named type alias | Repeating the full expression everywhere |
| Input and output types are related | A type parameter | Returning `object` or an unrelated union |

Use a type alias when the shape has domain meaning or is complex enough to
obscure signatures. Use `TypedDict` when the keys themselves are part of the
contract:

```python
from typing import Literal, TypedDict


class CreatedEvent(TypedDict):
    kind: Literal["created"]
    resource_id: str
    owner_id: str


class DeletedEvent(TypedDict):
    kind: Literal["deleted"]
    resource_id: str


type Event = CreatedEvent | DeletedEvent  # Python 3.12+
```

For projects targeting Python 3.11 or earlier, use the compatible spelling:

```python
from typing import TypeAlias


Event: TypeAlias = CreatedEvent | DeletedEvent
```

A generic expresses a relationship between types; it is not shorthand for
"this data has several possible shapes":

```python
# Good: the element type determines the return type.
def repeat[T](item: T, count: int) -> list[T]:  # Python 3.12+
    """Repeat an item `count` times."""
    return [item] * count


# Bad: bare containers discard the contract.
def repeat_bad(item: object, count: int) -> list:
    """Repeat an item `count` times."""
    return [item] * count


# Bad: T is unrelated to the input and tells callers nothing.
def parse_bad[T](payload: dict[str, object]) -> T:
    """Parse a payload."""
    ...
```

For projects targeting Python 3.11 or earlier, declare `T = TypeVar("T")` and
use the same `T` in the input and return annotations. Follow the project's
minimum Python version; do not introduce Python 3.12 syntax into an older
codebase.

## Return Shapes

An annotated scalar or object needs the meaning of the value, not its type or
the local variable used to hold it:

```python
def retry_delay(attempt: int) -> float:
    """Calculate the delay before another attempt.

    Returns:
        Delay in seconds before the next attempt.
    """
```

When the signature has no return annotation, put the missing type before the
description:

```python
def current_limit(account_id):
    """Read an account's current request limit.

    Returns:
        int: Maximum number of requests allowed per minute.
    """
```

Describe a tuple as one structured value rather than separate named returns:

```python
def parse_version(value: str) -> tuple[str, int]:
    """Parse a versioned resource identifier.

    Returns:
        A tuple `(name, revision)`, where `name` is the resource name and
        `revision` is its numeric revision.
    """
```

A generator documents what each iteration yields, not the iterator object:

```python
def iter_ready_jobs(queue: Queue) -> Iterator[Job]:
    """Iterate over jobs that are ready to run.

    Yields:
        Each ready job in queue order.
    """
```

Apply docstring changes alongside each code change. Before completing the task,
inspect the touched Python diff and correct any disagreement between the code
and its docstrings. Do not turn that check into a sweep of untouched code or a
separate docstring report.
