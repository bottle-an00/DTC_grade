import sqlite3

from dtc_transform.db_writer import write_sqlite
from dtc_transform.models import Row


def make_row(system, dtc, grade="D"):
    return Row(
        system=system, dtc=dtc, description="desc", warning_light="X",
        warning_message="X", limp_home="X", fail_safe="X", grade=grade,
        grading_background="bg", sheet="Sheet",
    )


def test_writes_expected_schema_and_rows(tmp_path):
    output = tmp_path / "out.sqlite"
    rows = [make_row("SYS2", "P000001", grade="B"), make_row("SYS1", "P000002", grade="A")]

    write_sqlite(rows, str(output))

    con = sqlite3.connect(str(output))
    cur = con.cursor()
    cur.execute('PRAGMA table_info(dtc_master)')
    columns = [c[1] for c in cur.fetchall()]
    assert columns == [
        "No", "System", "DTC", "Description", "Warning_Light",
        "Warning_Message", "Limp_Home", "Fail_Safe", "DTC Class",
    ]

    cur.execute('SELECT "No", System, DTC, "DTC Class" FROM dtc_master ORDER BY "No"')
    result = cur.fetchall()
    con.close()

    assert result == [
        (1, "SYS1", "P000002", "GSwsyYvDA+tNLWnROM9rCg=="),
        (2, "SYS2", "P000001", "4CDbt0Ai5c3St5tcEQKANA=="),
    ]


def test_overwrites_existing_table(tmp_path):
    output = tmp_path / "out.sqlite"
    write_sqlite([make_row("SYS1", "P000001")], str(output))
    write_sqlite([make_row("SYS2", "P000002")], str(output))

    con = sqlite3.connect(str(output))
    cur = con.cursor()
    cur.execute('SELECT COUNT(*) FROM dtc_master')
    count = cur.fetchone()[0]
    con.close()

    assert count == 1
