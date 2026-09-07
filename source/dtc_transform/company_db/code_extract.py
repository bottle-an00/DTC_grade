def extract_compare_code(code: str) -> str:
    """Split on '_' and take the last 4 characters of the second-to-last
    token -- the shared rule for turning an ECU DOC document code or a
    diagnostic-DB systemid into a 4-character comparison key."""
    tokens = code.split("_")
    if len(tokens) < 2:
        raise ValueError(f"code has no second-to-last token: {code!r}")

    second_last = tokens[-2]
    if len(second_last) < 4:
        raise ValueError(f"second-to-last token too short: {code!r}")

    return second_last[-4:]
