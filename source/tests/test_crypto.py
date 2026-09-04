import pytest

from dtc_transform.crypto import InvalidGradeError, encrypt_grade


def test_encrypts_known_grades():
    assert encrypt_grade("A") == "GSwsyYvDA+tNLWnROM9rCg=="
    assert encrypt_grade("B") == "4CDbt0Ai5c3St5tcEQKANA=="
    assert encrypt_grade("C") == "Loxt0sBGAIWprCbYyMZIFw=="
    assert encrypt_grade("D") == "AVX59pdiJ/jHbW3BIX/SMg=="


def test_raises_on_unknown_grade():
    with pytest.raises(InvalidGradeError):
        encrypt_grade("E")


def test_raises_on_empty_grade():
    with pytest.raises(InvalidGradeError):
        encrypt_grade("")
