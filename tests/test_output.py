import importlib.util

import narwhals.stable.v2 as nw
import pandas as pd
import pandas.testing as tm
import pytest

from pandas_datareader._output import (
    attach_index,
    concat_frames,
    detach_index,
    filter_date_range,
    from_pandas,
    make_frame,
    to_datetime_col,
    validate_output_type,
)

pytestmark = pytest.mark.stable

requires_dask = pytest.mark.skipif(importlib.util.find_spec("dask") is None, reason="dask[dataframe] is not installed")


def dated_frame(index_name: str | None = "DATE") -> pd.DataFrame:
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-03"], name=index_name)
    return pd.DataFrame({"GDP": [1.0, 2.0, 3.0], "CPI": [4.0, 5.0, 6.0]}, index=index)


def column_values(frame, name: str) -> list:
    return nw.from_native(frame, eager_only=True)[name].to_list()


def skip_unless_installed(backend: str) -> None:
    if backend != "pandas":
        pytest.importorskip(backend)


class TestValidateOutputType:
    def test_pandas_passes_without_backend_check(self, monkeypatch):
        def forbidden(name):
            raise AssertionError("pandas must not trigger a backend availability check")

        monkeypatch.setattr(importlib.util, "find_spec", forbidden)
        assert validate_output_type("pandas") == "pandas"

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("polars", "polars"),
            ("POLARS", "polars"),
            ("pyarrow", "pyarrow"),
            ("arrow", "pyarrow"),
            ("Arrow", "pyarrow"),
            ("dask", "dask"),
        ],
    )
    def test_canonicalization(self, monkeypatch, name, expected):
        monkeypatch.setattr(importlib.util, "find_spec", lambda module: object())
        assert validate_output_type(name) == expected

    def test_unknown_backend_raises_value_error(self):
        with pytest.raises(ValueError, match="output_type='modin' is not supported") as exc_info:
            validate_output_type("modin")
        for valid_name in ["'arrow'", "'dask'", "'pandas'", "'polars'", "'pyarrow'"]:
            assert valid_name in str(exc_info.value)

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError, match="must be a str"):
            validate_output_type(object())

    def test_missing_backend_raises_import_error_with_extra_hint(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda module: None)
        with pytest.raises(ImportError, match=r"pip install pandas-datareader\[polars\]"):
            validate_output_type("polars")

    def test_missing_parent_module_raises_import_error(self, monkeypatch):
        def raise_module_not_found(module):
            raise ModuleNotFoundError(f"No module named {module.partition('.')[0]!r}")

        monkeypatch.setattr(importlib.util, "find_spec", raise_module_not_found)
        with pytest.raises(ImportError, match=r"optional dependency 'dask'"):
            validate_output_type("dask")


class TestDetachAttachIndex:
    def test_named_datetime_index_round_trip(self):
        original = dated_frame()
        tidy, index_cols = detach_index(original)
        assert index_cols == ["DATE"]
        assert list(tidy.columns) == ["DATE", "GDP", "CPI"]
        assert isinstance(tidy.index, pd.RangeIndex)
        tm.assert_frame_equal(attach_index(tidy, index_cols), original)

    def test_unnamed_datetime_index_becomes_date(self):
        tidy, index_cols = detach_index(dated_frame(index_name=None))
        assert index_cols == ["Date"]
        assert tidy["Date"].dtype.kind == "M"

    def test_unnamed_period_index_becomes_date(self):
        frame = pd.DataFrame({"x": [1.0]}, index=pd.PeriodIndex(["2020-01"], freq="M"))
        tidy, index_cols = detach_index(frame)
        assert index_cols == ["Date"]

    def test_unnamed_plain_index_becomes_index(self):
        frame = pd.DataFrame({"x": [1.0, 2.0]}, index=pd.Index(["a", "b"]))
        tidy, index_cols = detach_index(frame)
        assert index_cols == ["index"]

    def test_multiindex_round_trip(self):
        index = pd.MultiIndex.from_tuples([("US", 2020), ("US", 2021), ("FR", 2020)], names=["country", "year"])
        original = pd.DataFrame({"gdp": [1.0, 2.0, 3.0]}, index=index)
        tidy, index_cols = detach_index(original)
        assert index_cols == ["country", "year"]
        assert list(tidy.columns) == ["country", "year", "gdp"]
        tm.assert_frame_equal(attach_index(tidy, index_cols), original)

    def test_multiindex_unnamed_levels_get_positional_names(self):
        index = pd.MultiIndex.from_tuples([("US", 2020), ("FR", 2021)])
        tidy, index_cols = detach_index(pd.DataFrame({"x": [1.0, 2.0]}, index=index))
        assert index_cols == ["level_0", "level_1"]

    def test_detach_does_not_mutate_input(self):
        original = dated_frame()
        before = original.copy()
        detach_index(original)
        tm.assert_frame_equal(original, before)


