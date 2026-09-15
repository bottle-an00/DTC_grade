import pytest

from tools.run_extraction import DEFAULT_CHUNK_SIZE, DEFAULT_MAX_CONCURRENCY
from tools.run_extraction_gui import OPTION_HELP_LINES, parse_positive_int, validate_inputs


def test_validate_inputs_passes_when_all_fields_present():
    assert validate_inputs("wh", "teams-webhook", "workbook", "out.sqlite") is None


def test_validate_inputs_fails_when_any_field_is_blank():
    assert validate_inputs("", "teams-webhook", "workbook", "out.sqlite") is not None
    assert validate_inputs("wh", "", "workbook", "out.sqlite") is not None
    assert validate_inputs("wh", "teams-webhook", "", "out.sqlite") is not None
    assert validate_inputs("wh", "teams-webhook", "workbook", "") is not None


def test_blank_field_falls_back_to_the_given_default():
    assert parse_positive_int("", DEFAULT_MAX_CONCURRENCY, "동시 요청 수") == DEFAULT_MAX_CONCURRENCY
    assert parse_positive_int("   ", DEFAULT_CHUNK_SIZE, "분할 크기") == DEFAULT_CHUNK_SIZE


def test_parses_a_positive_integer():
    assert parse_positive_int("7", DEFAULT_MAX_CONCURRENCY, "동시 요청 수") == 7
    assert parse_positive_int("20", DEFAULT_CHUNK_SIZE, "분할 크기") == 20


def test_rejects_non_positive_or_non_numeric_values():
    with pytest.raises(ValueError):
        parse_positive_int("0", DEFAULT_CHUNK_SIZE, "분할 크기")
    with pytest.raises(ValueError):
        parse_positive_int("-1", DEFAULT_CHUNK_SIZE, "분할 크기")
    with pytest.raises(ValueError):
        parse_positive_int("abc", DEFAULT_CHUNK_SIZE, "분할 크기")


def test_the_error_names_the_field_so_the_dialog_can_say_which_one():
    with pytest.raises(ValueError, match="분할 크기"):
        parse_positive_int("0", DEFAULT_CHUNK_SIZE, "분할 크기")
    with pytest.raises(ValueError, match="동시 요청 수"):
        parse_positive_int("0", DEFAULT_MAX_CONCURRENCY, "동시 요청 수")


# The two numeric options are the only settings an operator can get wrong in a
# way that makes a run fail, so each one's help line has to say what it does
# and what goes wrong if it's pushed too far.
def test_each_option_has_a_help_line_naming_it_and_its_failure_mode():
    assert len(OPTION_HELP_LINES) == 2
    chunk_line, concurrency_line = OPTION_HELP_LINES
    assert "분할 크기" in chunk_line
    assert "시간 초과" in chunk_line and "메모리 부족" in chunk_line
    assert "동시 요청 수" in concurrency_line
    assert "한도를 초과" in concurrency_line
