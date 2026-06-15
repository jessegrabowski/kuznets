import pandas as pd
import pytest

from pandas_datareader.io import read_jstat

pytestmark = pytest.mark.stable


def test_read_jstat_maps_row_major_offsets():
    # Minimal 2x2 JSON-stat cube. Values are keyed by the row-major offset geo*2 + time, so the
    # test pins that read_jstat unravels each offset back to the right (country, year) cell.
    dataset = {
        "id": ["geo", "time"],
        "size": [2, 2],
        "dimension": {
            "geo": {
                "label": "Country",
                "category": {
                    "index": {"DE": 0, "FR": 1},
                    "label": {"DE": "Germany", "FR": "France"},
                },
            },
            "time": {"label": "Time", "category": {"index": {"2009": 0, "2010": 1}}},
        },
        "value": {"0": 1.0, "1": 2.0, "2": 3.0, "3": 4.0},
    }

    df = read_jstat(dataset)

    assert isinstance(df.index, pd.DatetimeIndex)
    assert list(df.index.year) == [2009, 2010]
    assert df.columns.name == "Country"
    assert df["Germany"].tolist() == [1.0, 2.0]
    assert df["France"].tolist() == [3.0, 4.0]


def test_read_jstat_fills_gaps_across_series():
    # France is missing its 2010 observation (flat offset 3 omitted); the reshape must leave a NaN
    # there rather than dropping the row Germany still populates.
    dataset = {
        "id": ["geo", "time"],
        "size": [2, 2],
        "dimension": {
            "geo": {
                "label": "Country",
                "category": {
                    "index": {"DE": 0, "FR": 1},
                    "label": {"DE": "Germany", "FR": "France"},
                },
            },
            "time": {"label": "Time", "category": {"index": {"2009": 0, "2010": 1}}},
        },
        "value": {"0": 1.0, "1": 2.0, "2": 3.0},
    }

    df = read_jstat(dataset)

    assert df["Germany"].tolist() == [1.0, 2.0]
    france = df["France"].tolist()
    assert france[0] == 3.0
    assert pd.isna(france[1])
