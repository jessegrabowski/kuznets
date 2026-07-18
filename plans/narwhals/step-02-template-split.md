# Step 02 (PR 2) — mechanical template split + `output_type` threading

## What and why

Restructure every reader onto the template method **without changing any behavior**. This PR is
pure, `git diff`-reviewable code motion plus a kwarg; its test bar is the untouched offline suite
passing with **zero fixture changes**. Isolating the rename risk here means every later PR's diff
is purely about tidy behavior.

The template (in `base.py::_BaseReader`):

```python
def read(self):
    payload = self._read_core()               # network + parse; closes session as today
    if self.output_type == "pandas":
        return self._present_pandas(payload)  # today's decorations, verbatim
    return self._present_tidy(payload)        # native frame(s) in output_type

def _read_core(self):                         # default = exact current read() body
    try:
        return self._read_one_data(self.url, self.params)
    finally:
        self.close()

def _present_pandas(self, payload):           # simple readers: parse result IS today's output
    return payload

def _present_tidy(self, payload):             # default: detach transient parse index, convert
    tidy, _ = detach_index(payload)
    return from_pandas(tidy, self.output_type)
```

Rules of the split:

- Every bespoke `read()` override becomes `_read_core()`; internal `super().read()` chains become
  `super()._read_core()` so nothing double-converts (yahoo actions, tsp, quandl, av/forex).
- `fred.py` and `wb.py` already have a `read`/`_read` pair: delete the wrapper `read`, fold its
  `try/finally close` into `_read`, rename to `_read_core`.
- `famafrench.py`'s `read()` is docstring-only: delete it, move the docstring to the class.
- `moex.read_all_boards` (public) gets the same core/presenter split.
- Payload = whatever the old `read()` returned; `_present_pandas` is the identity everywhere in
  this PR. Presenters gain real bodies only in later steps.
- `_BaseReader.__init__` gains trailing `output_type: str = "pandas"`, stored as
  `self.output_type = validate_output_type(output_type)` (fail-fast, pre-HTTP), threaded through
  every subclass `__init__` with an explicit signature and through `DataReader`'s branches.
  `get_data_*` helpers already forward `**kwargs` — no edits.
- After this PR, `output_type="polars"` **works** for readers whose presenter is the identity on
  an index-decorated frame only via the default `_present_tidy` — which is correct for simple CSV
  readers and *not yet correct* for panel/dict/period readers. That's fine: those readers'
  tidy presenters are landed in steps 03–06; nothing regresses for pandas users meanwhile.

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | Template on `_BaseReader` + `_DailyBaseReader` | `base.py`: `read()` dispatcher, `_read_core`/`_present_pandas`/`_present_tidy` defaults; `_DailyBaseReader.read` → `_read_core`; `__init__` gains `output_type` + validation | Full offline suite green, zero fixture changes; new `tests/test_base.py` cases: `output_type="bogus"` raises `ValueError` in `__init__` (no HTTP — use a `from_fixtures` handler that fails on any URL); missing-backend `ImportError` via monkeypatched `find_spec` |
| 2 | Rename bespoke overrides, group A | `fred.py`, `wb.py` (collapse read/_read), `famafrench.py` (delete docstring-only override), `tsp.py`, `quandl.py` — `read` → `_read_core`, `super()` chains fixed | Full offline suite green, zero fixture changes (these files' tests are the parity oracle) |
| 3 | Rename bespoke overrides, group B | `econdb.py`, `tiingo.py` (×2 readers), `moex.py` (+ `read_all_boards` split), `av/forex.py`, `yahoo/actions.py` (×3, chained), `yahoo/fx.py`, `yahoo/quotes.py` | Full offline suite green, zero fixture changes |
| 4 | Thread `output_type` through subclass `__init__`s and `DataReader` | Explicit `__init__`s: econdb, tiingo ×3, moex, av family, yahoo daily/quotes, tsp, quandl, wb (verify which of naver/stooq/oecd/eurostat have explicit signatures — inherit otherwise); `data.py::DataReader` passes `output_type=` in every branch; nasdaq branch wraps `get_nasdaq_symbols` result via `detach_index`+`from_pandas` | Full offline suite green; `tests/test_data.py`: `DataReader(..., output_type="bogus")` raises before any request; smoke: `DataReader("SPY", "stooq", output_type="polars")` against fixtures returns a polars frame (schema asserted loosely — exact tidy schemas are later steps' contracts) |

## PR review notes

- Reviewer should verify commits 2–3 are pure code motion (rename + indentation), ideally with
  `git diff --color-moved`.
- The only semantic addition in the whole PR is the `output_type` kwarg + validation call.
