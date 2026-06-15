import pandas as pd
import pytest

from pandas_datareader.io.util import _pivot_observations, _to_datetime_index

pytestmark = pytest.mark.stable


def test_pivot_keeps_columns_with_duplicate_labels():
    # Two distinct codes can map to the same display name; pivoting on codes (not labels) must
    # preserve both columns rather than collapsing or raising "duplicate entries, cannot reshape".
    records = [(("A1", "2000"), 1.0), (("A2", "2000"), 2.0)]
    label_maps = [{"A1": "Foo", "A2": "Foo"}, {}]

    df = _pivot_observations(records, ["Area", "Time"], label_maps, time_pos=1)

    assert df.shape == (1, 2)
    assert list(df.columns) == ["Foo", "Foo"]
    assert sorted(df.iloc[0].tolist()) == [1.0, 2.0]


def test_pivot_relabels_multilevel_columns():
    records = [
        (("AUS", "TUD", "2000"), 24.7),
        (("USA", "TUD", "2000"), 12.8),
    ]
    label_maps = [
        {"AUS": "Australia", "USA": "United States"},
        {"TUD": "Trade union density"},
        {},
    ]

    df = _pivot_observations(records, ["Area", "Measure", "Time"], label_maps, time_pos=2)

    assert df.columns.names == ["Area", "Measure"]
    assert df.loc["2000", ("Australia", "Trade union density")].iloc[0] == 24.7


def test_pivot_time_only_cube():
    records = [(("2000",), 5.0), (("2001",), 6.0)]

    df = _pivot_observations(records, ["Time"], [{}], time_pos=0)

    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.squeeze().tolist() == [5.0, 6.0]


def test_to_datetime_index_parses_calendar_codes():
    idx = _to_datetime_index(["2009-01-01", "2010-01-01"], "Time")
    assert isinstance(idx, pd.DatetimeIndex)


@pytest.mark.filterwarnings("ignore:Could not infer format:UserWarning")
def test_to_datetime_index_keeps_non_calendar_codes():
    # Semester codes aren't datetimes; they must survive as plain labels, which is what tells the
    # readers to skip datetime-bounded truncation.
    idx = _to_datetime_index(["2013-S1", "2013-S2"], "Time")
    assert not isinstance(idx, pd.DatetimeIndex)
    assert list(idx) == ["2013-S1", "2013-S2"]
