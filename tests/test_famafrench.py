import narwhals.stable.v2 as nw
import pandas as pd
from pandas import testing as tm
import pytest

from pandas_datareader import data as web
from pandas_datareader.famafrench import _URL, get_available_datasets
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import live_or_record, patch_session_get, service_up, tolerate_outage

pytestmark = pytest.mark.stable


class TestFamaFrenchOffline:
    # The real data_library.html is ~250 KB; this is a trimmed sample with the same <a href> shape
    # the scraper relies on. TestFamaFrenchLive checks the live page returns >100 datasets.
    def test_get_available_datasets(self, monkeypatch, datapath):
        pytest.importorskip("lxml")
        patch_session_get(
            monkeypatch,
            {"data_library.html": datapath("data", "famafrench", "data_library.html")},
        )
        avail = get_available_datasets()
        assert "F-F_Research_Data_Factors" in avail
        assert "ME_Breakpoints" in avail

    def test_research_factors_index(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            {"F-F_Research_Data_Factors": datapath("data", "famafrench", "F-F_Research_Data_Factors_CSV.zip")},
        )
        ff = web.DataReader("F-F_Research_Data_Factors", "famafrench")
        assert "DESCR" in ff
        assert len(ff) > 1
        # Monthly table first, annual table second.
        assert ff[0].index.freq.name in ("ME", "M")
        assert ff[1].index.freq.name in ("YE-DEC", "A-DEC")

    def test_daily_factors_index(self, monkeypatch, datapath):
        # Daily files carry 8-digit YYYYMMDD dates and must yield a DatetimeIndex, not the
        # PeriodIndex used for monthly/annual tables. The old reader fed them to the %Y%m branch
        # and died with "unconverted data remains: 01".
        patch_session_get(
            monkeypatch,
            {
                "F-F_Research_Data_Factors_daily": datapath(
                    "data", "famafrench", "F-F_Research_Data_Factors_daily_CSV.zip"
                )
            },
        )
        ff = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench", start="2010-01-01", end="2010-12-31")
        assert isinstance(ff[0].index, pd.DatetimeIndex)
        assert ff[0].index.min() >= pd.Timestamp("2010-01-01")
        assert ff[0].index.max() <= pd.Timestamp("2010-12-31")

    def test_me_breakpoints(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            {"ME_Breakpoints": datapath("data", "famafrench", "ME_Breakpoints_CSV.zip")},
        )
        results = web.DataReader("ME_Breakpoints", "famafrench", start="2010-01-01", end="2010-12-31")
        assert isinstance(results, dict)
        assert results[0].shape == (12, 21)

        exp_index = pd.period_range("2010-01-01", "2010-12-01", freq="M", name="Date")
        tm.assert_index_equal(results[0].index, exp_index)

    def test_prior_2_12_breakpoints(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            {"Prior_2-12_Breakpoints": datapath("data", "famafrench", "Prior_2-12_Breakpoints_CSV.zip")},
        )
        results = web.DataReader("Prior_2-12_Breakpoints", "famafrench", start="2010-01-01", end="2010-12-01")
        assert isinstance(results, dict)
        assert results[0].shape == (12, 22)


@pytest.mark.network
class TestFamaFrenchLive:
    def test_available_datasets_count(self):
        # Not recorded (the HTML index is large); assert the live page yields many datasets.
        if not service_up(_URL + "data_library.html"):
            pytest.skip("Fama-French library unreachable")
        pytest.importorskip("lxml")
        with tolerate_outage():
            assert len(get_available_datasets()) > 100

    def test_research_factors_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"F-F_Research_Data_Factors": datapath("data", "famafrench", "F-F_Research_Data_Factors_CSV.zip")},
            _URL + "data_library.html",
        )
        with tolerate_outage():
            ff = web.DataReader("F-F_Research_Data_Factors", "famafrench")
            assert "DESCR" in ff
            assert ff[0].index.freq.name in ("ME", "M")

    def test_daily_factors_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {
                "F-F_Research_Data_Factors_daily": datapath(
                    "data", "famafrench", "F-F_Research_Data_Factors_daily_CSV.zip"
                )
            },
            _URL + "data_library.html",
        )
        with tolerate_outage():
            ff = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench")
            assert "DESCR" in ff
            assert isinstance(ff[0].index, pd.DatetimeIndex)

    def test_breakpoints_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {
                "ME_Breakpoints": datapath("data", "famafrench", "ME_Breakpoints_CSV.zip"),
                "Prior_2-12_Breakpoints": datapath("data", "famafrench", "Prior_2-12_Breakpoints_CSV.zip"),
            },
            _URL + "data_library.html",
        )
        with tolerate_outage():
            me = web.DataReader("ME_Breakpoints", "famafrench", start="2010-01-01", end="2010-12-31")
            assert me[0].shape == (12, 21)
            prior = web.DataReader("Prior_2-12_Breakpoints", "famafrench", start="2010-01-01", end="2010-12-01")
            assert prior[0].shape == (12, 22)


class TestFamaFrenchBackends:
    # This retires the base-presenter NotImplementedError guard for FamaFrenchReader
    # (plans/narwhals step-06): non-pandas output must succeed, as a dict of native frames.
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_dict_of_native_frames_with_period_start_dates(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(
            monkeypatch,
            {"F-F_Research_Data_Factors": datapath("data", "famafrench", "F-F_Research_Data_Factors_CSV.zip")},
        )
        as_pandas = web.DataReader("F-F_Research_Data_Factors", "famafrench")
        tidy = web.DataReader("F-F_Research_Data_Factors", "famafrench", output_type=output_type)

        assert isinstance(tidy, dict)
        assert set(tidy) == set(as_pandas)
        assert tidy["DESCR"] == as_pandas["DESCR"]

        monthly = as_narwhals(tidy[0])
        assert monthly.columns[0] == "Date"
        assert monthly.schema["Date"] == nw.Datetime
        assert len(monthly) == len(as_pandas[0])
        expected_first = as_pandas[0].index[0].to_timestamp(how="start").to_pydatetime()
        assert monthly["Date"].to_list()[0] == expected_first

        annual = as_narwhals(tidy[1])
        assert len(annual) == len(as_pandas[1])
        assert annual["Date"].to_list()[0].month == 1

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_daily_tables_and_row_parity_after_truncation(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(
            monkeypatch,
            {
                "F-F_Research_Data_Factors_daily": datapath(
                    "data", "famafrench", "F-F_Research_Data_Factors_daily_CSV.zip"
                )
            },
        )
        kwargs = {"start": "2010-01-01", "end": "2010-12-31"}
        as_pandas = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench", **kwargs)
        tidy = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench", output_type=output_type, **kwargs)

        daily = as_narwhals(tidy[0])
        assert daily.schema["Date"] == nw.Datetime
        assert len(daily) == len(as_pandas[0])
        first_column = as_pandas[0].columns[0]
        assert daily[first_column].to_list() == as_pandas[0][first_column].tolist()
