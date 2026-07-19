# kuznets

Remote data access for economic and financial data — FRED, OECD, Eurostat, World Bank,
Fama-French, Yahoo Finance, and more — returned as pandas, polars, pyarrow, or dask frames.

kuznets is a fork of [pydata/pandas-datareader](https://github.com/pydata/pandas-datareader),
renamed after diverging: readers are dataframe-agnostic, multi-symbol reads fetch concurrently,
and the test suite runs offline against recorded responses.

[![PyPI](https://img.shields.io/pypi/v/kuznets.svg)](https://pypi.org/project/kuznets/)
[![Coverage](https://codecov.io/gh/jessegrabowski/kuznets/branch/main/graph/badge.svg)](https://codecov.io/gh/jessegrabowski/kuznets)
[![License](https://img.shields.io/pypi/l/kuznets)](https://pypi.org/project/kuznets/)

## Installation

Install using `pip`

``` shell
pip install kuznets
```

## Usage

``` python
import kuznets as kz
kz.get_data_fred('GS10')
```

Every reader accepts an `output_type` argument to return polars, pyarrow, or dask frames instead of
pandas, and multi-symbol daily reads fetch concurrently (tune with `max_workers`):

``` python
kz.DataReader(["AAPL", "MSFT"], "stooq", output_type="polars", max_workers=8)
```

## Documentation

[Stable documentation](https://pydata.github.io/kuznets/) is available on
[github.io](https://pydata.github.io/kuznets/). A second copy of the stable
documentation is hosted on [read the docs](https://kuznets.readthedocs.io/)
for more details.

[Development documentation](https://pydata.github.io/kuznets/devel/) is available
for the latest changes in master.

### Requirements

Using kuznets requires the following packages:

-   pandas>=3.0
-   narwhals>=2.0
-   lxml
-   requests

Non-pandas output backends are optional extras:

``` shell
pip install kuznets[polars]    # or [pyarrow], [dask], [backends]
```

Building the documentation additionally requires:

-   matplotlib
-   ipython
-   requests_cache
-   sphinx
-   pydata_sphinx_theme

Development and testing dependencies are defined in `pyproject.toml`: the `dev` extra for pip
workflows, and the pixi `test`/`lint` features for the pixi workspace.

### Install latest development version

``` shell
python -m pip install git+https://github.com/jessegrabowski/kuznets.git
```

or

``` shell
git clone https://github.com/jessegrabowski/kuznets.git
cd kuznets
python setup.py install
```

### Development environment

The repo is a [pixi](https://pixi.sh) workspace: `pixi install` creates the dev environment
(editable install, test and lint tools), `pixi run test` runs the suite, and `pixi run -e py314
test` runs it on another Python. `pip install -e ".[dev]"` in a virtualenv works too.

### Running the tests

The test suite runs fully offline by default: each reader is replayed against a **recorded real
response** stored under `tests/data/`, so no third-party service is contacted.

``` shell
pytest
```

Tests marked `network` are deselected by default. Each one runs a reader against the live service
and asserts the *shape* of the result (columns, dtypes, non-empty) — an API-drift detector that
skips gracefully when a service is unreachable:

``` shell
pytest -m network
```

The offline fixtures are recordings, not hand-written mocks. To regenerate them from the live
services, run the `network` tests in record mode:

``` shell
RECORD=1 pytest -m network
```

This rewrites `tests/data/` from the real responses (and a wrong parser fails here, at record time,
rather than being hidden by a fixture built to match it). A weekly GitHub Actions workflow
(`refresh-fixtures`) does this automatically and opens a PR when a fixture changes, failing if an
upstream shape breaks. A few services can't be recorded and are documented in their tests: Stooq
serves an anti-bot challenge to scripted clients, and the keyed readers (AlphaVantage, Quandl,
Tiingo) need API keys.
