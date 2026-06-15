from pandas import DataFrame, DatetimeIndex

from pandas_datareader.base import _BaseReader
from pandas_datareader.io import read_jsdmx


class OECDReader(_BaseReader):
    """Get data for the given dataflow from the OECD SDMX API.

    The ``symbols`` argument is a fully-qualified dataflow reference, ``AGENCY,DATAFLOW,VERSION``,
    optionally followed by a ``/`` and a key selecting specific series, e.g.
    ``"OECD.ELS.SAE,DSD_TUD_CBC@DF_TUD,1.0"`` or
    ``"OECD.ELS.SAE,DSD_TUD_CBC@DF_TUD,1.0/AUS+USA"``. Browse available dataflows at
    https://sdmx.oecd.org/public/rest/dataflow/all/all/latest.
    """

    _format = "json"
    _URL = "https://sdmx.oecd.org/public/rest/data"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.headers = {"Accept": "application/vnd.sdmx.data+json"}

    @property
    def url(self) -> str:
        """API URL."""
        if not isinstance(self.symbols, str):
            raise ValueError("data name must be string")
        flow, _, key = self.symbols.partition("/")
        return f"{self._URL}/{flow}/{key}"

    @property
    def params(self) -> dict:
        """Query parameters requesting a flat all-dimensions JSON cube for the year range."""
        return {
            "startPeriod": self.start.year,
            "endPeriod": self.end.year,
            "dimensionAtObservation": "AllDimensions",
        }

    def _read_lines(self, out: dict) -> DataFrame:
        """Parse the OECD SDMX-JSON response into a DataFrame.

        Parameters
        ----------
        out : dict
            Parsed SDMX-JSON response.

        Returns
        -------
        df : DataFrame
            OECD data for the requested dataflow, indexed by time.
        """
        df = read_jsdmx(out)
        # Non-calendar period codes stay as a string index and can't be sliced by datetime bounds.
        if isinstance(df.index, DatetimeIndex):
            df = df.truncate(self.start, self.end)
        return df
