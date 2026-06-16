import pandas as pd

from pandas_datareader._utils import RemoteDataError
from pandas_datareader.base import _BaseReader
from pandas_datareader.config import get_api_key

AV_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantage(_BaseReader):
    """Base class for all Alpha Vantage queries."""

    _format = "json"

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int | None = None,
        pause: float | None = None,
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
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        api_key : str, optional
            Alpha Vantage API key. Resolved through :func:`pandas_datareader.config.get_api_key`
            (argument, ``options.api_keys['alphavantage']``, ``ALPHAVANTAGE_API_KEY``, then the
            config file). The API key is *required*.

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
        self.api_key = get_api_key("alphavantage", api_key)

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
