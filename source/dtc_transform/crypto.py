GRADE_CIPHER = {
    "A": "GSwsyYvDA+tNLWnROM9rCg==",
    "B": "4CDbt0Ai5c3St5tcEQKANA==",
    "C": "Loxt0sBGAIWprCbYyMZIFw==",
    "D": "AVX59pdiJ/jHbW3BIX/SMg==",
}


class InvalidGradeError(Exception):
    pass


def encrypt_grade(grade: str) -> str:
    try:
        return GRADE_CIPHER[grade]
    except KeyError:
        raise InvalidGradeError(f"Unknown grade: {grade!r}") from None
