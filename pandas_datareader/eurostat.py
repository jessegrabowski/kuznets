from pandas import DataFrame, DatetimeIndex

from pandas_datareader._output import filter_date_range
from pandas_datareader.base import _BaseReader
from pandas_datareader.io import read_jstat


class EurostatReader(_BaseReader):
    """Get data for the given name from Eurostat."""

    _format = "json"
    _URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

    @property
    def url(self) -> str:
        """API URL."""
        if not isinstance(self.symbols, str):
            raise ValueError("data name must be string")
        return f"{self._URL}/{self.symbols}"

    @property
    def params(self) -> dict:
        """Query parameters bounding the request to the requested year range."""
        return {
            "format": "JSON",
            "lang": "EN",
            "sinceTimePeriod": self.start.year,
            "untilTimePeriod": self.end.year,
        }

    def _read_lines(self, out: dict) -> dict:
        """Pass the parsed JSON-stat response through as the payload for the presenters."""
        return out

    def _present_pandas(self, payload: dict) -> DataFrame:
        """Pivot the observations into the wide time-indexed frame, truncated to the range."""
        df = read_jstat(payload)
        # Non-calendar period codes (e.g. semesters) stay as a string index and can't be sliced
        # against datetime bounds; the server-side year filter already constrains those.
        if isinstance(df.index, DatetimeIndex):
            df = df.truncate(self.start, self.end)
        return df

    def _present_tidy(self, payload: dict):
        """Build the long native frame and filter it to the requested range."""
        frame = read_jstat(payload, output_type=self.output_type)
        return filter_date_range(frame, start=self.start, end=self.end)
