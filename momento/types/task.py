from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Action:
    name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None  # populated at runtime after tool invocation


@dataclass
class DAGNode:
    id: str
    tool: str
    evaluation_type: str  # "results" | "arguments"
    arguments: Dict[str, Any] = field(default_factory=dict)
    expected_result: Optional[Any] = None
    predecessors: List[str] = field(default_factory=list)
    is_subset: bool = (
        False  # whether the expected result is a subset or superset of the actual result
    )


@dataclass
class TaskImage:
    id: int
    path: str
    description: str = ""


@dataclass
class ExpectedInformation:
    description: str
    reference_answer: str = ""


@dataclass
class SessionMessage:
    seq: int
    role: str  # "user" | "assistant" | "tool"
    content: Any  # str for user/assistant, dict for tool


@dataclass
class SessionSeed:
    id: str
    user_id: str
    started_at: str
    ended_at: str
    summary: str
    extracted_facts: Dict[str, Any] = field(default_factory=dict)
    messages: List[SessionMessage] = field(default_factory=list)


@dataclass
class ScenarioSeedData:
    orders: List[Dict[str, Any]] = field(default_factory=list)
    order_items: List[Dict[str, Any]] = field(default_factory=list)
    reservations: List[Dict[str, Any]] = field(default_factory=list)
    memberships: List[Dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.orders or self.order_items or self.reservations or self.memberships)


@dataclass
class Task:
    task_id: int
    user_id: str
    instruction: str
    orders_hashed: str
    reservations_hashed: str
    order_items_hashed: str
    memberships_hashed: str
    current_date: Optional[str] = None
    action_dags: List[List[DAGNode]] = field(default_factory=list)
    expected_information: List[ExpectedInformation] = field(default_factory=list)
    images: List[TaskImage] = field(default_factory=list)
    sessions: List[SessionSeed] = field(default_factory=list)
    seed_data: ScenarioSeedData = field(default_factory=ScenarioSeedData)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "instruction": self.instruction,
            "orders_hashed": self.orders_hashed,
            "reservations_hashed": self.reservations_hashed,
            "order_items_hashed": self.order_items_hashed,
            "memberships_hashed": self.memberships_hashed,
            "current_date": self.current_date,
            "action_dags": [
                [
                    {
                        "id": node.id,
                        "tool": node.tool,
                        "evaluation_type": node.evaluation_type,
                        "arguments": node.arguments,
                        "expected_result": node.expected_result,
                        "predecessors": node.predecessors,
                    }
                    for node in dag
                ]
                for dag in self.action_dags
            ],
            "expected_information": [
                {"description": ei.description, "reference_answer": ei.reference_answer}
                for ei in self.expected_information
            ],
            "images": [
                {"path": img.path, "description": img.description}
                for img in self.images
            ],
            "sessions": [
                {
                    "id": s.id,
                    "user_id": s.user_id,
                    "started_at": s.started_at,
                    "ended_at": s.ended_at,
                    "summary": s.summary,
                    "extracted_facts": s.extracted_facts,
                    "messages": [
                        {"seq": m.seq, "role": m.role, "content": m.content}
                        for m in s.messages
                    ],
                }
                for s in self.sessions
            ],
            "seed_data": {
                "orders": self.seed_data.orders,
                "order_items": self.seed_data.order_items,
                "reservations": self.seed_data.reservations,
                "memberships": self.seed_data.memberships,
            },
        }
