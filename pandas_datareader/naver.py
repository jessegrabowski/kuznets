from collections.abc import Generator
from datetime import datetime
from xml.etree import ElementTree

import numpy as np
from pandas import DataFrame, to_datetime

from pandas_datareader.base import _DailyBaseReader


class NaverDailyReader(_DailyBaseReader):
    """Fetch daily historical data from Naver Finance."""

    def __init__(
        self,
        symbols: str | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        adjust_price: bool = False,
        ret_index: bool = False,
        chunksize: int = 1,
        interval: str = "d",
        get_actions: bool = False,
        adjust_dividends: bool = True,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str
            A single stock symbol. Multiple symbols are not currently supported.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between retries.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        adjust_price : bool, default False
            Not implemented.
        ret_index : bool, default False
            Not implemented.
        chunksize : int, default 1
            Number of symbols to download consecutively before initiating pause.
        interval : str, default "d"
            Not implemented.
        get_actions : bool, default False
            Not implemented.
        adjust_dividends : bool, default True
            Not implemented.
        """
        if not isinstance(symbols, str):
            raise NotImplementedError("Bulk-fetching is not implemented")

        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            chunksize=chunksize,
        )

        self.headers = {
            "Sec-Fetch-Mode": "no-cors",
            "Referer": f"https://finance.naver.com/item/fchart.nhn?code={symbols}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36",  # noqa
        }

    @property
    def get_actions(self) -> bool:
        """Whether to fetch actions data."""
        return self._get_actions

    @property
    def url(self) -> str:
        """API URL."""
        return "https://fchart.stock.naver.com/sise.nhn"

    def _get_params(self, symbol: str) -> dict:
        """Build query parameters.

        Parameters
        ----------
        symbol : str
            Ticker symbol.

        Returns
        -------
        params : dict
        """
        # NOTE: The server does not take start, end dates as inputs; it only
        # takes the number of trading days as an input. To circumvent this
        # pitfall, we calculate the number of business days between self.start
        # and the current date. And then we filter by self.end before returning
        # the final result (in _read_one_data()).
        days = np.busday_count(self.start.date(), datetime.now().date())
        params = {"symbol": symbol, "timeframe": "day", "count": days, "requestType": 0}
        return params

    def _read_one_data(self, url: str, params: dict) -> DataFrame:
        """Read one data from specified symbol.

        Parameters
        ----------
        url : str
            Target URL.
        params : dict
            Query parameters.

        Returns
        -------
        df : DataFrame
        """
        resp = self._get_response(url, params=params)
        parsed = self._parse_xml_response(resp.text)
        prices = DataFrame(parsed, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        prices["Date"] = to_datetime(prices["Date"])
        prices = prices.set_index("Date")

        # NOTE: See _get_params() for explanations.
        return prices[(prices.index >= self.start) & (prices.index <= self.end)]

    def _parse_xml_response(self, xml_content: str) -> Generator:
        """Parse XML response from the server.

        Parameters
        ----------
        xml_content : str
            Raw XML string.

        Yields
        ------
        list of str
            Each row's data fields split by ``'|'``.
        """
        root = ElementTree.fromstring(xml_content)
        items = root.findall("chartdata/item")

        for item in items:
            yield item.attrib["data"].split("|")
