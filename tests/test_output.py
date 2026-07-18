import importlib.util

import pytest

from pandas_datareader._output import validate_output_type

pytestmark = pytest.mark.stable


class TestValidateOutputType:
    def test_pandas_passes_without_backend_check(self, monkeypatch):
        def forbidden(name):
            raise AssertionError("pandas must not trigger a backend availability check")

        monkeypatch.setattr(importlib.util, "find_spec", forbidden)
        assert validate_output_type("pandas") == "pandas"

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("polars", "polars"),
            ("POLARS", "polars"),
            ("pyarrow", "pyarrow"),
            ("arrow", "pyarrow"),
            ("Arrow", "pyarrow"),
            ("dask", "dask"),
        ],
    )
    def test_canonicalization(self, monkeypatch, name, expected):
        monkeypatch.setattr(importlib.util, "find_spec", lambda module: object())
        assert validate_output_type(name) == expected

    def test_unknown_backend_raises_value_error(self):
        with pytest.raises(ValueError, match="output_type='modin' is not supported"):
            validate_output_type("modin")

    def test_error_message_lists_valid_backends(self):
        with pytest.raises(ValueError, match="'arrow'.*'dask'.*'pandas'.*'polars'.*'pyarrow'"):
            validate_output_type("bogus")

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError, match="must be a str"):
            validate_output_type(object())

    def test_missing_backend_raises_import_error_with_extra_hint(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda module: None)
        with pytest.raises(ImportError, match=r"pip install pandas-datareader\[polars\]"):
            validate_output_type("polars")

    def test_missing_parent_module_raises_import_error(self, monkeypatch):
        def raise_module_not_found(module):
            raise ModuleNotFoundError(f"No module named {module.partition('.')[0]!r}")

        monkeypatch.setattr(importlib.util, "find_spec", raise_module_not_found)
        with pytest.raises(ImportError, match=r"optional dependency 'dask'"):
            validate_output_type("dask")