class TestFromPandas:
    def test_pandas_returns_identical_object(self):
        tidy, _ = detach_index(dated_frame())
        assert from_pandas(tidy, "pandas") is tidy

    def test_multiindex_columns_raise(self):
        frame = pd.DataFrame([[1.0, 2.0]], columns=pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "MSFT")]))
        with pytest.raises(TypeError, match="detach_index"):
            from_pandas(frame, "polars")

    def test_meaningful_index_raises(self):
        with pytest.raises(TypeError, match="meaningful index"):
            from_pandas(dated_frame(), "polars")

    def test_positional_leftover_index_is_discarded(self):
        polars = pytest.importorskip("polars")
        tidy, _ = detach_index(dated_frame())
        reordered = tidy.iloc[[2, 0, 1]]
        assert not isinstance(reordered.index, pd.RangeIndex)
        result = from_pandas(reordered, "polars")
        assert isinstance(result, polars.DataFrame)
        assert result["GDP"].to_list() == [3.0, 1.0, 2.0]

    def test_polars_conversion(self):
        polars = pytest.importorskip("polars")
        tidy, _ = detach_index(dated_frame())
        result = from_pandas(tidy, "polars")
        assert isinstance(result, polars.DataFrame)
        assert result.columns == ["DATE", "GDP", "CPI"]
        assert result["DATE"].dtype == polars.Datetime("us")

    def test_pyarrow_conversion(self):
        pyarrow = pytest.importorskip("pyarrow")
        tidy, _ = detach_index(dated_frame())
        result = from_pandas(tidy, "pyarrow")
        assert isinstance(result, pyarrow.Table)
        assert result.column_names == ["DATE", "GDP", "CPI"]

    @requires_dask
    def test_dask_conversion(self):
        dask_dataframe = pytest.importorskip("dask.dataframe")
        tidy, _ = detach_index(dated_frame())
        result = from_pandas(tidy, "dask")
        assert isinstance(result, dask_dataframe.DataFrame)
        tm.assert_frame_equal(result.compute().reset_index(drop=True), tidy)

    def test_non_string_column_labels_are_cast(self):
        pytest.importorskip("polars")
        frame = pd.DataFrame({(0, 5): [1.0], "Count": [2.0]})
        result = from_pandas(frame, "polars")
        assert result.columns == ["(0, 5)", "Count"]

    def test_all_null_object_columns_become_float(self):
        pytest.importorskip("pyarrow")
        frame = pd.DataFrame({"x": pd.Series([None, None], dtype=object), "y": [1.0, 2.0]})
        result = from_pandas(frame, "pyarrow")
        assert str(result.schema.field("x").type) == "double"


SDMX_RECORDS = [
    {"Country": "USA", "TIME_PERIOD": "2020-01", "value": 1.5},
    {"Country": "FRA", "TIME_PERIOD": "2020-02", "value": 2.5},
]


class TestMakeFrame:
    def test_pandas_from_records(self):
        result = make_frame(SDMX_RECORDS, "pandas")
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["Country", "TIME_PERIOD", "value"]
        assert result["value"].tolist() == [1.5, 2.5]

    def test_polars_from_records(self):
        polars = pytest.importorskip("polars")
        result = make_frame(SDMX_RECORDS, "polars")
        assert isinstance(result, polars.DataFrame)
        assert result.columns == ["Country", "TIME_PERIOD", "value"]

    def test_pyarrow_from_records(self):
        pyarrow = pytest.importorskip("pyarrow")
        result = make_frame(SDMX_RECORDS, "pyarrow")
        assert isinstance(result, pyarrow.Table)
        assert result.column_names == ["Country", "TIME_PERIOD", "value"]

    @requires_dask
    def test_dask_from_records(self):
        dask_dataframe = pytest.importorskip("dask.dataframe")
        result = make_frame(SDMX_RECORDS, "dask")
        assert isinstance(result, dask_dataframe.DataFrame)
        assert result.compute()["value"].tolist() == [1.5, 2.5]

    def test_missing_record_keys_become_null(self):
        pytest.importorskip("polars")
        result = make_frame([{"a": 1, "b": "x"}, {"a": 2}], "polars")
        assert result.rows() == [(1, "x"), (2, None)]

    def test_column_oriented_input(self):
        result = make_frame({"a": [1, 2], "b": [3.0, 4.0]}, "pandas")
        assert result["a"].tolist() == [1, 2]

    def test_schema_forces_dtypes_over_inference(self):
        polars = pytest.importorskip("polars")
        schema = {"Country": nw.String(), "value": nw.Float64()}
        result = make_frame([{"Country": "USA", "value": 1}], "polars", schema=schema)
        assert result.schema["value"] == polars.Float64

    def test_empty_records_with_schema_yield_typed_empty_frame(self):
        pytest.importorskip("polars")
        result = make_frame([], "polars", schema={"Country": nw.String(), "value": nw.Float64()})
        assert result.columns == ["Country", "value"]
        assert result.height == 0

    def test_empty_records_without_schema_yield_empty_frame(self):
        result = make_frame([], "pandas")
        assert isinstance(result, pd.DataFrame)
        assert result.shape == (0, 0)


