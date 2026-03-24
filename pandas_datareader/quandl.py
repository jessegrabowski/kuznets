import os
import re

from pandas import DataFrame

from pandas_datareader.base import _DailyBaseReader


class QuandlReader(_DailyBaseReader):
    """Get historical stock prices from Quandl."""

    _BASE_URL = "https://www.quandl.com/api/v3/datasets/"

    def __init__(
        self,
        symbols: str,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        chunksize: int = 25,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str
            Possible formats:

            1. ``DB/SYM`` — the Quandl "codes": ``DB`` is the database name,
               ``SYM`` is a ticker-symbol-like Quandl abbreviation for a particular security.
            2. ``SYM.CC`` — ``SYM`` is the same symbol and ``CC`` is an ISO
               country code. Will try to map to the best single Quandl database for that country.
               Beware of ambiguous symbols (different securities per country)!

            Only a single string is accepted.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Defaults to 20 years before current date.
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
        api_key : str, optional
            Quandl API key. If not provided the environmental variable ``QUANDL_API_KEY`` is read.
            The API key is *required*.
        """
        super().__init__(symbols, start, end, retry_count, pause, session, chunksize)
        if api_key is None:
            api_key = os.getenv("QUANDL_API_KEY")
        if not api_key or not isinstance(api_key, str):
            raise ValueError(
                "The Quandl API key must be provided either "
                "through the api_key variable or through the "
                "environmental variable QUANDL_API_KEY."
            )
        self.api_key = api_key

    @property
    def url(self) -> str:
        """API URL."""
        symbol = self.symbols if isinstance(self.symbols, str) else self.symbols[0]
        mm = self._fullmatch(r"([A-Z0-9]+)(([/\.])([A-Z0-9_]+))?", symbol)
        assert mm, f"Symbol '{symbol}' must conform to Quandl convention 'DB/SYM'"
        datasetname = "WIKI"
        if not mm.group(2):
            # bare symbol:
            datasetname = "WIKI"  # default; symbol stays itself
        elif mm.group(3) == "/":
            # --- normal Quandl DB/SYM convention:
            symbol = mm.group(4)
            datasetname = mm.group(1)
        elif mm.group(3) == ".":
            # secondary convention SYM.CountryCode:
            symbol = mm.group(1)
            datasetname = self._db_from_countrycode(mm.group(4))
        params = {
            "start_date": self.start.strftime("%Y-%m-%d"),
            "end_date": self.end.strftime("%Y-%m-%d"),
            "order": "asc",
            "api_key": self.api_key,
        }
        paramstring = "&".join([f"{k}={v}" for k, v in params.items()])
        url = "{url}{dataset}/{symbol}.csv?{params}"
        return url.format(url=self._BASE_URL, dataset=datasetname, symbol=symbol, params=paramstring)

    def _fullmatch(self, regex: str, string: str, flags: int = 0) -> re.Match | None:
        """Emulate python-3.4 ``re.fullmatch()``.

        Parameters
        ----------
        regex : str
            Regular expression pattern.
        string : str
            String to match.
        flags : int, default 0
            Regex flags.

        Returns
        -------
        Match or None
        """
        return re.match("(?:" + regex + r")\Z", string, flags=flags)

    _COUNTRYCODE_TO_DATASET = {
        # https://www.quandl.com/data/EURONEXT-Euronext-Stock-Exchange
        "BE": "EURONEXT",
        # https://www.quandl.com/data/HKEX-Hong-Kong-Exchange
        "CN": "HKEX",
        # https://www.quandl.com/data/SSE-Boerse-Stuttgart
        "DE": "SSE",
        "FR": "EURONEXT",
        # https://www.quandl.com/data/NSE-National-Stock-Exchange-of-India
        "IN": "NSE",
        # https://www.quandl.com/data/TSE-Tokyo-Stock-Exchange
        "JP": "TSE",
        "NL": "EURONEXT",
        "PT": "EURONEXT",
        # https://www.quandl.com/data/LSE-London-Stock-Exchange
        "UK": "LSE",
        # https://www.quandl.com/data/WIKI-Wiki-EOD-Stock-Prices
        "US": "WIKI",
    }

    def _db_from_countrycode(self, code: str) -> str:
        """Map an ISO country code to a Quandl dataset name.

        Parameters
        ----------
        code : str
            Two-letter ISO country code.

        Returns
        -------
        db : str
            Quandl dataset name.
        """
        assert code in self._COUNTRYCODE_TO_DATASET, f"No Quandl dataset known for country code '{code}'"
        return self._COUNTRYCODE_TO_DATASET[code]

    def _get_params(self, symbol: str) -> dict:
        """Return parameters for an API call (unused, URL contains params).

        Parameters
        ----------
        symbol : str
            Ticker symbol.

        Returns
        -------
        params : dict
            Empty dict.
        """
        return {}

    def read(self) -> DataFrame:
        """Read data from Quandl.

        Returns
        -------
        df : DataFrame
            Columns are cleaned (whitespace, punctuation removed).
        """
        df = super().read()
        df.rename(
            columns=lambda n: (
                n.replace(" ", "")
                .replace(".", "")
                .replace("/", "")
                .replace("%", "")
                .replace("(", "")
                .replace(")", "")
                .replace("'", "")
                .replace("-", "")
            ),
            inplace=True,
        )
        return df
