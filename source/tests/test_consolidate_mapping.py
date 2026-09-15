import csv

from tools.consolidate_mapping import consolidate, write_disagreement_csv


def test_single_entry_passes_through_with_its_own_name_as_alias():
    consolidated, disagreements = consolidate({"4WD(4WheelDrive)": {"system": "4WD", "source": "auto"}})

    key = next(iter(consolidated))
    assert consolidated[key]["system"] == "4WD"
    assert consolidated[key]["aliases"] == ["4WD(4WheelDrive)"]
    assert disagreements == []


def test_spelling_variants_agreeing_on_one_system_merge_without_a_disagreement():
    consolidated, disagreements = consolidate(
        {
            "4WD(4WheelDrive)": {"system": "4WD", "source": "auto"},
            "4WD (4 Wheel Drive)": {"system": "4WD", "source": "company_db"},
        }
    )

    assert len(consolidated) == 1
    key = next(iter(consolidated))
    assert consolidated[key]["system"] == "4WD"
    assert consolidated[key]["aliases"] == ["4WD (4 Wheel Drive)", "4WD(4WheelDrive)"]
    assert disagreements == []


def test_auto_beats_company_db_and_the_conflict_is_reported():
    consolidated, disagreements = consolidate(
        {
            "DHS(DoorHandleSensorModule)": {"system": "DHS_FL,DHS_FR", "source": "auto"},
            "DHS (Door Handle Sensor Module)": {"system": "DHS_FL,ENGINE", "source": "company_db"},
        }
    )

    key = next(iter(consolidated))
    assert consolidated[key]["system"] == "DHS_FL,DHS_FR"
    assert consolidated[key]["source"] == "auto"
    assert len(disagreements) == 1
    assert disagreements[0]["chosen"] == "DHS_FL,DHS_FR"
    assert disagreements[0]["rejected"] == [
        {"name": "DHS (Door Handle Sensor Module)", "source": "company_db", "system": "DHS_FL,ENGINE"}
    ]


def test_manual_beats_every_other_source():
    consolidated, _ = consolidate(
        {
            "AIRBAG": {"system": "AIRBAG_AUTO", "source": "auto"},
            "AIR BAG": {"system": "AIRBAG_CDB", "source": "company_db"},
            "Airbag": {"system": "AIRBAG_OK", "source": "manual"},
        }
    )

    key = next(iter(consolidated))
    assert consolidated[key]["system"] == "AIRBAG_OK"
    assert consolidated[key]["source"] == "manual"


def test_company_db_fills_a_key_no_other_source_covers():
    consolidated, disagreements = consolidate(
        {
            "BSD (Blind Spot Detection)": {"system": "RR_C_RADAR", "source": "company_db"},
        }
    )

    key = next(iter(consolidated))
    assert consolidated[key]["system"] == "RR_C_RADAR"
    assert consolidated[key]["source"] == "company_db"
    assert disagreements == []


def test_names_that_normalize_to_nothing_are_dropped():
    consolidated, _ = consolidate({" / () ": {"system": "X", "source": "auto"}})
    assert consolidated == {}


def test_disagreement_csv_lists_chosen_and_rejected_values(tmp_path):
    path = tmp_path / "disagreement.csv"
    write_disagreement_csv(
        str(path),
        [
            {
                "key": "dhs",
                "chosen": "DHS_FL,DHS_FR",
                "chosen_source": "auto",
                "chosen_name": "DHS(DoorHandleSensorModule)",
                "rejected": [{"name": "DHS (Door...)", "source": "company_db", "system": "DHS_FL,ENGINE"}],
            }
        ],
    )

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["key", "chosen_name", "chosen_source", "chosen_system", "rejected"]
    assert rows[1][3] == "DHS_FL,DHS_FR"
    assert rows[1][4] == "DHS (Door...)[company_db]=DHS_FL,ENGINE"
