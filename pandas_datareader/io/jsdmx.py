from pandas_datareader.io.util import (
    TIME_IDS,
    _load_json,
    _pivot_observations,
)


def read_jsdmx(path_or_buf):
    """Convert an SDMX-JSON 2.0 data message to a pandas DataFrame.

    Expects the message to have been requested with ``dimensionAtObservation=AllDimensions``.

    Parameters
    ----------
    path_or_buf : str or file-like
        A valid SDMX-JSON 2.0 string or file-like object. See
        https://github.com/sdmx-twg/sdmx-json.

    Returns
    -------
    df : DataFrame
        Time-indexed data with the remaining dimensions forming the columns.
    """
    data = _load_json(path_or_buf)

    payload = data["data"]
    dims = payload["structures"][0]["dimensions"]["observation"]
    dim_names = [d["name"] for d in dims]
    cat_codes = [[v["id"] for v in d["values"]] for d in dims]
    label_maps = [{v["id"]: v["name"] for v in d["values"]} for d in dims]
    time_pos = next((i for i, d in enumerate(dims) if d["id"] in TIME_IDS), len(dims) - 1)

    observations = payload["dataSets"][0]["observations"]
    records = []
    for key, value in observations.items():
        if value[0] is None:
            continue
        pos = (int(x) for x in key.split(":"))
        codes = tuple(dim_codes[p] for dim_codes, p in zip(cat_codes, pos, strict=True))
        records.append((codes, value[0]))

    return _pivot_observations(records, dim_names, label_maps, time_pos)
