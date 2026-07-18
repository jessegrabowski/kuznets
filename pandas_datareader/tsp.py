from pandas import DataFrame
import requests

from pandas_datareader.base import _BaseReader


class TSPReader(_BaseReader):
    """Get historical TSP (Thrift Savings Plan) fund prices."""

    all_symbols = frozenset(
        (
            "L Income",
            "L 2025",
            "L 2030",
            "L 2035",
            "L 2040",
            "L 2045",
            "L 2050",
            "L 2055",
            "L 2060",
            "L 2065",
            "G Fund",
            "F Fund",
            "C Fund",
            "S Fund",
            "I Fund",
        )
    )

    def __init__(
        self,
        symbols=all_symbols,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        output_type: str = "pandas",
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str, list of str, or frozenset, optional
            Single fund name, list of fund names, or default ``all_symbols``.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Defaults to 5 years before current date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between consecutive queries.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
        )
        self._format = "string"

    @property
    def url(self) -> str:
        """API URL."""
        return "https://secure.tsp.gov/components/CORS/getSharePricesRaw.html"

    def _read_core(self) -> DataFrame:
        """Fetch TSP fund price data.

        Returns
        -------
        df : DataFrame
        """
        df = super()._read_core()
        df.columns = (x.strip() for x in df.columns)
        df.drop(columns=self.all_symbols - set(self.symbols), inplace=True)
        return df

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        return {
            "startdate": self.start.strftime("%Y%m%d"),
            "enddate": self.end.strftime("%Y%m%d"),
            "download": "0",
            "Lfunds": "1",
            "InvFunds": "1",
        }

    @staticmethod
    def _sanitize_response(response: requests.Response) -> str:
        """Clean up the response string.

        Parameters
        ----------
        response : Response
            Raw HTTP response.

        Returns
        -------
        content : str
        """
        text = response.text.strip()
        if text[-1] == ",":
            return text[0:-1]
        return text
