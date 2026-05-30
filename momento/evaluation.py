from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from momento.envs.environment import RestaurantEnvironment, load_scenarios
from momento.eval.evaluator import Evaluator
from momento.types import Action, DBConfig, EnvironmentConfig, Task
from momento.types.evaluation import (
    BenchmarkResult,
    DBStateResult,
    InformationCoverageResult,
    TaskEvaluationSummary,
    TaskTrialResult,
    ToolRecallResult,
    TrajectoryResult,
)
from momento.utils.logger import get_logger

logger = get_logger(__name__)


def _trajectory_from_dict(data: Dict[str, Any]) -> TrajectoryResult:
    actions = [
        Action(
            name=a.get("name", ""),
            arguments=a.get("arguments") or {},
            result=a.get("result"),
        )
        for a in (data.get("actions") or [])
    ]
    return TrajectoryResult(
        messages=list(data.get("messages") or []),
        actions=actions,
    )


def _db_state_from_dict(data: Dict[str, Any]) -> DBStateResult:
    return DBStateResult(
        orders_match=bool(data.get("orders_match", False)),
        reservations_match=bool(data.get("reservations_match", False)),
        order_items_match=bool(data.get("order_items_match", False)),
        memberships_match=bool(data.get("memberships_match", False)),
    )


def _info_coverage_from_dict(data: Dict[str, Any]) -> InformationCoverageResult:
    return InformationCoverageResult(
        total_items=int(data.get("total_items", 0)),
        covered_items=int(data.get("covered_items", 0)),
        details=list(data.get("details") or []),
    )


def _replay_actions(env: RestaurantEnvironment, actions: List[Action]) -> None:
    for action in actions:
        try:
            env.tool_registry.invoke(action.name, action.arguments or {})
        except Exception as exc:
            logger.warning("Replay of action '%s' failed: %s", action.name, exc)


@contextlib.contextmanager
def _env_context(
    use_db: bool, env_config: Optional[EnvironmentConfig]
) -> Iterator[Optional[RestaurantEnvironment]]:
    if use_db:
        with RestaurantEnvironment(env_config) as env:
            yield env
    else:
        yield None


def _reevaluate_trial(
    evaluator: Evaluator,
    task: Task,
    trial_data: Dict[str, Any],
    rerun_info_coverage: bool,
    env: Optional[RestaurantEnvironment] = None,
) -> TaskTrialResult:
    trajectory = _trajectory_from_dict(trial_data.get("trajectory_result") or {})

    result = TaskTrialResult(
        task_id=task.task_id,
        user_id=trial_data.get("user_id") or task.user_id,
        trial_id=int(trial_data.get("trial_id", 0)),
        trajectory_result=trajectory,
        token_usage=trial_data.get("token_usage") or {},
    )

    # 1. DB state.
    if env is not None:
        env.reset()
        _replay_actions(env, trajectory.actions)
        result.db_state_result = Evaluator._evaluate_db_state(task)
    else:
        result.db_state_result = _db_state_from_dict(
            trial_data.get("db_state_result") or {}
        )

    # 2. Tool recall: re-score against the (possibly updated) action DAGs.
    if task.action_dags:
        result.tool_recall_result = Evaluator._evaluate_tool_recall(task, trajectory)
    else:
        result.tool_recall_result = ToolRecallResult(
            actual_actions=[a.name for a in trajectory.actions]
        )

    # 3. Information coverage: optionally re-run the LLM judge.
    if rerun_info_coverage and task.expected_information:
        result.information_coverage_result = evaluator._evaluate_information_coverage(
            task, trajectory
        )
    else:
        result.information_coverage_result = _info_coverage_from_dict(
            trial_data.get("information_coverage_result") or {}
        )

    return result


