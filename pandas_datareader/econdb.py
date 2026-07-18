import pandas as pd

from pandas_datareader._output import filter_date_range, make_frame
from pandas_datareader.base import _BaseReader
from pandas_datareader.io.util import _parse_period_code


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
        output_type: str = "pandas",
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
            freq=freq,
            output_type=output_type,
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

    def _read_core(self) -> list:
        """Fetch the raw series entries from the EconDB API.

        Returns
        -------
        results : list of dict
            One entry per series, each carrying ``data`` and ``additional_metadata``.
        """
        # Route through _get_response so a non-200 (e.g. the 401 the API now returns without
        # credentials) raises RemoteDataError instead of a confusing KeyError on ``["results"]``.
        return self._get_response(self.url).json()["results"]

    def _show_func(self, text: str) -> str:
        if self._show == "labels":
            return text[text.find(":") + 1 :]
        return text[: text.find(":")]

    def _present_pandas(self, results: list) -> pd.DataFrame:
        """Merge the series into the wide frame with MultiIndex metadata columns."""
        show_func = self._show_func
        df = pd.DataFrame({"dates": []}).set_index("dates")

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

    def _present_tidy(self, results: list):
        """One row per observation: metadata dimension columns, ``TIME_PERIOD``, and ``value``."""
        records = []
        unique_keys = {k for s in results for k in s["additional_metadata"]}
        for entry in results:
            head = dict(entry["additional_metadata"]) if entry["additional_metadata"] != "" else {}
            for key in unique_keys:
                head.setdefault(key, "-1:None")
            dimensions = {self._show_func(key): self._show_func(value) for key, value in head.items()}
            if not dimensions:
                dimensions = {"ticker": entry["ticker"]}
            for date_code, value in zip(entry["data"]["dates"], entry["data"]["values"], strict=True):
                records.append({**dimensions, "TIME_PERIOD": date_code, "value": value})
        # All-or-nothing datetime parsing keeps the column's dtype homogeneous per response.
        parsed = [_parse_period_code(record["TIME_PERIOD"]) for record in records]
        if records and all(timestamp is not None for timestamp in parsed):
            for record, timestamp in zip(records, parsed, strict=True):
                record["TIME_PERIOD"] = timestamp
        frame = make_frame(records, self.output_type)
        return filter_date_range(frame, "TIME_PERIOD", self.start, self.end)
