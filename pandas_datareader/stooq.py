from pandas_datareader.base import _DailyBaseReader


class StooqDailyReader(_DailyBaseReader):
    """
    Get historical stock prices from Stooq.

    Parameters
    ----------
    symbols : str, list of str, or DataFrame
        Single stock symbol (ticker), list of symbols, or DataFrame with
        index containing stock symbols.
    start : str, int, date, datetime, or Timestamp, optional
        Starting date. Defaults to 5 years before current date.
    end : str, int, date, datetime, or Timestamp, optional
        Ending date.
    retry_count : int, default 3
        Number of times to retry query request.
    pause : float, default 0.1
        Time, in seconds, to pause between consecutive queries of chunks.
    chunksize : int, default 25
        Number of symbols to download consecutively before initiating pause.
    session : Session, optional
        ``requests.sessions.Session`` instance to be used.

    Notes
    -----
    See `Stooq <https://stooq.com>`__
    """

    @property
    def url(self) -> str:
        """API URL."""
        return "https://stooq.com/q/d/l/"

    def _get_params(self, symbol: str, country: str = "US") -> dict:
        """Build query parameters for a given symbol.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        country : str, default "US"
            Country suffix to append if not already present.

        Returns
        -------
        dict
        """
        symbol_parts = symbol.split(".")
        if not symbol.startswith("^"):
            if len(symbol_parts) == 1:
                symbol = ".".join([symbol, country])
            elif symbol_parts[1].lower() == "pl":
                symbol = symbol_parts[0]
            else:
                if symbol_parts[1].lower() not in [
                    "de",
                    "hk",
                    "hu",
                    "jp",
                    "uk",
                    "us",
                    "f",
                    "b",
                ]:
                    symbol = ".".join([symbol, "US"])

        params = {
            "s": symbol,
            "i": self.freq or "d",
            "d1": self.start.strftime("%Y%m%d"),
            "d2": self.end.strftime("%Y%m%d"),
        }

        return params
