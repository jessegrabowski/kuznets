import json
from urllib.parse import urlencode

import pandas as pd

from pandas_datareader.base import _BaseReader

# Data provided for free by IEX
# Data is furnished in compliance with the guidelines promulgated in the IEX
# API terms of service and manual
# See https://iextrading.com/api-exhibit-a/ for additional information
# and conditions of use


class IEX(_BaseReader):
    """Base class for all IEX API services."""

    _format = "json"

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
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
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )

    @property
    def service(self) -> str:
        """Service endpoint. Must be overridden by subclass."""
        raise NotImplementedError("IEX API service not specified.")

    @property
    def url(self) -> str:
        """API URL."""
        qstring = urlencode(self._get_params(self.symbols))
        return f"https://api.iextrading.com/1.0/{self.service}?{qstring}"

    def read(self) -> pd.DataFrame:
        """Read data from IEX.

        Returns
        -------
        df : DataFrame
        """
        df = super().read()
        if isinstance(df, pd.DataFrame):
            df = df.squeeze()
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
        return df

    def _get_params(self, symbols: str | list[str] | None) -> dict:
        """Build query parameters.

        Parameters
        ----------
        symbols : str or list of str, optional
            Ticker symbols.

        Returns
        -------
        params : dict
        """
        p = {}
        if isinstance(symbols, list):
            p["symbols"] = ",".join(symbols)
        elif isinstance(symbols, str):
            p["symbols"] = symbols
        return p

    def _output_error(self, out) -> bool:
        """Interpret non-200 IEX responses.

        Parameters
        ----------
        out : Response
            The raw output from an HTTP request.

        Returns
        -------
        stop : bool
        """
        try:
            content = json.loads(out.text)
        except Exception as exc:
            raise TypeError("Failed to interpret response as JSON.") from exc

        for key, string in content.items():
            e = f"IEX Output error encountered: {string}"
            if key == "error":
                raise Exception(e)

    def _read_lines(self, out: list | dict) -> pd.DataFrame:
        """Parse IEX JSON response.

        Parameters
        ----------
        out : list or dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        # IEX will return a blank line for invalid tickers:
        if isinstance(out, list):
            out = [x for x in out if x is not None]
        return pd.DataFrame(out) if len(out) > 0 else pd.DataFrame()
