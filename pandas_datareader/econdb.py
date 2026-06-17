import pandas as pd

from pandas_datareader.base import _BaseReader


class EcondbReader(_BaseReader):
    """Get data from the EconDB API.

    .. versionadded:: 0.5.0
    """

    _URL = "https://www.econdb.com/api/series/"
    _format = None
    _show = "labels"

    def __init__(
        self,
        symbols: str,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        freq: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str
            Can be in two different formats:

            1. ``'ticker=<code>'`` for fetching a single series, where
               ``<code>`` is, e.g., ``CPIUS`` for the series at
               https://www.econdb.com/series/CPIUS/
            2. ``'dataset=<dataset>&<params>'`` for fetching a full or
               filtered subset of a dataset, like the one at
               https://www.econdb.com/dataset/ABS_GDP. After choosing
               the desired filters, the correctly formatted query string can be easily generated
               from that dataset's page by using the Export function and choosing Pandas Python3.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between consecutive queries of chunks.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Not used.
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            freq=freq,
        )
        params = dict(s.split("=") for s in self.symbols.split("&"))
        if "from" in params and not start:
            self.start = pd.to_datetime(params["from"], format="%Y-%m-%d")
        if "to" in params and not end:
            self.end = pd.to_datetime(params["to"], format="%Y-%m-%d")

    @property
    def url(self) -> str:
        """API URL."""
        if not isinstance(self.symbols, str):
            raise ValueError("data name must be string")

        return f"{self._URL}?{self.symbols}&format=json&page_size=500&expand=both"

    def read(self) -> pd.DataFrame:
        """Read data from the EconDB API.

        Returns
        -------
        df : DataFrame
            Requested time series data.
        """
        # Route through _get_response so a non-200 (e.g. the 401 the API now returns without
        # credentials) raises RemoteDataError instead of a confusing KeyError on ``["results"]``.
        results = self._get_response(self.url).json()["results"]
        df = pd.DataFrame({"dates": []}).set_index("dates")

        if self._show == "labels":

            def show_func(x):
                return x[x.find(":") + 1 :]

        elif self._show == "codes":

            def show_func(x):
                return x[: x.find(":")]

        unique_keys = {k for s in results for k in s["additional_metadata"]}
        for entry in results:
            series = pd.DataFrame(entry["data"])[["dates", "values"]].set_index("dates")
            head = entry["additional_metadata"]
            for k in unique_keys:
                if k not in head:
                    head[k] = "-1:None"
            if head != "":  # this additional metadata is not blank
                series.columns = pd.MultiIndex.from_tuples(
                    [[show_func(x) for x in head.values()]],
                    names=[show_func(x) for x in head.keys()],
                )
            else:
                series.rename(columns={"values": entry["ticker"]}, inplace=True)

            if not df.empty:
                df = df.merge(series, how="outer", left_index=True, right_index=True)
            else:
                df = series
        if df.shape[0] > 0:
            df.index = pd.to_datetime(df.index, errors="coerce")
        df.index.name = "TIME_PERIOD"
        df = df.truncate(self.start, self.end)
        return df
