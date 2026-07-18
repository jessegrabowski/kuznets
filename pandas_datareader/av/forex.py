import pandas as pd

from pandas_datareader._utils import RemoteDataError
from pandas_datareader.av import AlphaVantage


class AVForexReader(AlphaVantage):
    """Get Alpha Vantage Foreign Exchange (FX) exchange rate data."""

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        api_key: str | None = None,
        output_type: str = "pandas",
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str, optional
            Single currency pair (formatted ``'FROM/TO'``) or list of the same.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between consecutive queries.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        api_key : str, optional
            Alpha Vantage API key. If not provided the environmental variable
            ``ALPHAVANTAGE_API_KEY`` is read. The API key is *required*.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        super().__init__(
            symbols=symbols,
            start=None,
            end=None,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        )
        self.from_curr = {}
        self.to_curr = {}
        self.optional_params = {}
        if isinstance(symbols, str):
            self.symbols = [symbols]
        else:
            self.symbols = symbols
        try:
            for pair in self.symbols:
                self.from_curr[pair] = pair.split("/")[0]
                self.to_curr[pair] = pair.split("/")[1]
        except Exception as e:
            print(e)
            raise ValueError("Please input a currency pair formatted 'FROM/TO' or a list of currency symbols") from e

    def _present_tidy(self, payload):
        """One row per currency pair, with the rate fields as columns."""
        pairs = payload.T
        pairs.index.name = "Pair"
        return super()._present_tidy(pairs)

    @property
    def function(self) -> str:
        """Alpha Vantage endpoint function."""
        return "CURRENCY_EXCHANGE_RATE"

    @property
    def data_key(self) -> str:
        """Key of data returned from Alpha Vantage."""
        return "Realtime Currency Exchange Rate"

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        params = {"apikey": self.api_key, "function": self.function}
        params.update(self.optional_params)
        return params

    def _read_core(self) -> pd.DataFrame:
        """Fetch exchange rate data for all currency pairs.

        Returns
        -------
        df : DataFrame
        """
        result = []
        for pair in self.symbols:
            self.optional_params = {
                "from_currency": self.from_curr[pair],
                "to_currency": self.to_curr[pair],
            }
            data = super()._read_core()
            result.append(data)
        df = pd.concat(result, axis=1)
        df.columns = self.symbols
        return df

    def _read_lines(self, out: dict) -> pd.DataFrame:
        """Parse Alpha Vantage FX JSON response.

        Parameters
        ----------
        out : dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        try:
            df = pd.DataFrame.from_dict(out[self.data_key], orient="index")
        except KeyError as exc:
            raise RemoteDataError() from exc
        df.sort_index(ascending=True, inplace=True)
        df.index = [id[3:] for id in df.index]
        return df
