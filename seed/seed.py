"""Seed TECHNIK_DW.OPS in your Snowflake account and create the agent's role, warehouse and service user.

Run once, as an admin: uv run seed/seed.py
Re-running replaces the tables and their rows, and keeps the role, user and key.
"""
import os
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv

SEED = Path(__file__).parent
TABLES = ["SAP_PROJECTS", "SAP_UNITS", "SAP_BOM_LINES", "SAP_WORK_ORDERS", "SAP_WO_OPERATIONS",
          "SAP_QUALITY_NOTIFICATIONS", "TC_PARTS", "TC_DRAWINGS", "TC_DOCUMENTS", "TC_CNC_PROGRAMS",
          "TC_ECNS", "TC_ECN_AFFECTED_ITEMS", "FAT_RESULTS"]


def admin_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_ADMIN_USER"],
        authenticator="PROGRAMMATIC_ACCESS_TOKEN",
        token=os.environ["SNOWFLAKE_ADMIN_TOKEN"],
        warehouse=os.environ["SNOWFLAKE_ADMIN_WAREHOUSE"],
    )


def run_file(conn, name):
    for cursor in conn.execute_string((SEED / name).read_text(encoding="utf-8")):
        cursor.close()


def load_rows(conn):
    """Upload seed/data/*.csv to a temporary stage and copy each file into its table."""
    cur = conn.cursor()
    cur.execute("CREATE TEMPORARY STAGE SEED_STAGE")
    cur.execute("CREATE TEMPORARY FILE FORMAT SEED_CSV TYPE = CSV SKIP_HEADER = 1 "
                "FIELD_OPTIONALLY_ENCLOSED_BY = '\"' EMPTY_FIELD_AS_NULL = TRUE")
    cur.execute(f"PUT 'file://{(SEED / 'data').as_posix()}/*.csv' @SEED_STAGE OVERWRITE = TRUE")
    for table in TABLES:
        source = f"@SEED_STAGE/{table}.csv.gz"
        if table == "FAT_RESULTS":  # RAW is VARIANT: parse the JSON column on the way in
            source = f"(SELECT $1, $2, $3, $4, $5, PARSE_JSON($6) FROM {source})"
        cur.execute(f"COPY INTO {table} FROM {source} FILE_FORMAT = (FORMAT_NAME = SEED_CSV)")
        print(f"  {table}: {cur.fetchone()[3]} rows")


def public_key(key_file):
    """Create the service user's key pair on first run. Returns the public key for ALTER USER."""
    if not key_file.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_file.parent.mkdir(exist_ok=True)
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                               serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    return "".join(pem.decode().splitlines()[1:-1])


def main():
    load_dotenv()
    with admin_connection() as conn:
        conn.cursor().execute("USE ROLE SYSADMIN")
        print("Tables:")
        run_file(conn, "01_tables.sql")
        load_rows(conn)
        print("Views")
        run_file(conn, "02_views.sql")
        print("Role, warehouse and service user")
        run_file(conn, "03_access.sql")
        key = public_key(SEED.parent / os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"])
        conn.cursor().execute(f"ALTER USER TECHNIK_AGENT_SVC SET RSA_PUBLIC_KEY = '{key}'")
    print("Done. Now run: uv run setup/check.py")


if __name__ == "__main__":
    main()