class TestFilterDateRange:
    def datetime_native(self, backend):
        return make_frame(
            {
                "Date": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03")],
                "x": [1.0, 2.0, 3.0],
            },
            backend,
        )

    @pytest.mark.parametrize("backend", ["pandas", "polars", "pyarrow"])
    def test_both_endpoints_inclusive(self, backend):
        skip_unless_installed(backend)
        result = filter_date_range(
            self.datetime_native(backend), "Date", pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-02")
        )
        assert column_values(result, "x") == [1.0, 2.0]

    def test_start_only(self):
        result = filter_date_range(self.datetime_native("pandas"), "Date", start=pd.Timestamp("2020-01-02"))
        assert result["x"].tolist() == [2.0, 3.0]

    def test_end_only(self):
        result = filter_date_range(self.datetime_native("pandas"), "Date", end=pd.Timestamp("2020-01-02"))
        assert result["x"].tolist() == [1.0, 2.0]

    def test_no_bounds_returns_same_object(self):
        frame = self.datetime_native("pandas")
        assert filter_date_range(frame, "Date") is frame

    def test_string_period_codes_skip_filtering(self):
        frame = make_frame({"TIME_PERIOD": ["2013-S1", "2013-S2"], "value": [1.0, 2.0]}, "pandas")
        result = filter_date_range(frame, "TIME_PERIOD", pd.Timestamp("2013-01-01"), pd.Timestamp("2013-06-30"))
        assert result is frame

    def test_date_typed_column(self):
        polars = pytest.importorskip("polars")
        frame = polars.DataFrame(
            {"Date": [pd.Timestamp("2020-01-01").date(), pd.Timestamp("2020-02-01").date()], "x": [1.0, 2.0]}
        )
        result = filter_date_range(frame, "Date", pd.Timestamp("2020-01-15"), pd.Timestamp("2020-02-15"))
        assert result["x"].to_list() == [2.0]

    @requires_dask
    def test_lazy_dask_frame_filters_and_stays_lazy(self):
        dask_dataframe = pytest.importorskip("dask.dataframe")
        lazy = nw.from_native(self.datetime_native("pandas"), eager_only=True).lazy(backend="dask").to_native()
        result = filter_date_range(lazy, "Date", pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03"))
        assert isinstance(result, dask_dataframe.DataFrame)
        assert result.compute()["x"].tolist() == [2.0, 3.0]


class TestToDatetimeCol:
    @pytest.mark.parametrize("backend", ["pandas", "polars", "pyarrow"])
    def test_calendar_strings_are_cast(self, backend):
        skip_unless_installed(backend)
        frame = make_frame({"t": ["2020-01-01", "2020-02-01"], "x": [1.0, 2.0]}, backend)
        result = to_datetime_col(frame, "t")
        filtered = filter_date_range(result, "t", pd.Timestamp("2020-01-15"), pd.Timestamp("2020-02-15"))
        assert column_values(filtered, "x") == [2.0]

    def test_non_calendar_codes_keep_strings(self):
        pytest.importorskip("polars")
        frame = make_frame({"t": ["2013-S1", "2013-S2"]}, "polars")
        result = to_datetime_col(frame, "t")
        assert result is frame

    def test_non_string_column_is_unchanged(self):
        frame = make_frame({"t": [1, 2]}, "pandas")
        assert to_datetime_col(frame, "t") is frame


class TestConcatFrames:
    @pytest.mark.parametrize("backend", ["pandas", "polars", "pyarrow"])
    def test_vertical_concat(self, backend):
        skip_unless_installed(backend)
        parts = [make_frame({"x": [float(i)]}, backend) for i in range(3)]
        result = concat_frames(parts)
        assert column_values(result, "x") == [0.0, 1.0, 2.0]

    def test_empty_sequence_raises(self):
        with pytest.raises(ValueError, match="at least one frame"):
            concat_frames([])
