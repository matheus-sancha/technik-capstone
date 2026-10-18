"""Before You Start: prove the agent's identity can read what every later stage needs.

Connects as the service user with its key, exactly as the MCP server will. A missing grant fails
here, by name, instead of surfacing three stages later as an empty result set.

Run: uv run setup/check.py
"""
import os
import sys

import snowflake.connector
from dotenv import load_dotenv

GRANTED = ["V_WORK_ORDER_OPERATIONS", "V_RELEASED_REVISIONS", "SAP_QUALITY_NOTIFICATIONS", "TC_DOCUMENTS"]
NOT_GRANTED = ["SAP_WO_OPERATIONS", "TC_DRAWINGS"]  # behind the views: the agent must not read them


def agent_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="SNOWFLAKE_JWT",
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )


def check_grants(cur):
    failures = 0
    for name in GRANTED:
        try:
            rows = cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(f"PASS  reads {name} ({rows} rows)" if rows else f"FAIL  {name} is empty")
            failures += not rows
        except snowflake.connector.ProgrammingError as e:
            print(f"FAIL  cannot read {name}: {e.msg}")
            failures += 1
    for name in NOT_GRANTED:
        try:
            cur.execute(f"SELECT 1 FROM {name} LIMIT 1")
            print(f"FAIL  can read {name}, which the role should not reach")
            failures += 1
        except snowflake.connector.ProgrammingError:
            print(f"PASS  cannot read {name}")
    return failures


def check_data(cur):
    """One known answer through the view: welding at Plant 1 in September, duplicates removed."""
    pct = cur.execute("""
        SELECT ROUND(SUM(ROUTING_HOURS) / SUM(ACTUAL_HOURS) * 100, 1)
        FROM V_WORK_ORDER_OPERATIONS
        WHERE PLANT = 'Plant 1' AND OPERATION = 'Welding' AND OPERATION_STATUS = 'Confirmed'
          AND CONFIRMED_AT >= '2026-09-01' AND CONFIRMED_AT < '2026-10-01'""").fetchone()[0]
    ok = float(pct) == 88.9
    print(f"{'PASS' if ok else 'FAIL'}  welding efficiency at Plant 1 in September is {pct}% (expected 88.9%)")
    return not ok


def main():
    load_dotenv()
    with agent_connection() as conn:
        cur = conn.cursor()
        role = cur.execute("SELECT CURRENT_ROLE()").fetchone()[0]
        print(f"{'PASS' if role == 'TECHNIK_AGENT_RO' else 'FAIL'}  connected as {conn.user} with role {role}")
        failures = (role != "TECHNIK_AGENT_RO") + check_grants(cur) + check_data(cur)
    print("Ready for stage 1." if not failures else f"{failures} check(s) failed. Fix them before going on.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
