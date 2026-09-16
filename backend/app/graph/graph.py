"""Assembles the LangGraph `StateGraph` for the Tax Document Intake &
Classification Assistant.

    START -> ingest -> classify --route_after_classify--> extract_w2 ------\
                                                        -> extract_1099nec -\
                                                        -> extract_1099int --+--> cross_check -> review -> finalize -> END
                                                        -> extract_1099div -/
                                                        -> extract_k1 -----/
                                                        -> extract_bank_statement
                                                        -> extract_other --/

The branch point is right after `classify`: each document type has its own
extraction node using the pydantic schema and prompt that match its real
IRS box layout (see `app/graph/extraction_schema.py`) -- a W-2's boxes have
nothing in common with a K-1's, so this is a genuine conditional-routing
case rather than one generic "extract fields" step. Every extraction node
converges back onto the same `cross_check -> review -> finalize` tail.
`review`'s `interrupt()` is the other load-bearing piece of control flow
here -- see `app/graph/nodes.py::review_node`.
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    classify_node,
    cross_check_node,
    extract_1099div_node,
    extract_1099int_node,
    extract_1099nec_node,
    extract_bank_statement_node,
    extract_k1_node,
    extract_other_node,
    extract_w2_node,
    finalize_node,
    ingest_node,
    review_node,
    route_after_classify,
)
from app.graph.state import TaxIntakeState

_EXTRACTION_NODES = {
    "extract_w2": extract_w2_node,
    "extract_1099nec": extract_1099nec_node,
    "extract_1099int": extract_1099int_node,
    "extract_1099div": extract_1099div_node,
    "extract_k1": extract_k1_node,
    "extract_bank_statement": extract_bank_statement_node,
    "extract_other": extract_other_node,
}


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build (and optionally compile-with-checkpointer) the tax intake
    graph.

    Pass `checkpointer=None` to get an uncompiled-but-still-runnable graph
    with LangGraph's default in-memory checkpointing (handy for unit tests
    that don't need durability/interrupts across processes). Pass a real
    `AsyncPostgresSaver` in the FastAPI app for durable, resumable runs.
    """
    builder = StateGraph(TaxIntakeState)

    builder.add_node("ingest", ingest_node)
    builder.add_node("classify", classify_node)
    for name, fn in _EXTRACTION_NODES.items():
        builder.add_node(name, fn)
    builder.add_node("cross_check", cross_check_node)
    builder.add_node("review", review_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {name: name for name in _EXTRACTION_NODES},
    )
    for name in _EXTRACTION_NODES:
        builder.add_edge(name, "cross_check")
    builder.add_edge("cross_check", "review")
    builder.add_edge("review", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
