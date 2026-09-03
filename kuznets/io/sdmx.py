from collections.abc import Iterable, Mapping, Sequence
from io import BytesIO
import time
from typing import IO, NamedTuple
from xml.etree import ElementTree as ET
import zipfile

import narwhals.stable.v2 as nw
import pandas as pd

from kuznets.compat import HTTPError
from kuznets.io.util import _present_observations, _read_content
from kuznets.output import PANDAS, make_frame, observation_schema, validate_output_type
from kuznets.typing import Frame, PathOrBuffer

_TIME_PERIOD = "TIME_PERIOD"
_OBS_VALUE = "OBS_VALUE"

_STRUCTURE = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure}"
_MESSAGE = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message}"
_GENERIC = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic}"
_COMMON = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common}"
_XML = "{http://www.w3.org/XML/1998/namespace}"

_DATASET = _MESSAGE + "DataSet"
_SERIES = _GENERIC + "Series"
_SERIES_KEY = _GENERIC + "SeriesKey"
_OBSERVATION = _GENERIC + "Obs"
_VALUE = _GENERIC + "Value"
_OBSDIMENSION = _GENERIC + "ObsDimension"
_OBSVALUE = _GENERIC + "ObsValue"
_CODE = _STRUCTURE + "Code"
_TIMEDIMENSION = _STRUCTURE + "TimeDimension"


class SDMXCode(NamedTuple):
    """A parsed data structure definition: code labels per codelist, and the time dimensions."""

    codes: dict[str | None, dict[str | None, str | None]]
    ts: list[str | None]


def read_sdmx(path_or_buf: PathOrBuffer, dtype: str = "float64", dsd: SDMXCode | None = None) -> pd.DataFrame:
    """
    Convert a SDMX-XML string to pandas object

    Parameters
    ----------
    path_or_buf : a valid SDMX-XML string or file-like
        https://webgate.ec.europa.eu/fpfis/mwikis/sdmx/index.php/Main_Page
    dtype : str
        dtype to coerce values
    dsd : dict
        parsed DSD dict corresponding to the SDMX-XML data

    Returns
    -------
    results : Series, DataFrame, or dictionaly of Series or DataFrame.
    """

    xdata = _read_content(path_or_buf)
    root = ET.fromstring(xdata)

    try:
        structure = _get_child(root, _MESSAGE + "Structure")
    except ValueError as exc:
        # get zipped path
        result = list(root.iter(_COMMON + "Text"))[1].text
        if result is None or not result.startswith("http"):
            raise ValueError(result) from exc

        for _ in range(60):
            # wait zipped data is prepared
            try:
                data = _read_zipped_sdmx(result)
                return read_sdmx(data, dtype=dtype, dsd=dsd)
            except HTTPError:
                time.sleep(1)
                continue

        msg = "Unable to download zipped data within 60 secs, please download it manually from: {0}"
        raise ValueError(msg.format(result)) from exc

    idx_name = structure.get("dimensionAtObservation")
    dataset = _get_child(root, _DATASET)

    keys = []
    obss = []

    for series in dataset.iter(_SERIES):
        key = _parse_series_key(series)
        obs = _parse_observations(series.iter(_OBSERVATION))
        keys.append(key)
        obss.append(obs)

    mcols = _construct_index(keys, dsd=dsd)
    mseries = _construct_series(obss, name=idx_name, dsd=dsd)

    df = pd.DataFrame(mseries, dtype=dtype)
    df = df.T
    df.columns = mcols

    return df


def _construct_series(
    values: list[list[tuple[str | None, str | None]]], name: str | None, dsd: SDMXCode | None = None
) -> list[pd.Series]:
    # ts defines attributes to be handled as times
    times = dsd.ts if dsd is not None else []

    if len(values) < 1:
        raise ValueError("Data contains no 'Series'")
    results = []
    for value in values:
        idx: pd.Index
        if name in times:
            tvalue = [v[0] for v in value]
            try:
                idx = pd.DatetimeIndex(tvalue, name=name)
            except ValueError:
                # time may be unsupported format, like '2015-B1'
                idx = pd.Index(tvalue, name=name)
        else:
            idx = pd.Index([v[0] for v in value], name=name)

        results.append(pd.Series([v[1] for v in value], index=idx))
    return results


