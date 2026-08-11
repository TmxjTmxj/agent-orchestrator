---
name: pythonic-quality
description: "Use when analyzing, reviewing, refactoring, or writing Python code. Apply Pythonic idioms, SOLID design, and Liskov-safe subtyping. Invoke for code review, architecture feedback, or implementation in Python."
---

# Quality Python (Pythonic + SOLID + Liskov)

Read this skill **before** proposing or editing non-trivial Python. Align with repo conventions (formatter, linter, tests) when they exist.

## Pythonic (idioms and style)

- **PEP 8** as the baseline; clear names; modules with a coherent responsibility.
- **Comprehensions and generators** when they clarify control flow; avoid deep nesting.
- **`pathlib`**, **`with`** for resources, **`dataclasses`** / **`Enum`** when modeling simple data.
- **Typing** (`typing` / `collections.abc`): parameters and returns at public boundaries; `Protocol` for explicit duck typing.
- **EAFP** (try/except around operations that may fail) vs. **LBYL** only when clearer or cheaper.

```python
for i, item in enumerate(items, start=1):
    ...
merged = {**defaults, **overrides}
from pathlib import Path
with Path("data.txt").open(encoding="utf-8") as f:
    text = f.read()
```

## Class design in Python (preferences)

| Situation                  | Prefer                                                                            | Avoid                                                             |
| -------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Plain data + equality/hash | `@dataclass(frozen=True)` or `NamedTuple`                                         | Mutable shared defaults; huge mutable classes                     |
| Closed set of variants     | `Enum` or `StrEnum`                                                               | String constants scattered across modules                         |
| “Can do X” capability      | `Protocol` (structural)                                                           | Deep inheritance trees for behavior reuse                         |
| Must enforce overrides     | `ABC` + `@abstractmethod`                                                         | Empty ABCs “for documentation only”                               |
| Optional hooks / plugins   | Registry (`dict[str, Callable]`), `entry_points`, or injected `Sequence[Handler]` | Subclassing the framework for every feature                       |
| Construction               | `@classmethod` factory when names clarify variants; otherwise `__init__`          | `__new__` unless you truly need instance pooling                  |
| Privacy                    | Single leading `_` for internal API                                               | “Private” tricks unless profiling proves need (`__slots__`, etc.) |

**Protocol vs ABC:** use **`Protocol`** when callers only need a shape (duck typing with checks). Use **`ABC`** when you share real implementation or must force subclasses to implement methods.

```python
from abc import ABC, abstractmethod
from typing import Protocol

class Serializer(Protocol):
    def dumps(self, obj: object) -> bytes: ...

class ExportJob(ABC):
    @abstractmethod
    def run(self) -> None: ...

    def _temp_path(self) -> str:  # optional shared helper for subclasses
        return "/tmp/export"
```

## SOLID — concrete examples

### S — Single responsibility

**Bad:** one class loads config, validates, and sends email.

**Better:** separate units; orchestration is a thin function or small class.

```python
def load_config(path: Path) -> dict[str, object]: ...
def validate_config(cfg: dict[str, object]) -> None: ...
def send_alert(to: str, body: str) -> None: ...

def bootstrap(path: Path) -> None:
    cfg = load_config(path)
    validate_config(cfg)
    send_alert("ops@example.com", "ready")
```

### O — Open/closed

Extend behavior **without** editing the dispatcher: register new strategies.

```python
from typing import Callable

Handler = Callable[[str], str]

_REGISTRY: dict[str, Handler] = {}

def register(kind: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _REGISTRY[kind] = fn
        return fn
    return deco

@register("upper")
def _upper(s: str) -> str:
    return s.upper()

def transform(kind: str, s: str) -> str:
    return _REGISTRY[kind](s)
```

### L — Liskov substitution

Subtypes must keep the **observable contract** of the base. If the base documents “never raises on empty input,” a subclass must not raise `ValueError` for `""` unless the base type is updated everywhere.

```python
class Bird:
    def move(self) -> str:
        return "move"

class Penguin(Bird):
    def move(self) -> str:
        raise RuntimeError("cannot fly")  # breaks callers that iterate Bird.move() expecting no crash
```

Fix: split `FlyingBird` / `WalkingBird`, or make `move()` return a result type / document exceptions per subtype consistently.

### I — Interface segregation

**Bad:** one fat protocol forces PDF exporters to implement `to_html`.

**Better:** small protocols; adapters implement only what they support.

```python
from typing import Protocol

class ToPdf(Protocol):
    def to_pdf(self) -> bytes: ...

class ToHtml(Protocol):
    def to_html(self) -> str: ...

def publish_pdf(doc: ToPdf) -> None:
    send(doc.to_pdf())
```

### D — Dependency inversion

High-level policy depends on **`Notifier`**, not on `SlackClient`.

```python
from typing import Protocol

class Notifier(Protocol):
    def send(self, msg: str) -> None: ...

class OrderService:
    def __init__(self, notify: Notifier) -> None:
        self._notify = notify

    def place(self) -> None:
        ...
        self._notify.send("order placed")

class SlackNotifier:
    def send(self, msg: str) -> None:
        ...
```

Wire `SlackNotifier()` (or a fake) at the composition root—**not** inside `place()`.

## Liskov and inheritance (deeper)

- **Pre/postconditions:** subclass methods should accept **at least** what the base accepts and return **at most** what callers expect (exceptions included).
- **Invariant:** if `Cache.get` promises “returns same object for same key until invalidated,” a subclass must not return a fresh object each time without changing the contract.

Rectangle / square (mutable API breaks substitution once `Rectangle` grows independent setters):

```python
class Rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width, self.height = w, h

class Square(Rectangle):
    def __init__(self, side: int) -> None:
        super().__init__(side, side)

# Adding Rectangle.set_width(w) that does *not* touch height makes Square
# unsatisfiable: either Square breaks the square invariant or violates Liskov
# for code that only knows Rectangle.
```

Prefer sibling types + shared `Protocol` (e.g. `HasArea`) or an immutable `Square(side)` that does not inherit a mutable `Rectangle`.

## Quick checklist

1. One reason to change per module/class at boundaries?
2. New behavior = new registration/plugin, not editing core `if/elif` chains?
3. Subtypes safe for all valid base calls?
4. Clients depend on small `Protocol`s / ABCs, not concrete SDK classes?
5. Idiomatic for the project’s Python version?

Favor simplicity; not every module needs classes—**functions and modules** are often the most Pythonic layer.
