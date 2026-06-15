import os

import pandas as pd
import pytest

from pandas_datareader.io import read_jsdmx

pytestmark = pytest.mark.stable


@pytest.fixture
def dirpath(datapath):
    return datapath("io", "data")


def test_read_oecd_sdmx_json(dirpath):
    # OECD trade union density, captured from the SDMX 2.1 API as SDMX-JSON 2.0.
    result = read_jsdmx(os.path.join(dirpath, "jsdmx", "oecd_tud.json"))
    assert isinstance(result, pd.DataFrame)

    assert isinstance(result.index, pd.DatetimeIndex)
    assert list(result.index.year) == [2009, 2010]
    assert result.columns.names == ["Reference area", "Measure", "Unit of measure"]

    au = result.xs("Australia", axis=1, level="Reference area").iloc[:, 0]
    assert au.loc["2009"].iloc[0] == pytest.approx(19.5, abs=0.5)