def _construct_index(keys: list[list[tuple[str | None, str | None]]], dsd: SDMXCode | None = None) -> pd.MultiIndex:
    # code defines a mapping to key's internal code to its representation
    codes = dsd.codes if dsd is not None else {}

    if len(keys) < 1:
        raise ValueError("Data contains no 'Series'")
    names = [t[0] for t in keys[0]]
    values: dict[str | None, list[str | None]] = {}
    # initialize
    for key in keys:
        for name, value in key:
            # apply DSD
            try:
                value = codes[name][value]
            except KeyError:
                pass

            try:
                values[name].append(value)
            except KeyError:
                values[name] = [value]

    midx = pd.MultiIndex.from_arrays([values[name] for name in names], names=names)
    return midx


def _parse_observations(observations: Iterable[ET.Element]) -> list[tuple[str | None, str | None]]:
    results = []
    for observation in observations:
        obsdimension = _get_child(observation, _OBSDIMENSION)
        obsvalue = _get_child(observation, _OBSVALUE)
        results.append((obsdimension.get("value"), obsvalue.get("value")))
    # return list of key/value tuple, eg: [(key, value), ...]
    return results


def _parse_series_key(series: ET.Element) -> list[tuple[str | None, str | None]]:
    serieskey = _get_child(series, _SERIES_KEY)
    key_values = serieskey.iter(_VALUE)
    keys = [(key.get("id"), key.get("value")) for key in key_values]
    # return list of key/value tuple, eg: [(key, value), ...]
    return keys


def _get_child(element: ET.Element, key: str) -> ET.Element:
    elements = list(element.iter(key))
    if len(elements) == 1:
        return elements[0]
    elif len(elements) == 0:
        raise ValueError(f"Element {element.tag} contains no {key}")
    else:
        raise ValueError(f"Element {element.tag} contains multiple {key}")


_NAME_EN = f".//{_COMMON}Name[@{_XML}lang='en']"


def _get_english_name(element: ET.Element) -> str | None:
    """Return the element's English name, or None where it declares none."""
    name = element.find(_NAME_EN)
    return name.text if name is not None else None


def _read_sdmx_dsd(path_or_buf: PathOrBuffer) -> SDMXCode:
    """
    Convert a SDMX-XML DSD string to mapping dictionary

    Parameters
    ----------
    filepath_or_buffer : a valid SDMX-XML DSD string or file-like
        https://webgate.ec.europa.eu/fpfis/mwikis/sdmx/index.php/Main_Page

    Returns
    -------
    results : namedtuple (SDMXCode)
    """

    xdata = _read_content(path_or_buf)
    root = ET.fromstring(xdata)

    structure = _get_child(root, _MESSAGE + "Structures")
    codes = _get_child(structure, _STRUCTURE + "Codelists")
    # concepts = _get_child(structure, _STRUCTURE + 'Concepts')
    datastructures = _get_child(structure, _STRUCTURE + "DataStructures")

    code_results = {}
    for codelist in codes:
        # codelist_id = codelist.get('id')
        codelist_name = _get_english_name(codelist)
        mapper = {}
        for code in codelist.iter(_CODE):
            code_id = code.get("id")
            name = _get_english_name(code)
            mapper[code_id] = name
        # codeobj = SDMXCode(id=codelist_id, name=codelist_name, mapper=mapper)
        # code_results[codelist_id] = codeobj
        code_results[codelist_name] = mapper

    times = [dimension.get("id") for dimension in datastructures.iter(_TIMEDIMENSION)]

    result = SDMXCode(codes=code_results, ts=times)
    return result


def _read_zipped_sdmx(path_or_buf: PathOrBuffer) -> IO[bytes]:
    """Unzipp data contains SDMX-XML"""
    data = _read_content(path_or_buf)

    if not isinstance(data, bytes):
        data = data.encode("ascii")
    zp = BytesIO()
    zp.write(data)
    archive = zipfile.ZipFile(zp)
    members = archive.namelist()
    if len(members) != 1:
        raise ValueError(f"Expected one SDMX-XML document in the archive, found {len(members)}: {members}")
    return archive.open(members[0])


def build_sdmx_key(selections: Iterable[str | Iterable[str] | None]) -> str:
    """Build an SDMX data key from one selection per dimension, in the dataflow's dimension order.

    Values selected on a single dimension join with ``+``; dimensions join with ``.``. A dimension
    selected as ``None`` (or an empty sequence) renders as an empty slot, which the service reads as
    a wildcard.

    Parameters
    ----------
    selections : iterable
        One entry per dimension, in the order the data structure declares them. Each entry is a
        code, an iterable of codes, or ``None`` to leave that dimension unrestricted.

    Returns
    -------
    key : str
        The key segment of a data request URL, e.g. ``'LAO.XG_FOB_USD..A'``.

    Examples
    --------
    >>> build_sdmx_key(["LAO", "XG_FOB_USD", None, "A"])
    'LAO.XG_FOB_USD..A'
    >>> build_sdmx_key([["LAO", "THA"], "XG_FOB_USD", None, "A"])
    'LAO+THA.XG_FOB_USD..A'
    """
    parts = []
    for selection in selections:
        if selection is None:
            parts.append("")
        elif isinstance(selection, str):
            parts.append(selection)
        else:
            parts.append("+".join(selection))
    return ".".join(parts)


