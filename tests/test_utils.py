import datetime as dt
import importlib.util
import sys
import types

import pandas as pd
import pytest

import kuznets.utils
from kuznets.utils import _sanitize_dates, _year_bounds


class TestVersionFallback:
    @staticmethod
    def _utils_loaded_fresh():
        """Execute ``kuznets/utils.py`` into a throwaway module, leaving the imported one alone."""
        spec = importlib.util.spec_from_file_location("_kuznets_utils_probe", kuznets.utils.__file__)
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        return probe

    def test_missing_version_file_degrades_instead_of_raising(self, monkeypatch):
        # A source checkout the build hook has not run in has no _version module; importing must
        # still work, and the agent must not claim a version it cannot resolve.
        monkeypatch.setitem(sys.modules, "kuznets._version", None)
        probe = self._utils_loaded_fresh()

        assert probe.__version__ == "0.0.0+unknown"
        assert probe.DEFAULT_USER_AGENT == "kuznets"

    def test_resolved_version_reaches_the_user_agent(self, monkeypatch):
        stub = types.ModuleType("kuznets._version")
        stub.__version__ = "9.9.9"
        monkeypatch.setitem(sys.modules, "kuznets._version", stub)
        probe = self._utils_loaded_fresh()

        assert probe.__version__ == "9.9.9"
        assert probe.DEFAULT_USER_AGENT == "kuznets/9.9.9"


class TestUtils:
    @pytest.mark.parametrize(
        "input_date",
        [
            "2019-01-01",
            "JAN-01-2010",
            dt.datetime(2019, 1, 1),
            dt.date(2019, 1, 1),
            pd.Timestamp(2019, 1, 1),
        ],
    )
    def test_sanitize_dates(self, input_date):
        expected_start = pd.to_datetime(input_date)
        expected_end = pd.to_datetime(dt.date.today())
        result = _sanitize_dates(input_date, None)
        assert result == (expected_start, expected_end)

    def test_sanitize_dates_int(self):
        start_int = 2018
        end_int = 2019
        expected_start = pd.to_datetime(dt.datetime(start_int, 1, 1))
        expected_end = pd.to_datetime(dt.datetime(end_int, 1, 1))
        assert _sanitize_dates(start_int, end_int) == (expected_start, expected_end)

    def test_sanitize_invalid_dates(self):
        with pytest.raises(ValueError):
            _sanitize_dates(2019, 2018)

        with pytest.raises(ValueError):
            _sanitize_dates("2019-01-01", "2018-01-01")

        with pytest.raises(ValueError):
            _sanitize_dates("20199", None)

    def test_sanitize_dates_defaults(self):
        default_start = pd.to_datetime(dt.date.today() - dt.timedelta(days=365 * 5))
        default_end = pd.to_datetime(dt.date.today())
        assert _sanitize_dates(None, None) == (default_start, default_end)


class TestYearBounds:
    def test_widens_a_partial_range_to_whole_years(self):
        start, end = _year_bounds(pd.Timestamp("2019-06-15"), pd.Timestamp("2021-03-02"))

        assert start == pd.Timestamp("2019-01-01")
        assert end == pd.Timestamp("2021-12-31")

    def test_an_integer_end_year_covers_that_whole_year(self):
        # _sanitize_dates reads a bare year as January 1st, which would otherwise bound a request
        # for 2019 to its first day and drop every sub-annual period after it.
        start, end = _year_bounds(*_sanitize_dates(2019, 2019))

        assert (start, end) == (pd.Timestamp("2019-01-01"), pd.Timestamp("2019-12-31"))
