from datetime import datetime

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from pandas_datareader.io.util import (
    _observations_to_records,
    _parse_period_code,
    _pivot_observations,
    _present_observations,
    _to_datetime_index,
)
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed

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


class TestObservationsToRecords:
    records = [
        (("AUS", "TUD", "2000"), 24.7),
        (("USA", "TUD", "2001"), 12),
    ]
    dim_names = ["Area", "Measure", "Time"]
    label_maps = [{"AUS": "Australia"}, {"TUD": "Trade union density"}, {"2000": "Year 2000"}]

    def rows(self):
        return _observations_to_records(self.records, self.dim_names, self.label_maps, time_pos=2)

    def test_non_time_codes_map_to_display_labels(self):
        rows = self.rows()
        assert rows[0]["Area"] == "Australia"
        assert rows[0]["Measure"] == "Trade union density"

    def test_unlabeled_codes_fall_back_to_the_code(self):
        assert self.rows()[1]["Area"] == "USA"

    def test_time_keeps_raw_codes_even_when_labeled(self):
        assert [row["Time"] for row in self.rows()] == ["2000", "2001"]

    def test_values_coerce_to_float(self):
        assert self.rows()[1]["value"] == 12.0
        assert isinstance(self.rows()[1]["value"], float)


class TestPresentObservations:
    def test_pandas_output_is_the_pivot(self):
        records = [(("AUS", "2000"), 1.0), (("USA", "2000"), 2.0)]
        label_maps = [{"AUS": "Australia", "USA": "United States"}, {}]
        wide = _present_observations(records, ["Area", "Time"], label_maps, 1, "pandas")
        expected = _pivot_observations(records, ["Area", "Time"], label_maps, 1)
        pd.testing.assert_frame_equal(wide, expected)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_long_native_frame_with_datetime_cast(self, output_type):
        skip_unless_installed(output_type)
        records = [(("AUS", "2000"), 1.0), (("USA", "2001"), 2.0)]
        label_maps = [{"AUS": "Australia", "USA": "United States"}, {}]
        tidy = as_narwhals(_present_observations(records, ["Area", "Time"], label_maps, 1, output_type))

        assert tidy.columns == ["Area", "Time", "value"]
        assert tidy.schema["Time"] == nw.Datetime
        assert tidy.schema["value"] == nw.Float64
        assert tidy["Area"].to_list() == ["Australia", "United States"]

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_period_codes_parse_identically_across_backends(self, output_type):
        skip_unless_installed(output_type)
        records = [(("AUS", "2009-Q3"), 1.0), (("AUS", "2013-S2"), 2.0)]
        tidy = as_narwhals(_present_observations(records, ["Area", "Time"], [{}, {}], 1, output_type))
        assert tidy.schema["Time"] == nw.Datetime
        assert tidy["Time"].to_list() == [datetime(2009, 7, 1), datetime(2013, 7, 1)]

    def test_unrecognized_time_codes_keep_the_whole_column_as_strings(self):
        skip_unless_installed("polars")
        records = [(("AUS", "2009"), 1.0), (("AUS", "FY2009/10"), 2.0)]
        tidy = as_narwhals(_present_observations(records, ["Area", "Time"], [{}, {}], 1, "polars"))
        assert tidy.schema["Time"] == nw.String
        assert tidy["Time"].to_list() == ["2009", "FY2009/10"]


class TestParsePeriodCode:
    @pytest.mark.parametrize(
        "code, expected",
        [
            ("2009", datetime(2009, 1, 1)),
            ("2009-03", datetime(2009, 3, 1)),
            ("2009-3", datetime(2009, 3, 1)),
            ("2009-03-15", datetime(2009, 3, 15)),
            ("2009-Q1", datetime(2009, 1, 1)),
            ("2009-Q4", datetime(2009, 10, 1)),
            ("2009Q2", datetime(2009, 4, 1)),
            ("2013-S1", datetime(2013, 1, 1)),
            ("2013-S2", datetime(2013, 7, 1)),
            ("2013-s2", datetime(2013, 7, 1)),
            ("2020-W01", datetime(2019, 12, 30)),
            ("2020-W53", datetime(2020, 12, 28)),
            # Tolerated variants pandas parses to the correct period.
            ("20090101", datetime(2009, 1, 1)),
            ("2009/03", datetime(2009, 3, 1)),
            ("2009-q1", datetime(2009, 1, 1)),
            ("2009-01-15T00:00:00", datetime(2009, 1, 15)),
            (" 2009 ", datetime(2009, 1, 1)),
            # pandas 3 timestamps reach beyond the old nanosecond range.
            ("1500", datetime(1500, 1, 1)),
            ("2263", datetime(2263, 1, 1)),
            ("9999-12-31", datetime(9999, 12, 31)),
        ],
    )
    def test_period_start_convention(self, code, expected):
        assert _parse_period_code(code) == expected

    @pytest.mark.parametrize(
        "code",
        [
            "FY2009/10",
            "notadate",
            "20",
            "0000",
            # Out-of-range components must reject, not wrap.
            "2009-13",
            "2009-00",
            "2009-01-32",
            "2009-Q5",
            "2009-Q0",
            "2013-S3",
            "2013-S0",
            "2020-W1",
            "2020-W00",
            "2020-W54",
            "2020-W99",
            # Decimal years would misparse as year-month; they must stay strings.
            "2009.5",
        ],
    )
    def test_unrecognized_codes_return_none(self, code):
        assert _parse_period_code(code) is None
