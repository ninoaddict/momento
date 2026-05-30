from __future__ import annotations

import json
import os
from collections import deque
from typing import Any, Dict, List, Optional, Set

from momento.utils.inference import model_inference
from momento.types import DAGNode, Task
from momento.types.evaluation import (
    BenchmarkResult,
    DBStateResult,
    InformationCoverageResult,
    TaskEvaluationSummary,
    TaskTrialResult,
    ToolRecallResult,
    TrajectoryResult,
)
from momento.utils.json_parser import extract_json
from momento.types.task import Action
from momento.utils import compare_hashes, compute_all_user_hashes
from momento.utils.logger import get_logger
from momento.utils.utils import strip_thinking

logger = get_logger(__name__)


class Evaluator:
    """Benchmark evaluator that scores agent trajectories against ground truth."""
    EXCLUDED_MATCH_KEYS: Set[str] = {
        "special_requests",
        "special_instructions",
        "notes",
        "delivery_address",
        "created_at",
        "updated_at",
    }

    def __init__(
        self,
        judge_model: str = "openai/gpt-4o-mini",
        judge_base_url: Optional[str] = None,
        judge_temperature: float = 0.0,
        judge_max_tokens: int = 4096,
        judge_top_p: Optional[float] = None,
        judge_top_k: Optional[int] = None,
        judge_reasoning_effort: Optional[str] = None,
        judge_api_key: Optional[str] = None,
    ) -> None:
        self.judge_model = judge_model
        self.judge_base_url = judge_base_url or os.environ.get("AGENT_BASE_URL") or ""
        self.judge_temperature = judge_temperature
        self.judge_max_tokens = judge_max_tokens
        self.judge_top_p = judge_top_p
        self.judge_top_k = judge_top_k
        self.judge_reasoning_effort = judge_reasoning_effort
        self.judge_api_key = judge_api_key or os.getenv("JUDGE_API_KEY")

    def evaluate_task(
        self,
        task: Task,
        trial_id: int,
        trajectory: TrajectoryResult,
        token_usage: Dict[str, int],
        check_db: bool = True,
    ) -> TaskTrialResult:
        """Evaluate a single task trial and return detailed results."""
        result = TaskTrialResult(
            task_id=task.task_id,
            user_id=task.user_id,
            trial_id=trial_id,
            trajectory_result=trajectory,
            token_usage=token_usage,
        )

        # 1. DB State Match
        if check_db:
            result.db_state_result = self._evaluate_db_state(task)

        # 2. Information Coverage (LLM-as-Judge)
        if task.expected_information:
            result.information_coverage_result = self._evaluate_information_coverage(
                task, trajectory
            )

        # 3. Tool Recall (DAG-based)
        if task.action_dags:
            result.tool_recall_result = self._evaluate_tool_recall(task, trajectory)

        return result

    def evaluate_benchmark(
        self,
        summaries: List[TaskEvaluationSummary],
    ) -> BenchmarkResult:
        """Aggregate task evaluation summaries into a benchmark result."""
        benchmark = BenchmarkResult()
        benchmark.task_results = summaries
        return benchmark

    # Metric 1: DB State Match
    @staticmethod
    def _evaluate_db_state(task: Task) -> DBStateResult:
        """Compare current DB state hashes against ground-truth hashes."""
        expected = {
            "orders_hashed": task.orders_hashed,
            "reservations_hashed": task.reservations_hashed,
            "order_items_hashed": task.order_items_hashed,
            "memberships_hashed": task.memberships_hashed,
        }
        actual = compute_all_user_hashes(task.user_id)
        matches = compare_hashes(expected, actual)

        return DBStateResult(
            orders_match=matches["orders_hashed"],
            reservations_match=matches["reservations_hashed"],
            order_items_match=matches["order_items_hashed"],
            memberships_match=matches["memberships_hashed"],
        )

    # Metric 2: Information Coverage (LLM-as-Judge)
    def _evaluate_information_coverage(
        self,
        task: Task,
        trajectory: TrajectoryResult,
    ) -> InformationCoverageResult:
        """Use an LLM to judge whether the agent conveyed the expected information.

        The judge receives:
        - The user instruction (so it understands what was asked).
        - The full conversation between user and agent.
        - A list of expected information items, each with a natural-language
          description and an optional reference answer.

        The judge evaluates whether the agent's responses adequately convey
        each expected piece of information, considering semantic equivalence
        rather than exact string matching.
        """
        assistant_messages = "\n".join(
            msg.get("content", "")
            for msg in trajectory.messages
            if msg.get("role") == "assistant" and msg.get("content")
        )

        if not assistant_messages.strip():
            return InformationCoverageResult(
                total_items=len(task.expected_information),
                covered_items=0,
                details=[
                    {
                        "index": i,
                        "description": ei.description,
                        "covered": False,
                        "reason": "No assistant messages",
                    }
                    for i, ei in enumerate(task.expected_information)
                ],
            )

        conversation_text = "\n".join(
            f"[{msg.get('role', 'unknown').upper()}]: {msg.get('content', '')}"
            for msg in trajectory.messages
            if msg.get("content")
        )

        info_items = [
            {
                "index": i,
                "description": ei.description,
                "reference_answer": ei.reference_answer,
            }
            for i, ei in enumerate(task.expected_information)
        ]
        info_items_json = json.dumps(info_items, ensure_ascii=False, indent=2)

        prompt = (
            "You are an evaluation judge. Your task is to determine whether an AI "
            "assistant adequately conveyed specific pieces of information in its "
            "responses during a conversation.\n\n"
            "## User's Instruction (Context)\n"
            f"{task.instruction}\n\n"
            "## Conversation\n"
            f"{conversation_text}\n\n"
            "## Expected Information\n"
            f"{info_items_json}\n\n"
            "For each item, determine whether the assistant's responses convey the "
            "described information. The `reference_answer` is provided as guidance, "
            "the assistant does not need to use the exact same wording, but the "
            "information must be semantically equivalent (e.g., '09:00' matches "
            "'9:00 AM', '$15.50' matches '15.50 dollars').\n\n"
            "Output ONLY a JSON object with this exact structure:\n"
            "```json\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "index": 0,\n'
            '      "description": "...",\n'
            '      "covered": true,\n'
            '      "reason": "brief explanation of why the information was or was not conveyed"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```"
        )

        try:
            response, _ = model_inference(
                model=self.judge_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise evaluation judge.",
                    },
                    {"role": "user", "content": prompt},
                ],
                base_url=self.judge_base_url,
                temperature=self.judge_temperature,
                max_tokens=self.judge_max_tokens,
                top_p=self.judge_top_p,
                top_k=self.judge_top_k,
                reasoning_effort=self.judge_reasoning_effort,  # type: ignore
                api_key=self.judge_api_key,
            )

            raw = strip_thinking(response.content or "")
            parsed = self._parse_judge_response(raw, len(task.expected_information))

            covered_count = sum(1 for d in parsed if d.get("covered", False))
            return InformationCoverageResult(
                total_items=len(task.expected_information),
                covered_items=covered_count,
                details=parsed,
            )
        except Exception as exc:
            logger.error("LLM judge call failed: %s", exc)
            return self._fallback_information_check(task, assistant_messages)

    @staticmethod
    def _parse_judge_response(raw: str, expected_count: int) -> List[Dict[str, Any]]:
        """Parse the LLM judge response JSON."""

        parsed = extract_json(raw)
        if parsed and "results" in parsed:
            results = parsed["results"]
            if isinstance(results, list):
                return results

        logger.warning("Could not parse judge response, returning empty results.")
        logger.warning("Raw response was: %s", raw)
        return [
            {"index": i, "covered": False, "reason": "Parse failure"}
            for i in range(expected_count)
        ]

    @staticmethod
    def _fallback_information_check(
        task: Task, assistant_text: str
    ) -> InformationCoverageResult:
        """String-match fallback using reference answers when LLM judge fails."""
        text_lower = assistant_text.lower()
        details: List[Dict[str, Any]] = []
        covered = 0

        for i, ei in enumerate(task.expected_information):
            matched = False
            if ei.reference_answer:
                matched = ei.reference_answer.lower() in text_lower
            if matched:
                covered += 1
            details.append(
                {
                    "index": i,
                    "description": ei.description,
                    "reference_answer": ei.reference_answer,
                    "covered": matched,
                    "reason": "fallback string match on reference_answer",
                }
            )

        return InformationCoverageResult(
            total_items=len(task.expected_information),
            covered_items=covered,
            details=details,
        )

    # Metric 3: Tool Recall (DAG-based)
    @staticmethod
    def _evaluate_tool_recall(
        task: Task, trajectory: TrajectoryResult
    ) -> ToolRecallResult:
        """Score tool recall against the best-matching action DAG.

        For each alternative DAG, computes the fraction of nodes correctly
        executed (respecting AND dependencies and result/argument matching),
        then returns the result for the highest-scoring DAG.
        """
        actual_actions = trajectory.actions
        actual_names = [a.name for a in actual_actions]

        best: Optional[ToolRecallResult] = None
        best_score = -1.0

        for dag in task.action_dags:
            result = Evaluator._score_dag(dag, actual_actions)
            if result.recall > best_score:
                best_score = result.recall
                best = result

        return best or ToolRecallResult(actual_actions=actual_names)

    @staticmethod
    def _score_dag(
        dag: List[DAGNode], actual_actions: List[Action]
    ) -> ToolRecallResult:
        """Score a single DAG against the agent's actual actions."""
        order = Evaluator._topological_sort(dag)
        correctly_executed: Set[str] = set()
        used_indices: Set[int] = set()
        node_details: List[Dict[str, Any]] = []

        for node in order:
            preds_ok = all(p in correctly_executed for p in node.predecessors)
            if not preds_ok:
                node_details.append(
                    {
                        "id": node.id,
                        "tool": node.tool,
                        "correct": False,
                        "reason": "predecessor not satisfied",
                    }
                )
                continue

            matched = False
            for i, action in enumerate(actual_actions):
                if i in used_indices or action.name != node.tool:
                    continue
                if Evaluator._action_matches_node(action, node):
                    correctly_executed.add(node.id)
                    used_indices.add(i)
                    node_details.append(
                        {
                            "id": node.id,
                            "tool": node.tool,
                            "correct": True,
                            "reason": "matched",
                        }
                    )
                    matched = True
                    break

            if not matched:
                node_details.append(
                    {
                        "id": node.id,
                        "tool": node.tool,
                        "correct": False,
                        "reason": "no matching action found",
                    }
                )

        return ToolRecallResult(
            total_nodes=len(dag),
            correct_nodes=len(correctly_executed),
            node_details=node_details,
            actual_actions=[a.name for a in actual_actions],
        )

    @staticmethod
    def _action_matches_node(action: Action, node: DAGNode) -> bool:
        if node.evaluation_type == "arguments":
            return Evaluator._args_match(node.arguments, action.arguments)
        # query node: prefer result-based check, fall back to argument match
        if action.result is not None and node.expected_result is not None:
            return Evaluator._result_matches(
                expected=node.expected_result,
                actual_str=action.result,
                expected_is_subset=node.is_subset,
            )
        if node.arguments:
            return Evaluator._args_match(node.arguments, action.arguments)
        return True

    @staticmethod
    def _args_match(expected: Dict[str, Any], actual: Dict[str, Any]) -> bool:
        expected = Evaluator._strip_excluded(expected, Evaluator.EXCLUDED_MATCH_KEYS)
        actual = Evaluator._strip_excluded(actual, Evaluator.EXCLUDED_MATCH_KEYS)
        for k, v in expected.items():
            actual_v = actual.get(k)
            if isinstance(v, list) and isinstance(actual_v, list):
                if not Evaluator._is_subset(v, actual_v) or not Evaluator._is_subset(
                    actual_v, v
                ):
                    return False
            else:
                if str(actual_v) != str(v):
                    return False
        return True

    @staticmethod
    def _strip_excluded(value: Any, excluded_keys: Set[str]) -> Any:
        if isinstance(value, dict):
            return {
                k: Evaluator._strip_excluded(v, excluded_keys)
                for k, v in value.items()
                if k not in excluded_keys
            }
        if isinstance(value, list):
            return [Evaluator._strip_excluded(item, excluded_keys) for item in value]
        return value

    @staticmethod
    def _result_matches(
        expected: Any,
        actual_str: str,
        expected_is_subset: bool,
    ) -> bool:
        try:
            actual = json.loads(actual_str)
        except (json.JSONDecodeError, TypeError, ValueError):
            return False
        expected = Evaluator._strip_excluded(expected, Evaluator.EXCLUDED_MATCH_KEYS)
        actual = Evaluator._strip_excluded(actual, Evaluator.EXCLUDED_MATCH_KEYS)
        if expected_is_subset:
            return Evaluator._is_subset(expected, actual)
        return Evaluator._is_subset(actual, expected)

    @staticmethod
    def _is_subset(subset: Any, superset: Any) -> bool:
        if isinstance(subset, dict) and isinstance(superset, dict):
            return all(
                k in superset and Evaluator._is_subset(v, superset[k])
                for k, v in subset.items()
            )
        if isinstance(subset, list) and isinstance(superset, list):
            return all(Evaluator._item_in_list(item, superset) for item in subset)
        return subset == superset

    @staticmethod
    def _item_in_list(item: Any, lst: List[Any]) -> bool:
        return any(Evaluator._is_subset(item, candidate) for candidate in lst)

    @staticmethod
    def _topological_sort(dag: List[DAGNode]) -> List[DAGNode]:
        in_degree: Dict[str, int] = {n.id: len(n.predecessors) for n in dag}
        queue: deque[DAGNode] = deque(n for n in dag if not n.predecessors)
        result: List[DAGNode] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for other in dag:
                if node.id in other.predecessors:
                    in_degree[other.id] -= 1
                    if in_degree[other.id] == 0:
                        queue.append(other)

        return result
