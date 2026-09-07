import pytest

from tools.run_extraction import DEFAULT_MAX_CONCURRENCY
from tools.run_extraction_gui import parse_max_concurrency, validate_inputs


def test_validate_inputs_passes_when_all_fields_present():
    assert validate_inputs("wh", "teams", "workbook", "out.sqlite") is None


def test_validate_inputs_fails_when_any_field_is_blank():
    assert validate_inputs("", "teams", "workbook", "out.sqlite") is not None
    assert validate_inputs("wh", "", "workbook", "out.sqlite") is not None
    assert validate_inputs("wh", "teams", "", "out.sqlite") is not None
    assert validate_inputs("wh", "teams", "workbook", "") is not None


def test_parse_max_concurrency_defaults_when_blank():
    assert parse_max_concurrency("") == DEFAULT_MAX_CONCURRENCY
    assert parse_max_concurrency("   ") == DEFAULT_MAX_CONCURRENCY


def test_parse_max_concurrency_parses_a_positive_integer():
    assert parse_max_concurrency("7") == 7


def test_parse_max_concurrency_rejects_non_positive_or_non_numeric_values():
    with pytest.raises(ValueError):
        parse_max_concurrency("0")
    with pytest.raises(ValueError):
        parse_max_concurrency("-1")
    with pytest.raises(ValueError):
        parse_max_concurrency("abc")
