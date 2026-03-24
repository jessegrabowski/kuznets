import os

import pandas as pd

from pandas_datareader._utils import RemoteDataError
from pandas_datareader.base import _BaseReader

AV_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantage(_BaseReader):
    """Base class for all Alpha Vantage queries."""

    _format = "json"

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str, optional
            String symbol or list of symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, of the pause between retries.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        api_key : str, optional
            Alpha Vantage API key. If not provided the environmental variable
            ``ALPHAVANTAGE_API_KEY`` is read. The API key is *required*.

        Notes
        -----
        See `Alpha Vantage <https://www.alphavantage.co/>`__
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )
        if api_key is None:
            api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key or not isinstance(api_key, str):
            raise ValueError(
                "The AlphaVantage API key must be provided "
                "either through the api_key variable or "
                "through the environment variable "
                "ALPHAVANTAGE_API_KEY"
            )
        self.api_key = api_key

    @property
    def url(self) -> str:
        """API URL."""
        return AV_BASE_URL

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        return {"function": self.function, "apikey": self.api_key}

    @property
    def function(self) -> str:
        """Alpha Vantage endpoint function. Must be overridden in subclass."""
        raise NotImplementedError

    @property
    def data_key(self) -> str:
        """Key of data returned from Alpha Vantage. Must be overridden in subclass."""
        raise NotImplementedError

    def _read_lines(self, out: dict) -> pd.DataFrame:
        """Parse Alpha Vantage JSON response.

        Parameters
        ----------
        out : dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        try:
            df = pd.DataFrame.from_dict(out[self.data_key], orient="index")
        except KeyError as exc:
            if "Error Message" in out:
                raise ValueError(
                    f"The requested symbol {self.symbols} could not be retrieved. Check valid ticker."
                ) from exc
            else:
                raise RemoteDataError(
                    f" Their was an issue from the data vendor side, here is their response: {out}"
                ) from exc
        df = df[sorted(df.columns)]
        df.columns = [id[3:] for id in df.columns]
        return df
