import pandas as pd
from pandas import DataFrame, MultiIndex

from kuznets.yahoo.daily import YahooDailyReader


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
        columns = data.columns
        if not isinstance(columns, MultiIndex):
            return _get_one_action(data)
        data = data.swaplevel(0, 1, axis=1)
        return {symbol: _get_one_action(data[symbol]) for symbol in columns.levels[1]}

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

    def _read_core(self) -> DataFrame | dict[str, DataFrame]:
        """Fetch dividend data only.

        Returns
        -------
        DataFrame or dict of str to DataFrame
            If multiple symbols, returns a dict keyed by symbol.
        """
        return _keep_action(super()._read_core(), "DIVIDEND")


class YahooSplitReader(YahooActionReader):
    """Get historical stock split data from Yahoo Finance."""

    def _read_core(self) -> DataFrame | dict[str, DataFrame]:
        """Fetch split data only.

        Returns
        -------
        DataFrame or dict of str to DataFrame
            If multiple symbols, returns a dict keyed by symbol.
        """
        return _keep_action(super()._read_core(), "SPLIT")


def _keep_action(data: DataFrame | dict[str, DataFrame], action: str) -> DataFrame | dict[str, DataFrame]:
    """Keep only the rows of *action*, per symbol when the payload covers several."""
    if isinstance(data, dict):
        return {symbol: frame[frame["action"] == action] for symbol, frame in data.items()}
    return data[data["action"] == action]
