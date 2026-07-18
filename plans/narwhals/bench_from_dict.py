import random
import string
import time

import narwhals
import narwhals.stable.v2 as nw
import pandas as pd
import polars as pl
import pyarrow as pa

SIZES = [1_000, 10_000, 100_000]
BACKENDS = ["pandas", "polars", "pyarrow"]

random.seed(1234)


def sdmx_records(n: int) -> list[dict]:
    countries = ["AUS", "AUT", "BEL", "CAN", "DEU", "FRA", "JPN", "USA"]
    subjects = ["".join(random.choices(string.ascii_uppercase, k=8)) for _ in range(12)]
    months = [f"{1990 + i // 12}-{i % 12 + 1:02d}" for i in range(400)]
    return [
        {
            "Country": random.choice(countries),
            "Subject": random.choice(subjects),
            "TIME_PERIOD": random.choice(months),
            "value": random.random() * 100,
        }
        for _ in range(n)
    ]


def tiingo_records(n: int) -> list[dict]:
    symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
    return [
        {
            "symbol": random.choice(symbols),
            "date": f"{2000 + i // 250}-{i % 12 + 1:02d}-{i % 28 + 1:02d}T00:00:00.000Z",
            "open": random.random() * 500,
            "high": random.random() * 500,
            "low": random.random() * 500,
            "close": random.random() * 500,
            "volume": random.randrange(1_000_000, 90_000_000),
        }
        for i in range(n)
    ]


def records_to_columns(records: list[dict]) -> dict[str, list]:
    keys = records[0].keys()
    return {k: [r[k] for r in records] for k in keys}


def bench(fn, repeat: int = 7) -> float:
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best * 1000


def nw_from_dict_columns(columns: dict[str, list], backend: str):
    return nw.from_dict(columns, backend=backend).to_native()


def pandas_then_convert(records: list[dict], backend: str):
    df = pd.DataFrame(records)
    ndf = nw.from_native(df, eager_only=True)
    if backend == "polars":
        return ndf.to_polars()
    if backend == "pyarrow":
        return ndf.to_arrow()
    return df


def native_reference(records: list[dict], backend: str):
    if backend == "pandas":
        return pd.DataFrame(records)
    if backend == "polars":
        return pl.DataFrame(records)
    return pa.Table.from_pylist(records)


def main() -> None:
    print(
        f"pandas {pd.__version__} | narwhals {narwhals.__version__} | "
        f"polars {pl.__version__} | pyarrow {pa.__version__}\n"
    )

    for shape_name, make_records in [("sdmx", sdmx_records), ("tiingo", tiingo_records)]:
        print(f"## {shape_name}-shaped records (times in ms, best of 7)\n")
        header = ["n", "path"] + BACKENDS
        rows = []
        for n in SIZES:
            records = make_records(n)
            repeat = 7 if n <= 10_000 else 3

            row_pivot = bench(lambda records=records: records_to_columns(records), repeat)
            rows.append([n, "records->columns (pure python)", f"{row_pivot:.1f}", "-", "-"])

            for path_name, fn in [
                ("nw.from_dict (columns)", lambda b, r=records: nw_from_dict_columns(records_to_columns(r), b)),
                ("pd.DataFrame -> nw convert", lambda b, r=records: pandas_then_convert(r, b)),
                ("native constructor (reference)", lambda b, r=records: native_reference(r, b)),
            ]:
                timings = [f"{bench(lambda b=b, fn=fn: fn(b), repeat):.1f}" for b in BACKENDS]
                rows.append([n, path_name, *timings])

        widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
        print("| " + " | ".join(str(h).ljust(w) for h, w in zip(header, widths, strict=True)) + " |")
        print("|" + "|".join("-" * (w + 2) for w in widths) + "|")
        for r in rows:
            print("| " + " | ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)) + " |")
        print()


if __name__ == "__main__":
    main()
