from dtc_transform.models import RawRow
from tools.derive_mapping import derive_mapping


def make_raw(sheet, dtc, description="desc"):
    return RawRow(
        sheet=sheet, dtc=dtc, description=description, warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade="D",
        grading_background="bg",
    )


def test_picks_majority_system_for_each_sheet():
    raw_rows = [
        make_raw("TCU(TransmissionControlUnit)", "P060241", "err a"),
        make_raw("TCU(TransmissionControlUnit)", "P060247", "err b"),
        make_raw("TCU(TransmissionControlUnit)", "P172546", "err c"),
    ]
    # (dtc, description, system) as found in the reference sqlite
    reference_rows = [
        ("P060241", "err a", "AT,CVT,AMT,IMT,DCT"),
        ("P060247", "err b", "AT,CVT,AMT,IMT,DCT"),
        ("P172546", "err c", "ENGINE"),  # generic code shared with another controller
    ]

    result = derive_mapping(raw_rows, reference_rows)

    assert result["TCU(TransmissionControlUnit)"]["system"] == "AT,CVT,AMT,IMT,DCT"
    assert result["TCU(TransmissionControlUnit)"]["hits"] == 3
    assert round(result["TCU(TransmissionControlUnit)"]["confidence"], 2) == 0.67


def test_sheet_with_no_reference_match_is_omitted():
    raw_rows = [make_raw("NEW_SHEET(NewController)", "P999999", "brand new")]
    reference_rows = [("P060241", "err a", "ENGINE")]

    result = derive_mapping(raw_rows, reference_rows)

    assert "NEW_SHEET(NewController)" not in result


def test_confidence_is_one_when_all_hits_agree():
    raw_rows = [make_raw("AVN(AudioVideoNavigation)", "P100000", "desc a")]
    reference_rows = [("P100000", "desc a", "AVN")]

    result = derive_mapping(raw_rows, reference_rows)

    assert result["AVN(AudioVideoNavigation)"]["confidence"] == 1.0


def test_manual_entry_in_existing_is_preserved_even_if_fresh_data_disagrees():
    # Fresh raw/reference data would compute "WRONG_SYSTEM" as the majority
    # vote for this sheet, but the existing mapping already has a manually
    # verified (and different) value for it. Re-running the tool must not
    # silently clobber that manual correction.
    raw_rows = [
        make_raw("MFSW(MultifunctionSwitch)", "P200000", "generic desc"),
        make_raw("MFSW(MultifunctionSwitch)", "P200001", "generic desc 2"),
    ]
    reference_rows = [
        ("P200000", "generic desc", "WRONG_SYSTEM"),
        ("P200001", "generic desc 2", "WRONG_SYSTEM"),
    ]
    existing = {
        "MFSW(MultifunctionSwitch)": {
            "confidence": 1.0,
            "hits": 10,
            "system": "MFSW",
            "source": "manual",
            "note": "manually corrected, verified against reference sqlite",
        }
    }

    result = derive_mapping(raw_rows, reference_rows, existing=existing)

    assert result["MFSW(MultifunctionSwitch)"] == existing["MFSW(MultifunctionSwitch)"]
