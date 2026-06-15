from datetime import datetime

import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError

pytestmark = pytest.mark.stable

# OECD trade union density dataflow.
TUD = "OECD.ELS.SAE,DSD_TUD_CBC@DF_TUD,1.0"


class TestOECD:
    def test_get_tud(self):
        df = web.DataReader(TUD, "oecd", start=datetime(2000, 1, 1), end=datetime(2005, 1, 1))

        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.min().year >= 2000
        assert df.index.max().year <= 2005

        au = (
            df.xs("Australia", axis=1, level="Reference area")
            .xs("Trade union density", axis=1, level="Measure")
            .iloc[:, 0]
        )
        assert au.loc["2000"].iloc[0] == pytest.approx(24.7, abs=0.1)

    def test_oecd_invalid_symbol(self):
        with pytest.raises(RemoteDataError):
            web.DataReader("OECD,INVALID_FLOW,1.0", "oecd")

        with pytest.raises(ValueError):
            web.DataReader(1234, "oecd")
