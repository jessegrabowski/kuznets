# pandas-datareader

Up to date remote data access for pandas, works for multiple versions of
pandas.

[![image](https://img.shields.io/pypi/v/pandas-datareader.svg)](https://pypi.python.org/pypi/pandas-datareader/)
[![image](https://codecov.io/gh/pydata/pandas-datareader/branch/master/graph/badge.svg)](https://codecov.io/gh/pydata/pandas-datareader)
[![image](https://readthedocs.org/projects/pandas-datareader/badge/?version=latest)](https://pandas-datareader.readthedocs.io/en/latest/)
[![image](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License](https://img.shields.io/pypi/l/pandas-datareader)](https://pypi.org/project/pandas-datareader/)

## Installation

Install using `pip`

``` shell
pip install pandas-datareader
```

## Usage

``` python
import pandas_datareader as pdr
pdr.get_data_fred('GS10')
```

## Documentation

[Stable documentation](https://pydata.github.io/pandas-datareader/) is available on
[github.io](https://pydata.github.io/pandas-datareader/). A second copy of the stable
documentation is hosted on [read the docs](https://pandas-datareader.readthedocs.io/)
for more details.

[Development documentation](https://pydata.github.io/pandas-datareader/devel/) is available
for the latest changes in master.

### Requirements

Using pandas datareader requires the following packages:

-   pandas>=1.5.3
-   lxml
-   requests>=2.19.0

Building the documentation additionally requires:

-   matplotlib
-   ipython
-   requests_cache
-   sphinx
-   pydata_sphinx_theme

Development and testing additionally requires:

-   black
-   coverage
-   codecov
-   coveralls
-   flake8
-   pytest
-   pytest-cov
-   wrapt

### Install latest development version

``` shell
python -m pip install git+https://github.com/pydata/pandas-datareader.git
```

or

``` shell
git clone https://github.com/pydata/pandas-datareader.git
cd pandas-datareader
python setup.py install
```

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
