import pandas as pd
import pytest

from pandas_datareader import data as web

pytestmark = pytest.mark.stable


class TestEurostat:
    def test_get_ert_h_eur_a(self):
        # Former euro area national currencies vs. euro/ECU, annual data (ert_h_eur_a).
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
