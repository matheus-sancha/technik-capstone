"""A fake Snowflake connection for offline tests: SQLite in memory, loaded from seed/data/.

It exposes only the five objects TECHNIK_AGENT_RO is granted (seed/03_access.sql), built from the
same rows the seed loads. The views are SQLite translations of seed/02_views.sql, so a query that
reaches a table behind a view fails here as it would for the real role.
"""
import csv
import re
import sqlite3
from pathlib import Path

DATA = Path(__file__).parent.parent / "seed" / "data"
RAW = ["SAP_WORK_ORDERS", "SAP_WO_OPERATIONS", "SAP_QUALITY_NOTIFICATIONS", "TC_PARTS", "TC_DRAWINGS",
       "TC_DOCUMENTS", "TC_CNC_PROGRAMS", "TC_ECNS", "TC_ECN_AFFECTED_ITEMS"]

# Snowflake sorts NULL first in a descending order; SQLite needs it said.
LATEST_CONFIRMATION = """
    SELECT o.*, w.PLANT, w.PROJECT_ID, w.PART_NO, w.STATUS AS WO_STATUS FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY WO_NO, OP_SEQ
                                     ORDER BY CONFIRMATION_NO DESC NULLS FIRST) AS RN
        FROM raw.SAP_WO_OPERATIONS) o
    JOIN raw.SAP_WORK_ORDERS w ON w.WO_NO = o.WO_NO
    WHERE w.STATUS <> 'CRTD' AND o.RN = 1"""

GRANTED = {
    "V_WORK_ORDER_OPERATIONS": f"""
        SELECT WO_NO AS WORK_ORDER, OP_SEQ AS OPERATION_SEQ, OPERATION, WORK_CENTER AS WORK_CENTRE, PLANT,
               PROJECT_ID AS PROJECT, PART_NO AS PART_NUMBER,
               CASE STATUS WHEN 'OPEN' THEN 'Not started' WHEN 'INPROC' THEN 'In progress'
                           WHEN 'CNF' THEN 'Confirmed' END AS OPERATION_STATUS,
               CASE WO_STATUS WHEN 'REL' THEN 'Released' WHEN 'PCNF' THEN 'Partly confirmed'
                              WHEN 'CNF' THEN 'Confirmed' WHEN 'TECO' THEN 'Technically complete'
               END AS WORK_ORDER_STATUS,
               CAST(ROUTING_HOURS AS REAL) AS ROUTING_HOURS, CAST(ACTUAL_HOURS AS REAL) AS ACTUAL_HOURS,
               CONFIRMED_AT
        FROM ({LATEST_CONFIRMATION})""",
    "V_OPERATION_DOCUMENTS": f"""
        WITH ops AS ({LATEST_CONFIRMATION})
        SELECT WO_NO AS WORK_ORDER, OP_SEQ AS OPERATION_SEQ, OPERATION, DRAWING_NO AS ITEM_NO,
               'Drawing' AS ITEM_TYPE, DRAWING_REV AS REVISION FROM ops WHERE DRAWING_NO IS NOT NULL
        UNION ALL
        SELECT WO_NO, OP_SEQ, OPERATION, CNC_PROGRAM_NO, 'CNC Program', CNC_PROGRAM_REV
        FROM ops WHERE CNC_PROGRAM_NO IS NOT NULL
        UNION ALL
        SELECT WO_NO, OP_SEQ, OPERATION, WORK_INSTRUCTION_NO, 'Document', NULL
        FROM ops WHERE WORK_INSTRUCTION_NO IS NOT NULL""",
    "V_RELEASED_REVISIONS": """
        WITH items AS (
            SELECT PART_NO AS ITEM_NO, 'Part' AS ITEM_TYPE, DESCRIPTION AS TITLE, REVISION, RELEASED_AT
              FROM raw.TC_PARTS WHERE RELEASE_STATUS = 'Released'
            UNION ALL
            SELECT DRAWING_NO, 'Drawing', TITLE, REVISION, RELEASED_AT
              FROM raw.TC_DRAWINGS WHERE RELEASE_STATUS = 'Released'
            UNION ALL
            SELECT PROGRAM_NO, 'CNC Program', 'CNC program for ' || PART_NO || ' on ' || MACHINE, REVISION,
                   RELEASED_AT FROM raw.TC_CNC_PROGRAMS WHERE RELEASE_STATUS = 'Released'
            UNION ALL
            SELECT DOC_NO, 'Document', TITLE, REVISION, RELEASED_AT
              FROM raw.TC_DOCUMENTS WHERE STATUS = 'Released')
        SELECT i.*, e.ECN_NO, e.TITLE AS ECN_TITLE
        FROM items i
        LEFT JOIN raw.TC_ECN_AFFECTED_ITEMS a ON a.ITEM_NO = i.ITEM_NO AND a.TO_REV = i.REVISION
        LEFT JOIN raw.TC_ECNS e ON e.ECN_NO = a.ECN_NO AND e.STATUS = 'Released'""",
    "SAP_QUALITY_NOTIFICATIONS": "SELECT * FROM raw.SAP_QUALITY_NOTIFICATIONS",
    "TC_DOCUMENTS": "SELECT * FROM raw.TC_DOCUMENTS",
}


def load_raw(db):
    db.execute("ATTACH ':memory:' AS raw")
    for table in RAW:
        with open(DATA / f"{table}.csv", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            db.execute(f"CREATE TABLE raw.{table} ({', '.join(header)})")
            marks = ", ".join("?" * len(header))
            db.executemany(f"INSERT INTO raw.{table} VALUES ({marks})",
                           ([value or None for value in row] for row in reader))


class FakeCursor:
    """Takes Snowflake's %(name)s parameters, as the server sends them."""

    def __init__(self, db):
        self._cur = db.cursor()

    def execute(self, sql, params=None):
        self._cur.execute(re.sub(r"%\((\w+)\)s", r":\1", sql), params or {})
        return self

    @property
    def description(self):
        return self._cur.description

    def fetchall(self):
        return self._cur.fetchall()

    def fetchone(self):
        return self._cur.fetchone()


class FakeConnection:
    def __init__(self):
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        load_raw(self._db)
        for name, sql in GRANTED.items():
            self._db.execute(f"CREATE TABLE main.{name} AS {sql}")
        self._db.commit()
        self._db.execute("DETACH raw")

    def cursor(self):
        return FakeCursor(self._db)

    def close(self):
        self._db.close()
