"""Stage 2's three tools, called directly against the fake Snowflake, through the model's eyes."""
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from teamcenter import get_document, get_revision_status, list_operation_documents


def test_document_lists_every_revision_with_its_status():
    text = get_document("SWI70000318")
    assert text.startswith("SWI70000318: Cladding Preparation and Inspection (SWI), owner Marte Lien")
    assert "rev C: In Work" in text
    assert "rev B: Released, released 2024-09-30, next review 2026-09-30" in text
    assert "rev A: Obsolete" in text


def test_unknown_document_is_an_error_the_model_can_act_on():
    with pytest.raises(ToolError, match="No document SWI70000381"):
        get_document("SWI70000381")  # the number the injection lesson's QN text invents


def test_operation_lists_drawing_program_and_work_instruction():
    text = list_operation_documents("100004510", "0010")
    assert text.splitlines() == [
        "100004510 operation 0010 (Machining) uses:",
        "  Drawing DU700001042, rev B",
        "  Document SWI70000331, the current released revision",
        "  CNC Program T7000000217, rev B",
    ]


def test_operation_without_linked_items_says_so():
    assert list_operation_documents("100004519", "0030") == (
        "100004519 operation 0030 (Coating) uses no drawing, CNC program or work instruction in Teamcenter.")


def test_missing_operation_names_the_ones_that_exist():
    with pytest.raises(ToolError, match=r"has no operation 0090\. Its operations are: 0010 Machining, "):
        list_operation_documents("100004521", "0090")


def test_unknown_work_order_is_an_error():
    with pytest.raises(ToolError, match="No released work order 199999999"):
        list_operation_documents("199999999", "0010")


def test_superseded_revision_names_the_released_one_and_its_ecn():
    text = get_revision_status("DU700001042", "B")
    assert "rev B is NOT released" in text
    assert "rev C, released 2026-09-15 under ECN70000051" in text


def test_released_revision_and_no_revision_agree():
    assert get_revision_status("T7000000217") == get_revision_status("T7000000217", "B")
    assert "the released revision is rev B" in get_revision_status("T7000000217")


def test_never_released_item_is_an_error():
    with pytest.raises(ToolError, match="has no released revision"):
        get_revision_status("SWI70000381")
