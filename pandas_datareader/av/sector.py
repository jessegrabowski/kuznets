import pandas as pd

from pandas_datareader._utils import RemoteDataError
from pandas_datareader.av import AlphaVantage


class AVSectorPerformanceReader(AlphaVantage):
    """
    Get Alpha Vantage Sector Performance data.

    .. versionadded:: 0.7.0

    Parameters
    ----------
    symbols : str or list of str, optional
        Not used by this endpoint.
    retry_count : int, default 3
        Number of times to retry query request.
    pause : float, default 0.1
        Time, in seconds, to pause between consecutive queries.
    session : Session, optional
        ``requests.sessions.Session`` instance to be used.
    api_key : str, optional
        Alpha Vantage API key. If not provided the environmental variable
        ``ALPHAVANTAGE_API_KEY`` is read. The API key is *required*.
    """

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
        DataFrame
        """
        if "Information" in out:
            raise RemoteDataError()
        else:
            out.pop("Meta Data")
        df = pd.DataFrame(out)
        columns = ["RT", "1D", "5D", "1M", "3M", "YTD", "1Y", "3Y", "5Y", "10Y"]
        df.columns = columns
        return df
