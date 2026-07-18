import datetime as dt
from io import StringIO

import pandas as pd

from pandas_datareader.base import _DailyBaseReader
from pandas_datareader.compat import is_list_like


class MoexReader(_DailyBaseReader):
    """Get historical stock prices from the Moscow Exchange (MOEX)."""

    def __init__(self, *args, **kwargs):
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str, list of str, or DataFrame
            A single stock symbol (secid), list of symbols, or a DataFrame with an index containing
            stock symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Defaults to 20 years before current date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between consecutive queries of chunks.
        chunksize : int, default 25
            Number of symbols to download consecutively before initiating pause.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.

        Notes
        -----
        To avoid being penalized by MOEX servers, pauses more than 0.1s between downloading 'chunks'
        of symbols can be specified.
        """
        super().__init__(*args, **kwargs)
        self.start = self.start.date()
        self.end_dt = self.end
        self.end = self.end.date()

        if isinstance(self.symbols, pd.DataFrame):
            self.symbols = self.symbols.index.tolist()
        elif not is_list_like(self.symbols):
            self.symbols = [self.symbols]

        self.__markets_n_engines = {}  # dicts for tuples of engines and markets

    __url_metadata = "https://iss.moex.com/iss/securities/{symbol}.csv"
    __url_data = "https://iss.moex.com/iss/history/engines/{engine}/markets/{market}/securities/{symbol}.csv"

    @property
    def url(self):
        """Return a list of API URLs per symbol"""

        if not self.__markets_n_engines:
            raise Exception("Accessing url property before invocation of read() or _get_metadata() methods")

        return [
            self.__url_data.format(engine=engine, market=market, symbol=s)
            for s in self.symbols
            if s in self.__markets_n_engines
            for market, engine in self.__markets_n_engines[s]
        ]

    def _get_params(self, start):
        """Return a dict for REST API GET request parameters"""

        params = {
            "iss.only": "history",
            "iss.dp": "point",
            "iss.df": "%Y-%m-%d",
            "iss.tf": "%H:%M:%S",
            "iss.dtf": "%Y-%m-%d %H:%M:%S",
            "iss.json": "extended",
            "callback": "JSON_CALLBACK",
            "from": start,
            "till": self.end_dt.strftime("%Y-%m-%d"),
            "limit": 100,
            "start": 0,
            "sort_order": "TRADEDATE",
            "sort_order_desc": "asc",
        }
        return params

    def _get_metadata(self):
        """Get markets and engines for the given symbols"""

        markets_n_engines = {}
        boards = {}

        for symbol in self.symbols:
            response = self._get_response(self.__url_metadata.format(symbol=symbol))
            text = self._sanitize_response(response)
            if len(text) == 0:
                service = self.__class__.__name__
                raise OSError(
                    f"{service} request returned no data; check URL for invalid inputs: {self.__url_metadata}"
                )
            if isinstance(text, bytes):
                text = text.decode("windows-1251")

            header_str = "secid;boardid;"
            get_data = False
            for s in text.splitlines():
                if s.startswith(header_str):
                    get_data = True
                    continue
                if get_data and s != "":
                    fields = s.split(";")

                    if symbol not in markets_n_engines:
                        markets_n_engines[symbol] = []

                    markets_n_engines[symbol].append((fields[5], fields[7]))  # market and engine

                    if fields[14] == "1":  # main board for symbol
                        symbol_U = symbol.upper()
                        boards[symbol_U] = fields[1]

            if symbol not in markets_n_engines:
                raise OSError(
                    f"{self.__class__.__name__} request returned no metadata: {self.__url_metadata.format(symbol=symbol)}\n"
                    f"Typo in the security symbol `{symbol}`?"
                )
            if symbol in markets_n_engines:
                markets_n_engines[symbol] = list(set(markets_n_engines[symbol]))
        return markets_n_engines, boards

    def read_all_boards(self):
        """Read all data from every board for every ticker.

        Returns
        -------
        df : DataFrame or native frame
            One row per (date, board), as a pandas DataFrame by default or as a native frame of the
            backend selected with ``output_type``.
        """
        return self._present(self._read_all_boards_core())

    def _read_all_boards_core(self) -> pd.DataFrame:
        markets_n_engines, boards = self._get_metadata()
        try:
            self.__markets_n_engines = markets_n_engines

            urls = self.url  # generate urls per symbols
            dfs = []  # an array of pandas dataframes per symbol to concatenate

            for i in range(len(urls)):
                out_list = []
                date_column = None

                while True:  # read in a loop with small date intervals
                    if len(out_list) > 0:
                        if date_column is None:
                            date_column = out_list[0].split(";").index("TRADEDATE")

                        # get the last downloaded date
                        start_str = out_list[-1].split(";", 4)[date_column]
                        start = dt.datetime.strptime(start_str, "%Y-%m-%d").date()
                    else:
                        start_str = self.start.strftime("%Y-%m-%d")
                        start = self.start

                    if start > self.end or start > dt.date.today():
                        break

                    params = self._get_params(start_str)
                    strings_out = self._read_url_as_String(urls[i], params).splitlines()[2:]
                    strings_out = list(filter(lambda x: x.strip(), strings_out))

                    if len(out_list) == 0:
                        out_list = strings_out
                        if len(strings_out) < 101:  # all data received - break
                            break
                    else:
                        out_list += strings_out[1:]  # remove a CSV head line
                        if len(strings_out) < 100:  # all data received - break
                            break

                if len(out_list) > 0:
                    str_io = StringIO("\r\n".join(out_list))
                    dfs.append(self._read_lines(str_io))  # add a new DataFrame
        finally:
            self.close()

        if len(dfs) == 0:
            raise OSError(f"{self.__class__.__name__} returned no data; check URL or correct a date")
        elif len(dfs) > 1:
            b = pd.concat(dfs, axis=0, join="outer", sort=True)
        else:
            b = dfs[0]
        return b

    def _read_core(self) -> pd.DataFrame:
        """Fetch data from the primary board for each ticker.

        Returns
        -------
        df : DataFrame
        """
        markets_n_engines, boards = self._get_metadata()
        b = self._read_all_boards_core()
        parts = []
        for secid in list(set(b["SECID"].tolist())):
            part = b[b["BOARDID"] == boards[secid]]
            parts.append(part)
        result = pd.concat(parts, axis=0)
        result = result.drop_duplicates()
        return result

    def _read_url_as_String(self, url: str, params: dict | None = None) -> str:
        """Open a URL and return raw text (retries on failure).

        Parameters
        ----------
        url : str
            Target URL.
        params : dict, optional
            Query parameters.

        Returns
        -------
        text : str
        """

        response = self._get_response(url, params=params)
        text = self._sanitize_response(response)
        if len(text) == 0:
            service = self.__class__.__name__
            raise OSError(f"{service} request returned no data; check URL for invalid inputs: {self.url}")
        if isinstance(text, bytes):
            text = text.decode("windows-1251")
        return text

    def _read_lines(self, input: StringIO) -> pd.DataFrame:
        """Parse CSV content from a StringIO into a DataFrame.

        Parameters
        ----------
        input : StringIO
            CSV content.

        Returns
        -------
        df : DataFrame
        """

        return pd.read_csv(
            input,
            index_col="TRADEDATE",
            parse_dates=True,
            sep=";",
            na_values=("-", "null"),
        )
