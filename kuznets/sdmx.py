from collections.abc import Iterable, Mapping, Sequence
import difflib
from io import StringIO
from typing import NamedTuple

from pandas import DataFrame, DatetimeIndex
import requests

from kuznets.base import _BaseReader
from kuznets.io import (
    DataStructure,
    StructureRef,
    build_sdmx_key,
    read_codelist,
    read_data_structure,
    read_dataflow_ref,
    read_dataflow_structure_ref,
    read_structure_specific,
)
from kuznets.output import PANDAS, filter_date_range, is_empty
from kuznets.typing import DateLike, Frame, Headers, Symbols
from kuznets.utils import RemoteDataError, _year_bounds

# Resolved structures keyed by service root, agency and dataflow. A dataflow's shape changes only
# when the service republishes it, so resolving it once per process spares every later read the two
# structure requests.
_STRUCTURE_CACHE: dict[tuple[str, str, str], "ResolvedDataflow"] = {}


# Codes per codelist, keyed by service root and the codelist's own reference. Validating a
# selection needs only membership, and a codelist is large enough that refetching it per read is
# the difference between one request and one per dimension.
_CODELIST_CACHE: dict[tuple[str, str, str, str], frozenset[str]] = {}


class ResolvedDataflow(NamedTuple):
    """A dataflow addressed and shaped: how to request it, and the dimensions its key needs."""

    flow: StructureRef
    structure_ref: StructureRef
    structure: DataStructure
    children_requested: bool = False


