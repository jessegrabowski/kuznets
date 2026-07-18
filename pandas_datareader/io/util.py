from collections import OrderedDict
from datetime import datetime
from pathlib import Path
import re

import narwhals.stable.v2 as nw
import pandas as pd

from pandas_datareader._output import PANDAS, make_frame, observation_schema
from pandas_datareader.compat import get_filepath_or_buffer

# Dimension identifiers that mark the time axis across SDMX-JSON and JSON-stat responses.
TIME_IDS = {"time", "TIME_PERIOD"}


def _load_json(path_or_buf):
    """Read JSON content from a path, string, or file-like and parse it into a dict."""
    jdata = _read_content(path_or_buf)
    if isinstance(jdata, dict):
        return jdata
    try:
        import simplejson as json
    except ImportError:
        import json
    return json.loads(jdata, object_pairs_hook=OrderedDict)


def _to_datetime_index(idx, name):
    """Coerce period codes to a ``DatetimeIndex``, falling back to a string ``Index`` on failure."""
    try:
        return pd.DatetimeIndex(pd.to_datetime(idx), name=name)
    except (ValueError, TypeError):
        # Semester and other non-calendar codes (e.g. '2013-S1') aren't datetimes; keep the labels.
        return pd.Index(idx, name=name)


def _pivot_observations(records, dim_names, label_maps, time_pos):
    """Pivot long-form SDMX observations into a wide DataFrame indexed by time.

    Parameters
    ----------
    records : list of tuple
        Each entry is ``(code_tuple, value)`` where ``code_tuple`` holds one dimension code per
        entry in *dim_names*, in the same order.
    dim_names : list of str
        Human-readable name of each dimension, used as the index/column level names.
    label_maps : list of dict
        One mapping of code to display name per dimension, aligned with *dim_names*.
    time_pos : int
        Position of the time dimension within *dim_names*; it becomes the row index.

    Returns
    -------
    df : DataFrame
        Time-indexed data with the remaining dimensions forming the (possibly multi-level)
        columns.
    """
    midx = pd.MultiIndex.from_tuples([r[0] for r in records], names=dim_names)
    s = pd.Series([r[1] for r in records], index=midx, dtype="float64")

    others = [i for i in range(len(dim_names)) if i != time_pos]
    time_name = dim_names[time_pos]
    if not others:
        df = s.to_frame(name=time_name)
        df.index = df.index.get_level_values(0)
    else:
        # Pivot on the unique codes, then relabel, so two codes sharing a display name don't collide.
        df = s.unstack([dim_names[i] for i in others])
        cols = df.columns
        if isinstance(cols, pd.MultiIndex):
            df.columns = pd.MultiIndex.from_tuples(
                [tuple(label_maps[others[lvl]].get(c, c) for lvl, c in enumerate(key)) for key in cols],
                names=cols.names,
            )
        else:
            df.columns = pd.Index([label_maps[others[0]].get(c, c) for c in cols], name=cols.name)

    df.index = _to_datetime_index(df.index, time_name)
    return df.sort_index()


_SEMESTER_CODE = re.compile(r"^(\d{4})-?S([12])$", re.IGNORECASE)
_WEEK_CODE = re.compile(r"^(\d{4})-?W(\d{2})$", re.IGNORECASE)


def _parse_period_code(code) -> datetime | None:
    """Parse an SDMX/JSON-stat period code to its period-start timestamp, or None if unrecognized.

    Standard codes -- annual ('2009'), monthly ('2009-01'), daily ('2009-01-15'), quarterly
    ('2009-Q1' or '2009Q1') -- parse through ``pandas.Period``. Semesters ('2013-S2' -> July 1st)
    and ISO weeks ('2020-W05' -> that week's Monday) have no pandas frequency and parse here. Codes
    are case-insensitive and must open with a four-digit year; anything unrecognized returns None
    so the column stays string-typed.
    """
    text = str(code).strip()
    if len(text) < 4 or not text[:4].isdigit() or "." in text:
        # The dot guard blocks decimal-year strings like '2009.5', which pandas would otherwise
        # misread as year-month.
        return None
    if match := _SEMESTER_CODE.match(text):
        return datetime(int(match[1]), 6 * int(match[2]) - 5, 1)
    if match := _WEEK_CODE.match(text):
        try:
            return datetime.strptime(f"{match[1]}-W{match[2]}-1", "%G-W%V-%u")
        except ValueError:
            return None
    try:
        return pd.Period(text).start_time.to_pydatetime()
    except ValueError:
        return None


def _observations_to_records(records, dim_names, label_maps, time_pos):
    """Convert ``(codes, value)`` observations into display-labeled row records.

    Non-time dimension codes map through their label maps, matching the column labels
    :func:`_pivot_observations` produces; the time dimension keeps its raw codes for datetime
    casting downstream; values coerce to float.

    Parameters
    ----------
    records : list of tuple
        Each entry is ``(code_tuple, value)`` with one code per entry in *dim_names*.
    dim_names : list of str
        Human-readable name of each dimension, used as the record keys.
    label_maps : list of dict
        One mapping of code to display name per dimension, aligned with *dim_names*.
    time_pos : int
        Position of the time dimension within *dim_names*.

    Returns
    -------
    list of dict
        One record per observation: a key per dimension plus ``'value'``.
    """
    rows = []
    for codes, value in records:
        row = {}
        for position, (name, code) in enumerate(zip(dim_names, codes, strict=True)):
            row[name] = code if position == time_pos else label_maps[position].get(code, code)
        row["value"] = float(value)
        rows.append(row)
    return rows


def _present_observations(records, dim_names, label_maps, time_pos, output_type):
    """Present parsed observations as today's wide pandas frame or a long native frame.

    The pandas path pivots to the time-indexed wide frame, with its legacy time parsing. Every
    other backend gets one row per observation with display-labeled dimension columns and a float64
    ``value`` column; period codes parse in Python via :func:`_parse_period_code` before any
    backend sees them, so the time column is datetime-typed identically everywhere -- including
    quarterly, semester, and ISO-week codes -- and stays string-typed only when a code defeats the
    parser.
    """
    if output_type == PANDAS:
        return _pivot_observations(records, dim_names, label_maps, time_pos)
    tidy_records = _observations_to_records(records, dim_names, label_maps, time_pos)
    time_name = dim_names[time_pos]
    parsed_times = [_parse_period_code(row[time_name]) for row in tidy_records]
    schema = observation_schema(dim_names)
    if all(parsed is not None for parsed in parsed_times):
        for row, parsed in zip(tidy_records, parsed_times, strict=True):
            row[time_name] = parsed
        schema[time_name] = nw.Datetime()
    return make_frame(tidy_records, output_type, schema=schema)


def _read_content(path_or_buf):
    """
    Copied part of internal logic from pandas.io.read_json.
    """

    filepath_or_buffer = get_filepath_or_buffer(path_or_buf)[0]

    if isinstance(filepath_or_buffer, str | Path):
        try:
            exists = Path(filepath_or_buffer).exists()
        except (TypeError, ValueError, OSError):
            # A raw JSON string (not a path) or an over-long name isn't a file.
            exists = False

        if exists:
            data = Path(filepath_or_buffer).read_text()
        else:
            data = filepath_or_buffer
    elif hasattr(filepath_or_buffer, "read"):
        data = filepath_or_buffer.read()
    else:
        data = filepath_or_buffer

    return data
