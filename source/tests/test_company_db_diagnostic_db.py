from dtc_transform.company_db.diagnostic_db import (
    build_diagnostic_index,
    is_target_file,
    read_systemid,
)


def test_is_target_file_accepts_d0_and_a0_suffix_case_insensitive():
    assert is_target_file("0010D0.xml") is True
    assert is_target_file("0010A0.xml") is True
    assert is_target_file("0010d0.xml") is True


def test_is_target_file_rejects_other_suffixes():
    assert is_target_file("0010N0.xml") is False
    assert is_target_file("202301.xml") is False


def _write_systemtree(path, systemid):
    path.write_text(
        f'<systemtree systemid="{systemid}" mmcid="" mmctype="bcm">'
        "<commset></commset></systemtree>",
        encoding="utf-8",
    )


def test_read_systemid_returns_root_attribute(tmp_path):
    xml_path = tmp_path / "sample.xml"
    _write_systemtree(xml_path, "TEST_2009_1006101_001")

    assert read_systemid(str(xml_path)) == "TEST_2009_1006101_001"


def test_build_diagnostic_index_skips_non_target_files_without_parsing_them(tmp_path):
    region_dir = tmp_path / "HMA"
    region_dir.mkdir()

    _write_systemtree(region_dir / "0010D0.xml", "TEST_2009_1006101_001")
    _write_systemtree(region_dir / "0011A0.xml", "TEST_2009_9998888_001")
    # Not a target suffix -- must be skipped even though it would parse fine.
    _write_systemtree(region_dir / "0012N0.xml", "TEST_2009_1006101_001")
    # A target suffix but unparsable content -- must not crash the build.
    (region_dir / "0013D0.xml").write_text("not xml at all", encoding="utf-8")

    index = build_diagnostic_index(str(tmp_path))

    # The stored "document title" is the 4-char prefix, with the D0/A0
    # region suffix stripped off -- that's what vehicle_info's ecucode
    # matches against, not the full 6-char filename.
    assert sorted(index["6101"]) == ["0010"]
    assert index["8888"] == ["0011"]
    assert "0012" not in [f for files in index.values() for f in files]
    assert "0013" not in [f for files in index.values() for f in files]


def test_build_diagnostic_index_walks_nested_region_folders(tmp_path):
    for region in ("HMA", "KMC"):
        region_dir = tmp_path / region
        region_dir.mkdir()
        _write_systemtree(region_dir / "0020D0.xml", "TEST_2009_5551234_001")

    index = build_diagnostic_index(str(tmp_path))

    assert sorted(index["1234"]) == ["0020", "0020"]
