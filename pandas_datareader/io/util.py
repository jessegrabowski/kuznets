from collections import OrderedDict
import os

import pandas as pd

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


def _read_content(path_or_buf):
    """
    Copied part of internal logic from pandas.io.read_json.
    """

    filepath_or_buffer = get_filepath_or_buffer(path_or_buf)[0]

    if isinstance(filepath_or_buffer, str):
        try:
            exists = os.path.exists(filepath_or_buffer)
        except (TypeError, ValueError):
            exists = False

        if exists:
            with open(filepath_or_buffer) as fh:
                data = fh.read()
        else:
            data = filepath_or_buffer
    elif hasattr(filepath_or_buffer, "read"):
        data = filepath_or_buffer.read()
    else:
        data = filepath_or_buffer

    return data