def clear_structure_cache() -> None:
    """Forget every resolved dataflow and codelist, so the next read re-requests them."""
    _STRUCTURE_CACHE.clear()
    _CODELIST_CACHE.clear()


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
        self._validated: set[str] = set()

    @property
    def url(self) -> str:
        """Data URL once the dataflow's shape is known, and the service root before that."""
        resolved = self._resolved or self._static_structure()
        if resolved is None:
            return self._SERVICE
        flow = resolved.flow
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
        """Resolve the dataflow's shape, check the selection against it, then fetch the data."""
        try:
            self._resolved = self._resolve()
            self._validated = self._validate_selections(self._resolved)
            return self._read_one_data(self.url, self.params)
        finally:
            self.close()

    def _static_structure(self) -> ResolvedDataflow | None:
        """The dataflow's shape when a subclass already knows it, sparing the structure requests.

        Default None, meaning the shape is discovered. A subclass fixing one dataflow can return it
        instead, at the cost of the codelists that discovery would have brought with it.
        """
        return None

    def _resolve(self) -> ResolvedDataflow:
        """Resolve the dataflow's reference and data structure, once per process."""
        static = self._static_structure()
        if static is not None:
            return static

        cache_key = (self._SERVICE, self.agency, self.dataflow)
        resolved = _STRUCTURE_CACHE.get(cache_key)
        if resolved is None:
            record = self._read_one_data(f"{self._SERVICE}/dataflow/{self.agency}/{self.dataflow}", None)
            resolved = self._read_structure(read_dataflow_ref(record), read_dataflow_structure_ref(record))

        # Services disagree on where a codelist reference lives. The ILO puts it on the dimension, so
        # the data structure alone carries it; the IMF puts it on the concept, which only arrives
        # with the concept schemes. Asking for those unconditionally would cost the ILO 1.4MB.
        if not resolved.children_requested and self._dimensions_missing_codelists(resolved):
            resolved = self._read_structure(resolved.flow, resolved.structure_ref, children=True)

        _STRUCTURE_CACHE[cache_key] = resolved
        return resolved

    def _read_structure(
        self, flow: StructureRef, reference: StructureRef, *, children: bool = False
    ) -> ResolvedDataflow:
        """Fetch and parse a data structure, optionally with the concept schemes it references."""
        document = self._read_one_data(
            f"{self._SERVICE}/datastructure/{reference.agency}/{reference.id}/{reference.version}",
            {"references": "children"} if children else None,
        )
        return ResolvedDataflow(flow, reference, read_data_structure(document), children_requested=children)

    def _dimensions_missing_codelists(self, resolved: ResolvedDataflow) -> set[str]:
        """Name the restricted dimensions whose codelist the current structure does not resolve."""
        declared = set(resolved.structure.dimensions)
        return {name for name in self.selections if name in declared and name not in resolved.structure.codelists}

    def _validate_selections(self, resolved: ResolvedDataflow) -> set[str]:
        """Reject codes the service does not list, and report which dimensions could be checked.

        A dimension whose codelist the service does not resolve is skipped rather than failed, so
        validation is partial and the returned set is how partial.
        """
        validated = set()
        for dimension, selection in self.selections.items():
            reference = resolved.structure.codelists.get(dimension)
            if reference is None or selection is None:
                continue
            codes = self._codelist(reference)
            unknown = [code for code in _as_codes(selection) if code not in codes]
            if unknown:
                raise ValueError(self._unknown_code_message(dimension, reference, unknown, codes))
            validated.add(dimension)
        return validated

    def _unknown_code_message(
        self, dimension: str, reference: StructureRef, unknown: list[str], codes: frozenset[str]
    ) -> str:
        """Explain which codes the dimension does not accept, suggesting near misses where there are any."""
        message = f"{dimension} has no code {', '.join(repr(code) for code in unknown)} in codelist {reference.id}"
        ordered = sorted(codes)
        suggestions = list(dict.fromkeys(match for code in unknown for match in _nearest_codes(code, ordered)))
        if suggestions:
            return f"{message}; did you mean {', '.join(repr(match) for match in suggestions)}?"
        return f"{message}, which lists {len(codes)} codes"

    def _codelist(self, reference: StructureRef) -> frozenset[str]:
        """Fetch the codes a codelist enumerates, once per process."""
        cache_key = (self._SERVICE, reference.agency, reference.id, reference.version)
        cached = _CODELIST_CACHE.get(cache_key)
        if cached is None:
            url = f"{self._SERVICE}/codelist/{reference.agency}/{reference.id}/{reference.version}"
            cached = frozenset(read_codelist(self._read_one_data(url, None)))
            _CODELIST_CACHE[cache_key] = cached
        return cached

    def _require_resolved(self) -> ResolvedDataflow:
        """Return the dataflow's shape, or explain that nothing has read it yet."""
        resolved = self._resolved or self._static_structure()
        if resolved is None:
            raise RuntimeError(f"the shape of dataflow {self.dataflow!r} is not known until it is read")
        return resolved

    def _column_names(self) -> dict[str, str]:
        """Map each SDMX dimension to the column name it is presented under."""
        structure = self._require_resolved().structure
        return {dimension: dimension for dimension in structure.dimensions} | {structure.time_dimension: "period"}

    def _present_pandas(self, payload: str) -> DataFrame:
        """Pivot the observations into the wide time-indexed frame, truncated to the range."""
        df = read_structure_specific(payload, self._column_names(), PANDAS)
        self._require_observations(df)
        if isinstance(df.index, DatetimeIndex):
            df = df.truncate(*_year_bounds(self.start, self.end))
        return df

    def _present_tidy(self, payload: str) -> Frame:
        """Build the long native frame and filter it to the requested range."""
        frame = read_structure_specific(payload, self._column_names(), self.output_type)
        self._require_observations(frame)
        start, end = _year_bounds(self.start, self.end)
        return filter_date_range(frame, "period", start, end)

    def _require_observations(self, frame: Frame) -> None:
        """Refuse to hand back an empty frame, naming whether the key or the coverage is at fault.

        A bad code and a series the service does not carry both come back as an empty document under
        HTTP 200, so the message reports which of the two validation was able to rule out.
        """
        if not is_empty(frame):
            return
        unchecked = sorted(set(self.selections) - self._validated)
        if unchecked:
            detail = (
                f"the codes selected on {', '.join(unchecked)} could not be checked against a codelist, "
                "so one of them may not exist"
            )
        else:
            detail = "every selected code exists in the service's codelists, so this selection has no data"
        raise RemoteDataError(
            f"{self.dataflow} returned no observations for key {self.key!r} over "
            f"{self.start.year}-{self.end.year}; {detail}"
        )


def _as_codes(selection: str | Iterable[str]) -> list[str]:
    """Normalize a dimension selection to the list of codes it names."""
    return [selection] if isinstance(selection, str) else list(selection)


def _nearest_codes(code: str, ordered: Sequence[str], limit: int = 3) -> list[str]:
    """Codes a rejected one was most plausibly meant to be, likeliest first.

    Codes extending the rejected one rank ahead of edit-distance matches, because the common mistake
    is a code from the wrong scheme -- an ISO alpha-2 country where the service wants alpha-3. Pass
    *ordered* sorted: equal-scoring matches tie-break on the code itself.
    """
    extends = [candidate for candidate in ordered if candidate.startswith(code)]
    return list(dict.fromkeys(extends + difflib.get_close_matches(code, ordered, n=limit)))[:limit]
