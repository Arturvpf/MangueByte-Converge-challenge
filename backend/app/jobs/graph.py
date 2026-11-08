"""A stateless LangGraph for one synthetic transition; SQL owns durability."""
from typing import Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph


class MockState(TypedDict):
    state: str
    limit_reached: bool
    target: str
    question_id: str | None
    reason: str | None


def route(state: MockState) -> Literal["limit", "validate", "investigate", "ask", "block", "invalid"]:
    if state["limit_reached"]:
        return "limit"
    return {"CREATED": "validate", "VALIDATING": "investigate",
            "INVESTIGATING": "ask", "PLANNING": "block"}.get(state["state"], "invalid")


def limit(state: MockState) -> dict:
    return {"target": "FAILED", "question_id": None, "reason": "LIMIT_REACHED"}


def validate(state: MockState) -> dict:
    return {"target": "VALIDATING", "question_id": None, "reason": None}


def investigate(state: MockState) -> dict:
    return {"target": "INVESTIGATING", "question_id": None, "reason": None}


def ask(state: MockState) -> dict:
    return {"target": "WAITING_INPUT", "question_id": str(uuid4()), "reason": None}


def block(state: MockState) -> dict:
    return {"target": "BLOCKED", "question_id": None, "reason": "REAL_NODES_UNAVAILABLE"}


def invalid(state: MockState) -> dict:
    return {"target": "", "question_id": None, "reason": "INVALID_STATE"}


def build_graph():
    graph = StateGraph(MockState)
    nodes = {"limit": limit, "validate": validate, "investigate": investigate,
             "ask": ask, "block": block, "invalid": invalid}
    for name, node in nodes.items():
        graph.add_node(name, node)
        graph.add_edge(name, END)
    graph.add_conditional_edges(START, route, {name: name for name in nodes})
    # No checkpointer: a fresh invocation starts from the authoritative SQL row.
    return graph.compile()


MOCK_GRAPH = build_graph()
