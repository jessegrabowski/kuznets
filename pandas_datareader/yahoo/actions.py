import pandas as pd
from pandas import DataFrame, MultiIndex

from pandas_datareader.yahoo.daily import YahooDailyReader


class YahooActionReader(YahooDailyReader):
    """
    Get historical corporate actions (dividends and stock splits) from Yahoo Finance. All dates
    correspond with dividend and stock split ex-dates.
    """

    def _read_core(self) -> DataFrame | dict[str, DataFrame]:
        """Fetch action data.

        Returns
        -------
        DataFrame or dict of str to DataFrame
            If multiple symbols, returns a dict keyed by symbol.
        """
        data = super()._read_core()
        if isinstance(data, dict):
            data = self._to_panel(data)
        actions = {}
        if isinstance(data.columns, MultiIndex):
            data = data.swaplevel(0, 1, axis=1)
            for s in data.columns.levels[0]:
                actions[s] = _get_one_action(data[s])
            return actions
        else:
            return _get_one_action(data)

    def _present_pandas(self, payload):
        """The action payload (frame, or dict keyed by symbol) is already the pandas output."""
        return payload

    @property
    def get_actions(self) -> bool:
        """Always True for action reader."""
        return True


def _get_one_action(data: DataFrame) -> DataFrame:
    """Stack the dividend and split columns of a single-symbol frame into action/value rows.

    Parameters
    ----------
    data : DataFrame
        DataFrame with optional ``'Dividends'`` and ``'Splits'`` columns.

    Returns
    -------
    df : DataFrame
        Rows labelled ``'DIVIDEND'`` or ``'SPLIT'`` with their value, newest first.
    """
    frames = []
    for column, label in (("Dividends", "DIVIDEND"), ("Splits", "SPLIT")):
        if column in data.columns:
            events = data[[column]].dropna().rename(columns={column: "value"})
            events["action"] = label
            frames.append(events)

    if not frames:
        return DataFrame(columns=["action", "value"])
    return pd.concat(frames).sort_index(ascending=False)[["action", "value"]]


class YahooDivReader(YahooActionReader):
    """Get historical dividend data from Yahoo Finance."""

    def _read_core(self) -> DataFrame:
        """Fetch dividend data only.

        Returns
        -------
        df : DataFrame
        """
        data = super()._read_core()
        return data[data["action"] == "DIVIDEND"]


class YahooSplitReader(YahooActionReader):
    """Get historical stock split data from Yahoo Finance."""

    def _read_core(self) -> DataFrame:
        """Fetch split data only.

        Returns
        -------
        df : DataFrame
        """
        data = super()._read_core()
        return data[data["action"] == "SPLIT"]
