import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader.eurostat import EurostatReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import live_or_record, patch_session_get, tolerate_outage

pytestmark = pytest.mark.stable


class TestEurostatOffline:
    def test_exchange_rates_are_parsed(self, monkeypatch, datapath):
        # Former euro area national currencies vs. euro/ECU, annual data (ert_h_eur_a).
        patch_session_get(monkeypatch, {"eurostat": datapath("data", "eurostat", "ert_h_eur_a.json")})

        df = web.DataReader(
            "ert_h_eur_a",
            "eurostat",
            start=pd.Timestamp("2009-01-01"),
            end=pd.Timestamp("2010-01-01"),
        )
        assert isinstance(df.index, pd.DatetimeIndex)

        # The Italian lira's irrevocable conversion rate to the euro is a fixed constant.
        lira = df.xs("Italian lira", axis=1, level="Currency")
        avg = lira.xs("Average", axis=1, level="Statistical information").iloc[:, 0]
        assert avg.loc["2009"].iloc[0] == pytest.approx(1936.27, abs=0.01)
        assert avg.loc["2010"].iloc[0] == pytest.approx(1936.27, abs=0.01)


@pytest.mark.network
class TestEurostatLive:
    def test_exchange_rates_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"eurostat": datapath("data", "eurostat", "ert_h_eur_a.json")},
            EurostatReader._URL,
        )
        with tolerate_outage():
            df = web.DataReader(
                "ert_h_eur_a",
                "eurostat",
                start=pd.Timestamp("2009-01-01"),
                end=pd.Timestamp("2010-01-01"),
            )
            assert isinstance(df.index, pd.DatetimeIndex)
            assert "Currency" in df.columns.names
            assert len(df) > 0


class TestEurostatBackends:
    # This retires the base-presenter NotImplementedError guard for EurostatReader (plans/narwhals
    # step-04): non-pandas output must succeed, as one row per observation.
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_long_schema_and_value_parity(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"eurostat": datapath("data", "eurostat", "ert_h_eur_a.json")})

        kwargs = {"start": pd.Timestamp("2009-01-01"), "end": pd.Timestamp("2010-01-01")}
        wide = web.DataReader("ert_h_eur_a", "eurostat", **kwargs)
        tidy = as_narwhals(web.DataReader("ert_h_eur_a", "eurostat", output_type=output_type, **kwargs))

        assert tidy.columns[-1] == "value"
        assert "Currency" in tidy.columns
        assert any(dtype == nw.Datetime for dtype in tidy.schema.values())
        assert len(tidy) == int(wide.notna().sum().sum())
        assert sum(tidy["value"].to_list()) == pytest.approx(float(wide.sum().sum()))
