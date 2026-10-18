"""Stage 2: an MCP server over Teamcenter, with three narrow tools.

It reads the Teamcenter views as the agent's service user, so it sees exactly what setup/check.py
proved the role can read. VS Code starts it over stdio from .vscode/mcp.json.

Run: uv run server/teamcenter.py
"""
import os
from functools import cache
from typing import Annotated

import snowflake.connector
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

WorkOrder = Annotated[str, Field(pattern=r"^1\d{8}$", description="SAP work order number, for example 100004521")]
OperationSeq = Annotated[str, Field(pattern=r"^\d{4}$", description="Operation in the routing, for example 0020")]
DocNo = Annotated[str, Field(pattern=r"^[A-Z]{3}\d{8}$", description="Document number, for example SWI70000318")]
ItemNo = Annotated[str, Field(pattern=r"^[A-Z]{1,3}\d{8,10}$",
                              description="Part, drawing, CNC program or document number, for example DU700001042")]
Revision = Annotated[str, Field(pattern=r"^[A-Z]{1,2}$", description="Revision letter, for example B")]

mcp = MCPServer("technik-teamcenter", instructions=(
    "Read-only lookups in Technik's Teamcenter: controlled documents, the items each work order "
    "operation uses, and whether a revision is the released one. It holds metadata, not document text."))


def connect():
    load_dotenv()
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


@cache
def connection():
    return connect()


def rows(sql, **params):
    """Run one query with bound parameters and return its rows as dicts keyed by column name."""
    cur = connection().cursor()
    cur.execute(sql, params)
    names = [column[0] for column in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def day(value):
    return str(value)[:10] if value else "never"


@mcp.tool()
def get_document(doc_no: DocNo) -> str:
    """Look up a controlled document (SOP, SWI, GWI, TDS, DGL or DCP) by its number.

    Returns its title, type and owner, and every revision with its status and review date.
    Use it for a document's metadata. It does not return the document's text.
    """
    revisions = rows("""SELECT DOC_TYPE, REVISION, TITLE, OWNER, STATUS, RELEASED_AT, NEXT_REVIEW_DATE
                        FROM TC_DOCUMENTS WHERE DOC_NO = %(doc_no)s ORDER BY REVISION DESC""", doc_no=doc_no)
    if not revisions:
        raise ToolError(f"No document {doc_no} in Teamcenter. Check the number with the user. "
                        "Do not describe a document you could not find.")
    first = revisions[0]
    lines = [f"{doc_no}: {first['TITLE']} ({first['DOC_TYPE']}), owner {first['OWNER']}"]
    for r in revisions:
        released = f", released {day(r['RELEASED_AT'])}, next review {day(r['NEXT_REVIEW_DATE'])}" \
            if r["STATUS"] == "Released" else ""
        lines.append(f"  rev {r['REVISION']}: {r['STATUS']}{released}")
    return "\n".join(lines)


@mcp.tool()
def list_operation_documents(work_order: WorkOrder, operation_seq: OperationSeq) -> str:
    """List the drawing, CNC program and work instruction one work order operation uses.

    Drawings and CNC programs come with the revision the operation was released against. Check
    whether that revision is still the released one with get_revision_status.
    """
    items = rows("""SELECT OPERATION, ITEM_NO, ITEM_TYPE, REVISION FROM V_OPERATION_DOCUMENTS
                    WHERE WORK_ORDER = %(wo)s AND OPERATION_SEQ = %(op)s ORDER BY ITEM_TYPE DESC""",
                 wo=work_order, op=operation_seq)
    if not items:
        return no_items(work_order, operation_seq)
    lines = [f"{work_order} operation {operation_seq} ({items[0]['OPERATION']}) uses:"]
    for i in items:
        revision = f"rev {i['REVISION']}" if i["REVISION"] else "the current released revision"
        lines.append(f"  {i['ITEM_TYPE']} {i['ITEM_NO']}, {revision}")
    return "\n".join(lines)


def no_items(work_order, operation_seq):
    """Say why an operation has no linked items: it has none, or the operation does not exist."""
    ops = rows("""SELECT OPERATION_SEQ, OPERATION FROM V_WORK_ORDER_OPERATIONS
                  WHERE WORK_ORDER = %(wo)s ORDER BY OPERATION_SEQ""", wo=work_order)
    if not ops:
        raise ToolError(f"No released work order {work_order}. Check the number with the user.")
    for op in ops:
        if op["OPERATION_SEQ"] == operation_seq:
            return f"{work_order} operation {operation_seq} ({op['OPERATION']}) uses no drawing, " \
                   "CNC program or work instruction in Teamcenter."
    listed = ", ".join(f"{op['OPERATION_SEQ']} {op['OPERATION']}" for op in ops)
    raise ToolError(f"Work order {work_order} has no operation {operation_seq}. Its operations are: {listed}.")


@mcp.tool()
def get_revision_status(item_no: ItemNo, revision: Revision | None = None) -> str:
    """Say whether a revision of a part, drawing, CNC program or document is the released one.

    Leave out the revision to get the released revision. A revision that is not released was
    either superseded or is still in work; the answer names the released one and its change notice.
    """
    released = rows("""SELECT ITEM_TYPE, TITLE, REVISION, RELEASED_AT, ECN_NO, ECN_TITLE
                       FROM V_RELEASED_REVISIONS WHERE ITEM_NO = %(item)s""", item=item_no)
    if not released:
        raise ToolError(f"{item_no} has no released revision in Teamcenter. It may not exist, "
                        "or may never have been released. Do not treat any revision of it as approved.")
    r = released[0]
    via = f" under {r['ECN_NO']} ({r['ECN_TITLE']})" if r["ECN_NO"] else ""
    current = f"rev {r['REVISION']}, released {day(r['RELEASED_AT'])}{via}"
    if revision is None or revision == r["REVISION"]:
        return f"{r['ITEM_TYPE']} {item_no} ({r['TITLE']}): the released revision is {current}."
    return f"{r['ITEM_TYPE']} {item_no} ({r['TITLE']}): rev {revision} is NOT released. " \
           f"The released revision is {current}."


if __name__ == "__main__":
    mcp.run()