def read_structure_specific(
    path_or_buf: PathOrBuffer,
    dimensions: Mapping[str, str] | Sequence[str] | None = None,
    output_type: str = "pandas",
) -> Frame:
    """Convert an SDMX 2.1 ``StructureSpecificData`` message to a dataframe of the requested backend.

    This message type carries dimension and attribute values as XML attributes of ``<Series>`` and
    ``<Obs>`` rather than as the child elements :func:`read_sdmx` expects, and its target namespace
    is dataflow-specific, so elements match on their local names. Observations carrying no value,
    and documents holding only ``<Group>`` metadata, contribute no rows.

    Parameters
    ----------
    path_or_buf : str or file-like
        A valid SDMX-XML ``StructureSpecificData`` string, path, or file-like object.
    dimensions : mapping or sequence of str, optional
        Which XML attributes to treat as dimensions, in the order they should appear. A mapping also
        renames them, its values becoming the column names; include ``'TIME_PERIOD'`` to name and
        position the time dimension. A sequence keeps the SDMX identifiers as the names. Naming the
        dimensions matters because a series carries attributes such as ``UNIT_MEASURE`` and
        ``SCALE`` alongside them, and only the data structure definition tells them apart. Default
        None, which takes every attribute the document carries.
    output_type : str, optional
        Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
        Default 'pandas'.

    Returns
    -------
    df : DataFrame or native frame
        For pandas, time-indexed wide data with the remaining dimensions forming the columns; for
        any other backend, one row per observation with a dimension column apiece and a float64
        ``value`` column.
    """
    output_type = validate_output_type(output_type)
    root = ET.fromstring(_read_content(path_or_buf))
    records = _structure_specific_records(root)

    codes, names = _resolve_dimensions(dimensions, records)
    time_pos = codes.index(_TIME_PERIOD)

    observations = [
        (tuple(record.get(code, "") for code in codes), record[_OBS_VALUE])
        for record in records
        if record.get(_OBS_VALUE)
    ]
    if not observations:
        return _empty_observations(names, time_pos, output_type)

    label_maps: list[dict[str, str]] = [{} for _ in names]
    return _present_observations(observations, names, label_maps, time_pos, output_type)


def _structure_specific_records(root: ET.Element) -> list[dict[str, str]]:
    """Walk a parsed ``StructureSpecificData`` tree into one attribute dict per observation.

    Each record merges its series' attributes with the observation's own, so it carries the full
    dimension key; an observation restating a series-level attribute wins.
    """
    records = []
    for series in root.iter():
        if _local_name(series.tag) != "Series":
            continue
        for observation in series:
            if _local_name(observation.tag) == "Obs":
                records.append({**series.attrib, **observation.attrib})
    return records


def _resolve_dimensions(
    dimensions: Mapping[str, str] | Sequence[str] | None, records: list[dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Resolve the ``dimensions`` argument into SDMX identifiers and their output column names.

    The time dimension is appended when the caller leaves it out, so it always has a position.
    """
    if dimensions is None:
        codes = list(dict.fromkeys(key for record in records for key in record if key != _OBS_VALUE))
        names = list(codes)
    elif isinstance(dimensions, Mapping):
        codes = list(dimensions)
        names = [dimensions[code] for code in codes]
    elif isinstance(dimensions, Sequence) and not isinstance(dimensions, str):
        codes = list(dimensions)
        names = list(codes)
    else:
        raise TypeError(f"'dimensions' must be a mapping or a sequence of str, got {type(dimensions).__name__}")

    if _TIME_PERIOD not in codes:
        codes.append(_TIME_PERIOD)
        names.append(_TIME_PERIOD)
    return codes, names


def _empty_observations(names: list[str], time_pos: int, output_type: str) -> Frame:
    """Build the empty frame for a document that yielded no observations."""
    time_name = names[time_pos]
    if output_type == PANDAS:
        return pd.DataFrame(index=pd.DatetimeIndex([], name=time_name))
    schema = observation_schema(names)
    schema[time_name] = nw.Datetime()
    return make_frame([], output_type, schema=schema)


def _local_name(tag: str) -> str:
    """Strip the namespace from a qualified element tag."""
    return tag.rpartition("}")[2]
