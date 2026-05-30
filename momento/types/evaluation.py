from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from momento.types.task import Action
import math


@dataclass
class TrajectoryResult:
    messages: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": self.messages,
            "actions": [
                {"name": a.name, "arguments": a.arguments, "result": a.result}
                for a in self.actions
            ],
        }


@dataclass
class DBStateResult:
    orders_match: bool = False
    reservations_match: bool = False
    order_items_match: bool = False
    memberships_match: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.orders_match
            and self.reservations_match
            and self.order_items_match
            and self.memberships_match
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orders_match": self.orders_match,
            "reservations_match": self.reservations_match,
            "order_items_match": self.order_items_match,
            "memberships_match": self.memberships_match,
            "passed": self.passed,
        }


@dataclass
class InformationCoverageResult:
    total_items: int = 0
    covered_items: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return 1.0 - 1e-6 <= self.coverage_score <= 1.0 + 1e-6

    @property
    def coverage_score(self) -> float:
        if self.total_items == 0:
            return 1.0
        return self.covered_items / self.total_items

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_items": self.total_items,
            "covered_items": self.covered_items,
            "coverage_score": round(self.coverage_score, 4),
            "passed": self.passed,
            "details": self.details,
        }


@dataclass
class ToolRecallResult:
    total_nodes: int = 0
    correct_nodes: int = 0
    node_details: List[Dict[str, Any]] = field(default_factory=list)
    actual_actions: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return 1.0 - 1e-6 <= self.recall <= 1.0 + 1e-6

    @property
    def recall(self) -> float:
        if self.total_nodes == 0:
            return 1.0
        return self.correct_nodes / self.total_nodes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "correct_nodes": self.correct_nodes,
            "recall": round(self.recall, 4),
            "node_details": self.node_details,
            "actual_actions": self.actual_actions,
        }


@dataclass
class TaskTrialResult:
    task_id: int
    user_id: str
    trial_id: int
    trajectory_result: TrajectoryResult = field(default_factory=TrajectoryResult)
    db_state_result: DBStateResult = field(default_factory=DBStateResult)
    information_coverage_result: InformationCoverageResult = field(
        default_factory=InformationCoverageResult
    )
    tool_recall_result: ToolRecallResult = field(default_factory=ToolRecallResult)
    token_usage: Dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return (
            self.db_state_result.passed
            and self.information_coverage_result.passed
            and self.tool_recall_result.passed
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "trial_id": self.trial_id,
            "trajectory_result": self.trajectory_result.to_dict(),
            "db_state_result": self.db_state_result.to_dict(),
            "information_coverage_result": self.information_coverage_result.to_dict(),
            "tool_recall_result": self.tool_recall_result.to_dict(),
            "passed": self.passed,
            "token_usage": self.token_usage,
        }


class TaskEvaluationSummary:
    def __init__(self, task_id: int):
        self.task_id = task_id
        self.trials: List[TaskTrialResult] = []

    @property
    def tool_recall(self) -> float:
        if not self.trials:
            return 0.0
        return sum(t.tool_recall_result.recall for t in self.trials) / len(self.trials)

    @property
    def db_state_match(self) -> float:
        if not self.trials:
            return 0.0
        passed = sum(1.0 for t in self.trials if t.db_state_result.passed)
        return passed / len(self.trials)

    @property
    def information_coverage(self) -> float:
        if not self.trials:
            return 0.0
        return sum(
            t.information_coverage_result.coverage_score for t in self.trials
        ) / len(self.trials)

    def pass_at_k(self, k: int) -> float:
        n = len(self.trials)
        if n == 0 or k <= 0 or k > n:
            return 0.0

        c = sum(1 for trial in self.trials if trial.passed)
        failures = n - c
        if k > failures:
            return 1.0
        prob_all_failures = math.comb(failures, k) / math.comb(n, k)
        return 1.0 - prob_all_failures

    def pass_hat_k(self, k: int) -> float:
        n = len(self.trials)
        if n == 0 or k <= 0 or k > n:
            return 0.0
        c = sum(1 for trial in self.trials if trial.passed)
        if k > c:
            return 0.0
        return math.comb(c, k) / math.comb(n, k)

    def add_trial_result(self, trial_result: TaskTrialResult):
        assert (
            trial_result.task_id == self.task_id
        ), "Mismatched task ID in trial result"
        self.trials.append(trial_result)

    @property
    def total_tokens(self) -> Dict[str, int]:
        token_sums: Dict[str, int] = {}
        for trial in self.trials:
            for key, count in trial.token_usage.items():
                token_sums[key] = token_sums.get(key, 0) + count
        return token_sums

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trials": [trial.to_dict() for trial in self.trials],
            "db_state_match": self.db_state_match,
            "information_coverage": self.information_coverage,
            "tool_recall": self.tool_recall,
            "pass_at_k": {k: self.pass_at_k(k) for k in range(1, len(self.trials) + 1)},
            "pass_hat_k": {
                k: self.pass_hat_k(k) for k in range(1, len(self.trials) + 1)
            },
        }


class BenchmarkResult:
    task_results: List[TaskEvaluationSummary] = field(default_factory=list)

    @property
    def total_tasks(self) -> int:
        return len(self.task_results)

    @property
    def average_tool_recall(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        total_recall = sum(ts.tool_recall for ts in self.task_results)
        return total_recall / self.total_tasks

    @property
    def average_db_state_match(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        total = sum(ts.db_state_match for ts in self.task_results)
        return total / self.total_tasks

    @property
    def average_information_coverage(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        total = sum(ts.information_coverage for ts in self.task_results)
        return total / self.total_tasks

    @property
    def average_pass_at_k(self) -> Dict[int, float]:
        if self.total_tasks == 0:
            return {}
        max_k = max(len(ts.trials) for ts in self.task_results)
        avg_pass_at_k = {}
        for k in range(1, max_k + 1):
            avg_pass_at_k[k] = (
                sum(ts.pass_at_k(k) for ts in self.task_results) / self.total_tasks
            )
        return avg_pass_at_k

    @property
    def average_pass_hat_k(self) -> Dict[int, float]:
        if self.total_tasks == 0:
            return {}
        max_k = max(len(ts.trials) for ts in self.task_results)
        avg_pass_hat_k = {}
        for k in range(1, max_k + 1):
            avg_pass_hat_k[k] = (
                sum(ts.pass_hat_k(k) for ts in self.task_results) / self.total_tasks
            )
        return avg_pass_hat_k

    @property
    def total_tokens(self) -> Dict[str, int]:
        token_sums: Dict[str, int] = {}
        for task_result in self.task_results:
            for key, count in task_result.total_tokens.items():
                token_sums[key] = token_sums.get(key, 0) + count
        return token_sums

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "metrics": {
                "average_db_state_match": self.average_db_state_match,
                "average_information_coverage": self.average_information_coverage,
                "average_tool_recall": self.average_tool_recall,
                "average_pass_at_k": self.average_pass_at_k,
                "average_pass_hat_k": self.average_pass_hat_k,
                "total_tokens": self.total_tokens,
            },
        }