def reevaluate(
    results_folder: Path,
    scenarios_dir: Path,
    output_dir: Path,
    judge_model: str = "openai/gpt-4o-mini",
    judge_base_url: Optional[str] = None,
    rerun_info_coverage: bool = True,
    use_db: bool = False,
    env_config: Optional[EnvironmentConfig] = None,
) -> BenchmarkResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = load_scenarios("adrilmanurung/momento")
    tasks_by_id = {t.task_id: t for t in tasks}

    evaluator = Evaluator(
        judge_model=judge_model,
        judge_base_url=judge_base_url,
        judge_temperature=0.0,
    )

    summaries: List[TaskEvaluationSummary] = []
    task_files = sorted(results_folder.glob("task_*.json"))
    if not task_files:
        logger.warning("No task_*.json files found in %s", results_folder)

    with _env_context(use_db, env_config) as env:
        for path in task_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read %s: %s", path, exc)
                continue

            task_id = data.get("task_id")
            if task_id is None:
                logger.warning("No task_id in %s, skipping.", path)
                continue

            task = tasks_by_id.get(int(task_id))
            if task is None:
                logger.warning(
                    "No scenario found for task_id=%s in %s, skipping.",
                    task_id,
                    scenarios_dir,
                )
                continue

            if env is not None:
                env.set_scenario(task)

            summary = TaskEvaluationSummary(task_id=task.task_id)
            for trial_data in data.get("trials") or []:
                new_trial = _reevaluate_trial(
                    evaluator=evaluator,
                    task=task,
                    trial_data=trial_data,
                    rerun_info_coverage=rerun_info_coverage,
                    env=env,
                )
                summary.add_trial_result(new_trial)

            out_path = output_dir / f"task_{task.task_id}.json"
            out_path.write_text(
                json.dumps(
                    summary.to_dict(),
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )
            logger.info("Re-evaluated task %d -> %s", task.task_id, out_path)
            summaries.append(summary)

    benchmark = BenchmarkResult()
    benchmark.task_results = summaries

    bench_path = output_dir / "benchmark.json"
    bench_path.write_text(
        json.dumps(
            benchmark.to_dict(),
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    logger.info("Saved benchmark result -> %s", bench_path)
    return benchmark


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Re-evaluate saved trial trajectories against the current scenario "
            "definitions. Useful after editing action_dags or expected_information "
            "in scenario_*.json. DB state is carried over from the original run."
        )
    )
    parser.add_argument(
        "folder",
        type=str,
        help="Run folder containing task_*.json files to re-evaluate.",
    )
    parser.add_argument(
        "--scenarios-dir",
        type=str,
        default="momento/envs/scenarios",
        help="Directory containing scenario_*.json (default: momento/envs/scenarios).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory. Defaults to <folder>/reevaluated.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="openai/gpt-4o-mini",
        help="LLM judge model for information coverage.",
    )
    parser.add_argument(
        "--judge-base-url",
        type=str,
        default=None,
        help="LLM judge API base URL.",
    )
    parser.add_argument(
        "--skip-info-coverage",
        action="store_true",
        help="Skip re-running the LLM judge; reuse the saved information coverage.",
    )
    parser.add_argument(
        "--use-db",
        action="store_true",
        help=(
            "Spin up the live environment, replay each trial's actions against "
            "a freshly-reset DB, and recompute DB state hashes. Requires Docker."
        ),
    )
    args = parser.parse_args(argv)

    results_folder = Path(args.folder)
    if not results_folder.is_dir():
        raise SystemExit(f"Folder not found: {results_folder}")

    scenarios_dir = Path(args.scenarios_dir)
    if not scenarios_dir.is_dir():
        raise SystemExit(f"Scenarios directory not found: {scenarios_dir}")

    output_dir = (
        Path(args.output_dir) if args.output_dir else results_folder / "reevaluated"
    )

    benchmark = reevaluate(
        results_folder=results_folder,
        scenarios_dir=scenarios_dir,
        output_dir=output_dir,
        judge_model=args.judge_model,
        judge_base_url=args.judge_base_url,
        rerun_info_coverage=not args.skip_info_coverage,
        use_db=args.use_db,
        env_config=EnvironmentConfig(db=DBConfig.from_env()),
    )

    m = benchmark.to_dict()["metrics"]
    print(f"Re-evaluated {benchmark.total_tasks} task(s) -> {output_dir}")
    print(f"  average_db_state_match:       {m['average_db_state_match']:.4f}")
    print(f"  average_information_coverage: {m['average_information_coverage']:.4f}")
    print(f"  average_tool_recall:          {m['average_tool_recall']:.4f}")
    if m["average_pass_at_k"]:
        pak = {k: round(v, 4) for k, v in m["average_pass_at_k"].items()}
        print(f"  average_pass_at_k:            {pak}")
    if m["average_pass_hat_k"]:
        phk = {k: round(v, 4) for k, v in m["average_pass_hat_k"].items()}
        print(f"  average_pass_hat_k:           {phk}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
