import datetime as dt
import re
import tempfile
from zipfile import ZipFile

from pandas import DataFrame, read_csv, to_datetime

from pandas_datareader.base import _BaseReader
from pandas_datareader.compat import PYTHON_LT_3_10, StringIO

_URL = "http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
_URL_PREFIX = "ftp/"
_URL_SUFFIX = "_CSV.zip"


def get_available_datasets(**kwargs) -> list[str]:
    """
    Get the list of datasets available from the Fama/French data library.

    Parameters
    ----------
    session : Session, default None
        ``requests.sessions.Session`` instance to be used.

    Returns
    -------
    list of str
        A list of valid inputs for get_data_famafrench.
    """
    return FamaFrenchReader(symbols="", **kwargs).get_available_datasets()


def _parse_date_famafrench(x: str) -> dt.datetime:
    x = x.strip()
    try:
        return dt.datetime.strptime(x, "%Y%m")
    except Exception:
        pass
    return to_datetime(x)


class FamaFrenchReader(_BaseReader):
    """
    Get data for the given name from the Fama/French data library.

    For annual and monthly data, index is a pandas.PeriodIndex, otherwise it's a
    pandas.DatetimeIndex.
    """

    @property
    def url(self) -> str:
        """API URL."""
        return "".join([_URL, _URL_PREFIX, self.symbols, _URL_SUFFIX])

    def _read_zipfile(self, url: str) -> str:
        """Download and extract the first file from a ZIP archive.

        Parameters
        ----------
        url : str
            URL of the ZIP file.

        Returns
        -------
        data : str
            Contents of the first file in the archive.
        """
        raw = self._get_response(url).content

        with tempfile.TemporaryFile() as tmpf:
            tmpf.write(raw)
            with ZipFile(tmpf, "r") as zf:
                try:
                    data = zf.open(zf.namelist()[0]).read().decode("utf-8", "ignore")
                except UnicodeDecodeError:
                    data = zf.open(zf.namelist()[0]).read().decode(encoding="cp1252")
        return data

    def read(self) -> dict[int | str, DataFrame]:
        """
        Read data.

        Returns
        -------
        datasets : dict of int or str to DataFrame
            A dictionary of DataFrames. Tables are accessed by integer keys. See df['DESCR'] for a
            description of the data set.
        """
        return super().read()

    def _read_one_data(self, url: str, params) -> dict[int | str, DataFrame]:
        params = {
            "index_col": 0,
        }

        # headers in these files are not valid
        if self.symbols.endswith("_Breakpoints"):
            if self.symbols.find("-") > -1:
                c = ["<=0", ">0"]
            else:
                c = ["Count"]
            r = list(range(0, 105, 5))

            if PYTHON_LT_3_10:
                additional_params = list(zip(r, r[1:]))  # noqa: B905
            else:
                additional_params = list(zip(r, r[1:], strict=False))
            params["names"] = ["Date"] + c + additional_params

            if self.symbols != "Prior_2-12_Breakpoints":
                params["skiprows"] = 1
            else:
                params["skiprows"] = 3

        doc_chunks, tables = [], []
        data = self._read_zipfile(url)

        for chunk in data.split(2 * "\r\n"):
            if len(chunk) < 800:
                doc_chunks.append(chunk.replace("\r\n", " ").strip())
            else:
                tables.append(chunk)

        datasets, table_desc = {}, []
        for i, src in enumerate(tables):
            match = re.search(r"^\s*,", src, re.M)  # the table starts there
            start = 0 if not match else match.start()

            df = read_csv(StringIO("Date" + src[start:]), **params)
            idx = df.index.astype(str)
            # Dates are bare integers whose width encodes the frequency: YYYY (annual),
            # YYYYMM (monthly), or YYYYMMDD (daily). Daily tables keep a DatetimeIndex;
            # annual and monthly collapse to a PeriodIndex.
            if df.index.min() > 19000000:
                df.index = to_datetime(idx, format="%Y%m%d")
            elif df.index.min() > 190000:
                df.index = to_datetime(idx, format="%Y%m").to_period(freq="M")
            else:
                df.index = to_datetime(idx, format="%Y").to_period(freq="Y")
            df = df.truncate(self.start, self.end)
            datasets[i] = df

            title = src[:start].replace("\r\n", " ").strip()
            shape = "({} rows x {} cols)".format(*df.shape)
            table_desc.append(f"{title} {shape}".strip())

        descr = "{}\n{}\n\n".format(self.symbols.replace("_", " "), len(self.symbols) * "-")
        if doc_chunks:
            descr += " ".join(doc_chunks).replace(2 * " ", " ") + "\n\n"
        table_descr = ("{:3} : {}".format(*x) for x in enumerate(table_desc))
        datasets["DESCR"] = descr + "\n".join(table_descr)

        return datasets

    def get_available_datasets(self) -> list[str]:
        """
        Get the list of datasets available from the Fama/French data library.

        Returns
        -------
        list of str
            A list of valid inputs for get_data_famafrench.
        """
        try:
            from lxml.html import document_fromstring
        except ImportError as exc:
            raise ImportError("Please install lxml if you want to use the get_datasets_famafrench function") from exc

        response = self.session.get(_URL + "data_library.html")
        root = document_fromstring(response.content)

        datasets = [e.attrib["href"] for e in root.findall(".//a") if "href" in e.attrib]
        datasets = [ds for ds in datasets if ds.startswith(_URL_PREFIX) and ds.endswith(_URL_SUFFIX)]

        return [x[len(_URL_PREFIX) : -len(_URL_SUFFIX)] for x in datasets]
