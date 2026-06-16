# CURRICULUM — Advanced Python for Test Automation (AQA)

> Owned by the **methodist** agent. This is a topic map (structure only — no
> copied text from sources). Topics are ordered basic → advanced, each tagged
> with the source that informs *coverage* (never wording or examples).
>
> **Source legend**
> - **Y** = *Intermediate Python* (Yasoob) — free backbone; reword for the platform.
> - **R** = *Fluent Python* (Ramalho) — **reference only**, NO copied text/examples.
> - **O** = *Python Testing with pytest* (Okken) — **reference only**, NO copied text/examples.
> - **orig** = no book; authored from scratch.
>
> `level` mirrors the contract's notion of difficulty progression. `slug` is the
> stable lesson id for ingest. Status: `done` / `next` / `planned`.

## How to use this map

When authoring, take the next `planned` topic in order (respecting
dependencies), give it a lesson `slug` from this table, and place it via the
lesson's `position` (the integer in the **Pos** column).

## Track 1 — Functions as first-class objects (foundation for everything AQA)

| Pos | Topic | Lesson slug | Source | Status | AQA connection |
|----:|-------|-------------|--------|--------|----------------|
| 1 | First-class & higher-order functions; closures | `functions-first-class` | Y, R | **done** | Fixtures and parametrization pass callables around; closures back factory fixtures. |
| 2 | `*args` / `**kwargs`, argument forwarding | `args-kwargs` | Y | **done** | Wrappers/decorators must forward arbitrary test signatures. |
| 3 | **Decorators (basics)** | `decorators-basics` | Y, R | **done** | `@pytest.fixture`, `@pytest.mark.*`, timing/retry decorators. |
| 4 | Decorators with arguments; stacking; `functools.wraps` deep dive | `decorators-advanced` | Y, R | done | `@pytest.mark.parametrize`, custom marks, `@retry(times=3)`. |
| 5 | `functools` toolkit (`partial`, `lru_cache`, `reduce`, `cmp_to_key`) | `functools-toolkit` | Y, R | **done** | `partial` for building parametrized test callables and clients. |

## Track 2 — Iteration & lazy data (test-data generation)

| Pos | Topic | Lesson slug | Source | Status | AQA connection |
|----:|-------|-------------|--------|--------|----------------|
| 6 | Iterators & the iterator protocol | `iterators-protocol` | Y, R | **done** | Understanding what pytest iterates over during collection. |
| 7 | Generators & `yield` | `generators` | Y, R | **done** | Generator-based fixtures (`yield` for setup/teardown). |
| 8 | Generator expressions vs comprehensions; `itertools` | `itertools` | Y, R | **done** | Building large parametrized test-case streams lazily. |

## Track 3 — Context & resource management (setup/teardown)

| Pos | Topic | Lesson slug | Source | Status | AQA connection |
|----:|-------|-------------|--------|--------|----------------|
| 9 | Context managers (`with`, `__enter__`/`__exit__`) | `context-managers` | Y, R | **done** | Deterministic resource setup/teardown in tests. |
| 10 | `contextlib` (`@contextmanager`, `ExitStack`, `suppress`) | `contextlib` | Y, R | **done** | `pytest.raises` is a context manager; building reusable test scaffolds. |

## Track 4 — Data modelling & correctness

| Pos | Topic | Lesson slug | Source | Status | AQA connection |
|----:|-------|-------------|--------|--------|----------------|
| 11 | Comprehensions & unpacking patterns | `comprehensions` | Y, R | **done** | Concise assertions and test-data shaping. |
| 12 | Dataclasses & `__eq__`/`__repr__` | `dataclasses` | R | **done** | Value objects make `assert a == b` failures readable. |
| 13 | Type hints & `typing` for tests | `type-hints` | R | **done** | Typed fixtures/factories catch wiring bugs before runtime. |
| 14 | Exceptions, custom exception types, `raise ... from` | `exceptions` | Y, R | **done** | Asserting on error type/message; negative testing. |

## Track 5 — Objects & protocols (advanced)

| Pos | Topic | Lesson slug | Source | Status | AQA connection |
|----:|-------|-------------|--------|--------|----------------|
| 15 | Dunder methods & the data model | `dunder-methods` | R | **done** | Custom matchers/comparators for domain objects under test. |
| 16 | Properties & descriptors | `descriptors` | R | **done** | Understanding framework magic (e.g. how fixtures attach). |
| 17 | `__slots__`, metaclasses (awareness, not abuse) | `metaclasses` | Y, R | **done** | How test frameworks auto-register classes/plugins. |

## Track 6 — Concurrency & I/O (modern AQA)

| Pos | Topic | Lesson slug | Source | Status | AQA connection |
|----:|-------|-------------|--------|--------|----------------|
| 18 | `async`/`await` basics | `async-basics` | R | **done** | Testing async code; `pytest-asyncio` mental model. |
| 19 | Mocking & test doubles (stdlib `unittest.mock`) | `mocking` | O | planned | Isolating units; patching network/time for determinism. |

## Track 7 — pytest mastery (capstone, AQA-specific)

| Pos | Topic | Lesson slug | Source | Status | AQA connection |
|----:|-------|-------------|--------|--------|----------------|
| 20 | Fixtures: scope, factories, `yield` teardown | `pytest-fixtures` | O | planned | Core AQA skill; builds on decorators + generators + context managers. |
| 21 | Parametrization & `ids` | `pytest-parametrize` | O | planned | Table-driven testing; builds on Track 1/2. |
| 22 | Marks, conftest, plugins | `pytest-marks-plugins` | O | planned | Organizing real suites; builds on decorators-advanced. |
| 23 | Assertions, `pytest.raises`, `approx` | `pytest-assertions` | O | planned | Expressive failures; builds on exceptions + context managers. |

## Dependency notes

- Decorators (3, 4) are prerequisites for understanding pytest marks/fixtures (20, 22).
- Generators (7) and context managers (9–10) are prerequisites for `yield` fixtures (20).
- Track 7 is intentionally last: it composes Tracks 1–6 into the learner's target skill.

## Progress

Done (18): pos 1–18. Remaining: pos 19 `mocking`, then Track 7 capstone —
pos 20 `pytest-fixtures`, 21 `pytest-parametrize`, 22 `pytest-marks-plugins`,
23 `pytest-assertions`.
