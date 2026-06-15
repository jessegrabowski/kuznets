from pandas import DataFrame, DatetimeIndex

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

    def _read_lines(self, out: dict) -> DataFrame:
        """Parse the Eurostat JSON-stat response into a DataFrame.

        Parameters
        ----------
        out : dict
            Parsed JSON-stat response.

        Returns
        -------
        df : DataFrame
            Eurostat data for the requested symbol, indexed by time.
        """
        df = read_jstat(out)
        # Non-calendar period codes (e.g. semesters) stay as a string index and can't be sliced
        # against datetime bounds; the server-side year filter already constrains those.
        if isinstance(df.index, DatetimeIndex):
            df = df.truncate(self.start, self.end)
        return df
