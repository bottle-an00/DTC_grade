import sqlite3

from .crypto import encrypt_grade
from .models import Row

SCHEMA = """
CREATE TABLE "dtc_master" (
    "No" INTEGER,
    "System" TEXT,
    "DTC" TEXT,
    "Description" TEXT,
    "Warning_Light" TEXT,
    "Warning_Message" TEXT,
    "Limp_Home" TEXT,
    "Fail_Safe" TEXT,
    "DTC Class" TEXT
)
"""


def write_sqlite(rows: list[Row], output_path: str) -> None:
    sorted_rows = sorted(rows, key=lambda r: (r.system, r.dtc))

    con = sqlite3.connect(output_path)
    try:
        cur = con.cursor()
        cur.execute("DROP TABLE IF EXISTS dtc_master")
        cur.execute(SCHEMA)
        for i, row in enumerate(sorted_rows, start=1):
            cur.execute(
                'INSERT INTO dtc_master VALUES (?,?,?,?,?,?,?,?,?)',
                (
                    i,
                    row.system,
                    row.dtc,
                    row.description,
                    row.warning_light,
                    row.warning_message,
                    row.limp_home,
                    row.fail_safe,
                    encrypt_grade(row.grade),
                ),
            )
        con.commit()
    finally:
        con.close()
