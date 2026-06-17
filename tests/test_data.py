import pytest

from pandas_datareader.data import DataReader

pytestmark = pytest.mark.stable


class TestDataReader:
    def test_unknown_source_raises(self):
        with pytest.raises(NotImplementedError):
            DataReader("NA", "NA")
