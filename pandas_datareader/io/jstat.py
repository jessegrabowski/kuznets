import numpy as np

from pandas_datareader._output import validate_output_type
from pandas_datareader.io.util import (
    TIME_IDS,
    _load_json,
    _present_observations,
)


def read_jstat(path_or_buf, output_type: str = "pandas"):
    """Convert a JSON-stat 2.0 dataset to a dataframe of the requested backend.

    Parameters
    ----------
    path_or_buf : str or file-like
        A valid JSON-stat 2.0 string or file-like object. See https://json-stat.org/.
    output_type : str, optional
        Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
        Default 'pandas'.

    Returns
    -------
    df : DataFrame or native frame
        For pandas, time-indexed wide data with the remaining dimensions forming the columns; for
        any other backend, one row per observation with display-labeled dimension columns and a
        float64 ``value`` column.
    """
    output_type = validate_output_type(output_type)
    data = _load_json(path_or_buf)

    dim_ids = data["id"]
    sizes = data["size"]
    cat_codes, label_maps, dim_names = [], [], []
    for dim_id in dim_ids:
        category = data["dimension"][dim_id]["category"]
        index = category["index"]
        codes = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
        cat_codes.append(codes)
        label_maps.append(category.get("label", {}))
        dim_names.append(data["dimension"][dim_id].get("label", dim_id))

    time_pos = next((i for i, d in enumerate(dim_ids) if d in TIME_IDS), len(dim_ids) - 1)

    records = []
    for flat, value in data["value"].items():
        if value is None:
            continue
        # JSON-stat values are keyed by the row-major offset into the cube described by `size`.
        coords = np.unravel_index(int(flat), sizes)
        codes = tuple(dim_codes[c] for dim_codes, c in zip(cat_codes, coords, strict=True))
        records.append((codes, value))

    return _present_observations(records, dim_names, label_maps, time_pos, output_type)
