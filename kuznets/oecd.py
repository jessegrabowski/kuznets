from pandas import DataFrame, DatetimeIndex

from kuznets._output import filter_date_range
from kuznets.base import _BaseReader
from kuznets.io import read_jsdmx


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

    def _read_lines(self, out: dict) -> dict:
        """Pass the parsed SDMX-JSON response through as the payload for the presenters."""
        return out

    def _present_pandas(self, payload: dict) -> DataFrame:
        """Pivot the observations into the wide time-indexed frame, truncated to the range."""
        df = read_jsdmx(payload)
        # Non-calendar period codes stay as a string index and can't be sliced by datetime bounds.
        if isinstance(df.index, DatetimeIndex):
            df = df.truncate(self.start, self.end)
        return df

    def _present_tidy(self, payload: dict):
        """Build the long native frame and filter it to the requested range."""
        frame = read_jsdmx(payload, output_type=self.output_type)
        return filter_date_range(frame, start=self.start, end=self.end)
