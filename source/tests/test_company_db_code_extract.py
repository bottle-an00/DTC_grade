import pytest

from dtc_transform.company_db.code_extract import extract_compare_code


def test_extracts_last_four_chars_of_second_to_last_token():
    assert extract_compare_code("TEST_2009_1006101_001") == "6101"


def test_works_with_a_short_second_to_last_token():
    assert extract_compare_code("92710100_ABC_D2O6_001") == "D2O6"


def test_raises_when_fewer_than_two_tokens():
    with pytest.raises(ValueError):
        extract_compare_code("NOTOKENS")


def test_raises_when_second_to_last_token_is_too_short():
    with pytest.raises(ValueError):
        extract_compare_code("A_12_001")
