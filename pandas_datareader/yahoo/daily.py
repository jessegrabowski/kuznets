import time

from pandas import DataFrame, Series, date_range, isnull, notnull, to_datetime

from pandas_datareader.base import _DailyBaseReader
from pandas_datareader.yahoo.headers import DEFAULT_HEADERS


class YahooDailyReader(_DailyBaseReader):
    """Get historical stock prices from Yahoo Finance."""

    def __init__(
        self,
        symbols=None,
        start=None,
        end=None,
        retry_count=3,
        pause=0.1,
        session=None,
        adjust_price=False,
        ret_index=False,
        chunksize=1,
        interval="d",
        get_actions=False,
        adjust_dividends=True,
    ):
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str, list of str, or DataFrame
            Single stock symbol (ticker), list of symbols, or DataFrame with index containing stock
            symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Defaults to 5 years before current date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between consecutive queries of chunks.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        adjust_price : bool, default False
            If True, adjusts all prices ('Open', 'High', 'Low', 'Close') based on 'Adj Close'. Adds
            'Adj_Ratio' column and drops 'Adj Close'.
        ret_index : bool, default False
            If True, includes a simple return index 'Ret_Index'.
        chunksize : int, default 1
            Number of symbols to download consecutively before initiating pause.
        interval : str, default "d"
            Time interval code. Valid values are ``'d'`` for daily, ``'wk'`` for weekly, ``'mo'``
            for monthly (``'w'`` and ``'m'`` accepted for backward compatibility).
        get_actions : bool, default False
            If True, adds Dividend and Split columns to the DataFrame.
        adjust_dividends : bool, default True
            If True, adjusts dividends for splits.
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            chunksize=chunksize,
        )

        if session is None:
            self.headers = DEFAULT_HEADERS
        else:
            self.headers = session.headers

        self.adjust_price = adjust_price
        self.ret_index = ret_index
        self.interval = interval
        self._get_actions = get_actions

        if self.interval not in ["d", "wk", "mo", "m", "w"]:
            raise ValueError(
                "Invalid interval: valid values are  'd', 'wk' and 'mo'. 'm' and 'w' "
                "have been implemented for backward compatibility. 'v' has been moved "
                "to the yahoo-actions or yahoo-dividends APIs."
            )
        elif self.interval in ["m", "mo"]:
            self.pdinterval = "m"
            self.interval = "mo"
        elif self.interval in ["w", "wk"]:
            self.pdinterval = "w"
            self.interval = "wk"

        self.interval = "1" + self.interval
        self.adjust_dividends = adjust_dividends

    @property
    def get_actions(self) -> bool:
        """Whether to fetch actions data."""
        return self._get_actions

    @property
    def url(self) -> str:
        """API URL."""
        return "https://query1.finance.yahoo.com/v8/finance/chart/{}"

    def _get_params(self, symbol: str) -> dict:
        day_end = self.end.replace(hour=23, minute=59, second=59)
        return {
            "period1": int(time.mktime(self.start.timetuple())),
            "period2": int(time.mktime(day_end.timetuple())),
            "interval": self.interval,
            "events": "div,splits",
            "includeAdjustedClose": "true",
            "symbol": symbol,
        }

    def _read_one_data(self, url: str, params: dict) -> DataFrame:
        """Read price history for a single symbol from the Yahoo v8 chart API."""
        symbol = params.pop("symbol")
        resp = self._get_response(url.format(symbol), params=params, headers=self.headers)

        result = resp.json()["chart"]["result"]
        if not result or "timestamp" not in result[0]:
            return self._empty_history()
        result = result[0]

        quote = result["indicators"]["quote"][0]
        adjclose = result["indicators"].get("adjclose", [{}])[0].get("adjclose", quote["close"])
        prices = DataFrame(
            {
                "High": quote["high"],
                "Low": quote["low"],
                "Open": quote["open"],
                "Close": quote["close"],
                "Volume": quote["volume"],
                "Adj Close": adjclose,
            },
            index=_date_index(result["timestamp"]),
        )
        prices.index.name = "Date"
        prices = prices.sort_index().dropna(how="all")

        if self.ret_index:
            prices["Ret_Index"] = _calc_return_index(prices["Adj Close"])
        if self.adjust_price:
            prices = _adjust_prices(prices)
        if self.get_actions:
            prices = self._add_actions(prices, result.get("events", {}))

        return prices

    def _empty_history(self) -> DataFrame:
        """Return an empty price frame spanning the requested date range."""
        freq = self.interval[1].upper()
        if freq == "W":
            freq += "-MON"
        dates = date_range(self.start, self.end, freq=freq)
        return DataFrame(index=dates, columns=["High", "Low", "Open", "Close", "Volume", "Adj Close"])

    def _add_actions(self, prices: DataFrame, events: dict) -> DataFrame:
        """Join dividend and split columns onto the price frame from the chart ``events`` block."""
        dividends = events.get("dividends", {})
        splits = events.get("splits", {})

        if dividends:
            divs = DataFrame(list(dividends.values()))
            divs.index = _date_index(divs["date"])
            prices = prices.join(divs["amount"].rename("Dividends"), how="outer")

        if splits:
            spl = DataFrame(list(splits.values()))
            spl.index = _date_index(spl["date"])
            # The split column is denominator/numerator (e.g. 1/7 for a 7:1 split); a non-positive
            # numerator denotes a symbol change rather than a real split.
            ratio = (spl["denominator"] / spl["numerator"]).where(spl["numerator"] > 0, 1.0)
            prices = prices.join(ratio.rename("Splits"), how="outer")

            if dividends and not self.adjust_dividends:
                # Yahoo reports split-adjusted dividends; undo the adjustment.
                adj = prices["Splits"].sort_index(ascending=False).fillna(1).cumprod()
                prices["Dividends"] = prices["Dividends"] / adj

        return prices


def _date_index(seconds):
    """Convert a sequence of Unix timestamps to a calendar-date DatetimeIndex (time dropped)."""
    return to_datetime(to_datetime(Series(seconds), unit="s").dt.date)


def _adjust_prices(hist_data, price_list=None):
    """
    Return modifed DataFrame with adjusted prices based on 'Adj Close' price. Adds 'Adj_Ratio'
    column.
    """
    if price_list is None:
        price_list = "Open", "High", "Low", "Close"
    adj_ratio = hist_data["Adj Close"] / hist_data["Close"]

    data = hist_data.copy()
    for item in price_list:
        data[item] = hist_data[item] * adj_ratio
    data["Adj_Ratio"] = adj_ratio
    del data["Adj Close"]
    return data


def _calc_return_index(price_df):
    """
    Return a returns index from a input price df or series. Initial value (typically NaN) is set to
    1.
    """
    df = price_df.pct_change().add(1).cumprod()
    mask = notnull(df.iloc[1]) & isnull(df.iloc[0])
    if mask:
        df.loc[df.index[0]] = 1

    # Check for first stock listings after starting date of index in ret_index
    # If True, find first_valid_index and set previous entry to 1.
    if not mask:
        tstamp = df.first_valid_index()
        t_idx = df.index.get_loc(tstamp) - 1
        df.iloc[t_idx] = 1

    return df
