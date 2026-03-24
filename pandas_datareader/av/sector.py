import pandas as pd

from pandas_datareader._utils import RemoteDataError
from pandas_datareader.av import AlphaVantage


class AVSectorPerformanceReader(AlphaVantage):
    """Get Alpha Vantage Sector Performance data."""

    @property
    def function(self) -> str:
        """Alpha Vantage endpoint function."""
        return "SECTOR"

    def _read_lines(self, out: dict) -> pd.DataFrame:
        """Parse Alpha Vantage sector performance JSON response.

        Parameters
        ----------
        out : dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        if "Information" in out:
            raise RemoteDataError()
        else:
            out.pop("Meta Data")
        df = pd.DataFrame(out)
        columns = ["RT", "1D", "5D", "1M", "3M", "YTD", "1Y", "3Y", "5Y", "10Y"]
        df.columns = columns
        return df
