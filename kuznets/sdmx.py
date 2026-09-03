from collections.abc import Mapping
from io import StringIO
from typing import NamedTuple

from pandas import DataFrame, DatetimeIndex
import requests

from kuznets.base import _BaseReader
from kuznets.io import (
    DataStructure,
    StructureRef,
    build_sdmx_key,
    read_data_structure,
    read_dataflow_ref,
    read_dataflow_structure_ref,
    read_structure_specific,
)
from kuznets.output import PANDAS, filter_date_range
from kuznets.typing import DateLike, Frame, Headers, Symbols
from kuznets.utils import _year_bounds

# Resolved structures keyed by service root, agency and dataflow. A dataflow's shape changes only
# when the service republishes it, so resolving it once per process spares every later read the two
# structure requests.
_STRUCTURE_CACHE: dict[tuple[str, str, str], "ResolvedDataflow"] = {}


class ResolvedDataflow(NamedTuple):
    """A dataflow addressed and shaped: how to request it, and the dimensions its key needs."""

    flow: StructureRef
    structure: DataStructure


def clear_structure_cache() -> None:
    """Forget every resolved dataflow, so the next read re-requests its structure."""
    _STRUCTURE_CACHE.clear()


class _SdmxDataflowReader(_BaseReader):
    """Read one dataflow from an SDMX 2.1 REST service, resolving its shape before requesting data.

    A dataflow is served without its shape, so each read resolves the dataflow's own reference and
    its data structure first and builds a positional key from the dimensions the service declares.
    Subclasses supply ``_SERVICE``; everything else is discovered.
    """

    _SERVICE: str = ""

    def __init__(
        self,
        dataflow: str,
        selections: Mapping[str, Symbols | None] | None = None,
        agency: str = "all",
        start: DateLike | None = None,
        end: DateLike | None = None,
        retry_count: int | None = None,
        pause: float | None = None,
        timeout: float | None = None,
        session: requests.Session | None = None,
        headers: Headers | None = None,
        output_type: str = "pandas",
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        dataflow : str
            Identifier of the dataflow to read, e.g. ``'CPI'``.
        selections : mapping of str to str or list of str, optional
            Codes to restrict dimensions to, keyed by the dimension identifier the service uses. A
            dimension left out, or mapped to None, is requested unrestricted. Default None, every
            dimension unrestricted.
        agency : str, optional
            Agency maintaining the dataflow. Default ``'all'``, which lets the service resolve it
            and spares the caller having to know which agency publishes what.
        start : str, int, date, datetime, or Timestamp, optional
            Start of the data series. Only the year is used.
        end : str, int, date, datetime, or Timestamp, optional
            End of the data series, inclusive. Only the year is used.
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        timeout : float, optional
            Time, in seconds, to wait for server response. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        headers : dict, optional
            Headers applied to every request, merged over ``options.headers`` and the config file.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        if not dataflow:
            raise ValueError(f"{type(self).__name__} requires a dataflow identifier")

        super().__init__(
            symbols=None,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            timeout=timeout,
            session=session,
            headers=headers,
            output_type=output_type,
        )
        self.dataflow = dataflow
        self.agency = agency
        self.selections = dict(selections or {})
        self._resolved: ResolvedDataflow | None = None

    @property
    def url(self) -> str:
        """Data URL once the dataflow is resolved, and the service root before that."""
        if self._resolved is None:
            return self._SERVICE
        flow = self._resolved.flow
        return f"{self._SERVICE}/data/{flow.agency},{flow.id},{flow.version}/{self.key}"

    @property
    def key(self) -> str:
        """Positional key selecting the requested series, in the order the service declares."""
        dimensions = self._require_resolved().structure.dimensions
        unknown = sorted(set(self.selections) - set(dimensions))
        if unknown:
            raise ValueError(
                f"dataflow {self.dataflow!r} declares no dimension named {', '.join(unknown)}; "
                f"its dimensions are {', '.join(dimensions)}"
            )
        return build_sdmx_key(self.selections.get(dimension) for dimension in dimensions)

    @property
    def params(self) -> dict:
        """Query parameters bounding the request to the requested year range."""
        return {"startPeriod": self.start.year, "endPeriod": self.end.year}

    def _read_lines(self, out: StringIO) -> str:
        """Pass the XML response body through as the payload for the presenters."""
        return out.read()

    def _read_core(self) -> str:
        """Resolve the dataflow's shape, then fetch the data it addresses."""
        try:
            self._resolved = self._resolve()
            return self._read_one_data(self.url, self.params)
        finally:
            self.close()

    def _resolve(self) -> ResolvedDataflow:
        """Resolve the dataflow's own reference and its data structure, once per process."""
        cache_key = (self._SERVICE, self.agency, self.dataflow)
        cached = _STRUCTURE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        record = self._read_one_data(f"{self._SERVICE}/dataflow/{self.agency}/{self.dataflow}", None)
        flow = read_dataflow_ref(record)
        reference = read_dataflow_structure_ref(record)
        document = self._read_one_data(
            f"{self._SERVICE}/datastructure/{reference.agency}/{reference.id}/{reference.version}", None
        )
        resolved = ResolvedDataflow(flow=flow, structure=read_data_structure(document))
        _STRUCTURE_CACHE[cache_key] = resolved
        return resolved

    def _require_resolved(self) -> ResolvedDataflow:
        """Return the resolved dataflow, or explain that nothing has read its structure yet."""
        if self._resolved is None:
            raise RuntimeError(f"the shape of dataflow {self.dataflow!r} is not known until it is read")
        return self._resolved

    def _column_names(self) -> dict[str, str]:
        """Map each SDMX dimension to the column name it is presented under."""
        structure = self._require_resolved().structure
        return {dimension: dimension for dimension in structure.dimensions} | {structure.time_dimension: "period"}

    def _present_pandas(self, payload: str) -> DataFrame:
        """Pivot the observations into the wide time-indexed frame, truncated to the range."""
        df = read_structure_specific(payload, self._column_names(), PANDAS)
        if isinstance(df.index, DatetimeIndex):
            df = df.truncate(*_year_bounds(self.start, self.end))
        return df

    def _present_tidy(self, payload: str) -> Frame:
        """Build the long native frame and filter it to the requested range."""
        frame = read_structure_specific(payload, self._column_names(), self.output_type)
        start, end = _year_bounds(self.start, self.end)
        return filter_date_range(frame, "period", start, end)
