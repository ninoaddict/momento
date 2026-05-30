from __future__ import annotations

import argparse
import base64
import json
import mimetypes
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from momento.agent.agent import Agent
from momento.envs.environment import RestaurantEnvironment
from momento.eval.evaluator import Evaluator
from momento.types import (
    BenchmarkResult,
    DBConfig,
    EnvironmentConfig,
    GenerationConfig,
    Task,
    TaskEvaluationSummary,
    TrajectoryResult,
)
from momento.user.simulated_user import SimulatedUser
from momento.utils.logger import get_logger
from urllib.parse import urlparse, unquote

logger = get_logger(__name__)


_IMAGES_DIR = Path(__file__).resolve().parent / "images"


def _image_path_to_url(image_path: str) -> str:
    if image_path.startswith("data:"):
        return image_path

    if image_path.startswith(("http://", "https://")):
        url_path = unquote(urlparse(image_path).path)
        filename = Path(url_path).name
        local = _IMAGES_DIR / filename
        if local.is_file():
            p = local
        else:
            logger.warning(
                "No local image found for %s (looked for %s), skipping.",
                image_path,
                local,
            )
            raise FileNotFoundError(f"Local image not found: {local}")
    else:
        p = Path(image_path)
        if not p.is_absolute():
            p = _IMAGES_DIR / p
        if not p.is_file():
            raise FileNotFoundError(f"Image file not found: {p}")

    mime, _ = mimetypes.guess_type(str(p))
    if mime is None:
        mime = "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _resolve_images(task: Task, image_ids: List[int]) -> List[str]:
    """Return a list of base64 data URLs for the requested images."""
    by_id = {img.id: img for img in task.images}
    urls: List[str] = []
    for img_id in image_ids:
        img = by_id.get(img_id)
        if img is None:
            logger.warning("Task %d: image id %d not found", task.task_id, img_id)
            continue
        try:
            urls.append(_image_path_to_url(img.path))
        except FileNotFoundError:
            logger.warning(
                "Task %d: image file not found at %s", task.task_id, img.path
            )
    return urls


# Trial execution
def _run_trial(
    task: Task,
    env: RestaurantEnvironment,
    config: GenerationConfig,
) -> Tuple[TrajectoryResult, Dict[str, int]]:
    """Run a single trial of a task and return its trajectory and token usage."""
    env.reset()

    current_date = task.current_date or date.today().isoformat()

    agent = Agent(
        config=config,
        tool_registry=env.tool_registry,
        user_id=task.user_id,
        current_date=current_date,
    )
    user = SimulatedUser(
        task=task,
        model=config.user_model,
        base_url=config.user_base_url,
        temperature=config.user_temperature,
        max_tokens=config.user_max_tokens,
        top_p=config.user_top_p,
        top_k=config.user_top_k,
        reasoning_effort=config.user_reasoning_effort,
        current_date=current_date,
    )

    global_messages = []

    def _build_result() -> Tuple[TrajectoryResult, Dict[str, int]]:
        trajectory = TrajectoryResult(
            messages=list(global_messages),
            actions=list(agent.actions),
        )
        token_usage = {
            "prompt_tokens": agent.token_usage.get("prompt_tokens", 0)
            + user.token_usage.get("prompt_tokens", 0),
            "completion_tokens": agent.token_usage.get("completion_tokens", 0)
            + user.token_usage.get("completion_tokens", 0),
            "total_tokens": agent.token_usage.get("total_tokens", 0)
            + user.token_usage.get("total_tokens", 0),
        }
        return trajectory, token_usage

    try:
        user_msg = user.get_initial_message()
        logger.debug(
            "Task %d: initial user message:\n%s", task.task_id, user_msg
        )
        global_messages.append({"role": "user", "content": user_msg})
    except Exception as exc:
        logger.exception(
            "Failed to obtain initial user message for task %d: %s",
            task.task_id,
            exc,
        )
        return _build_result()

    for turn in range(config.max_turns):
        if user.is_done(user_msg):
            logger.debug(
                "Task %d: user signaled completion at turn %d.", task.task_id, turn
            )
            break

        clean_msg, image_ids = user.parse_image_tags(user_msg)
        images = _resolve_images(task, image_ids) if image_ids else None

        try:
            agent_reply = agent.step(clean_msg, images=images)
            logger.debug(
                "Task %d: agent reply at turn %d:\n%s", task.task_id, turn, agent_reply
            )
            global_messages.append({"role": "assistant", "content": agent_reply})
        except Exception as exc:
            logger.exception("Agent step failed on task %d: %s", task.task_id, exc)
            break

        try:
            user_msg = user.respond(agent_reply)
            logger.debug(
                "Task %d: user reply at turn %d:\n%s", task.task_id, turn, user_msg
            )
            global_messages.append({"role": "user", "content": user_msg})
        except Exception as exc:
            logger.exception(
                "Simulated user response failed on task %d: %s", task.task_id, exc
            )
            break
    else:
        logger.info(
            "Task %d: reached max_turns=%d without [DONE] signal.",
            task.task_id,
            config.max_turns,
        )

    return _build_result()


# Scenario filtering
def _filter_tasks(tasks: List[Task], config: GenerationConfig) -> List[Task]:
    if config.task_ids:
        wanted = set(config.task_ids)
        return [t for t in tasks if t.task_id in wanted]
    end = len(tasks) if config.end_index == -1 else config.end_index
    return tasks[config.start_index : end]


# Benchmark driver
def run_benchmark(
    config: GenerationConfig,
    env_config: Optional[EnvironmentConfig] = None,
) -> BenchmarkResult:
    """Run the full benchmark across all selected scenarios and save results."""
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    evaluator = Evaluator(
        judge_model=config.judge_model,
        judge_base_url=config.judge_base_url,
        judge_temperature=config.judge_temperature,
        judge_max_tokens=config.judge_max_tokens,
        judge_top_p=config.judge_top_p,
        judge_top_k=config.judge_top_k,
        judge_reasoning_effort=config.judge_reasoning_effort,
    )

    summaries: List[TaskEvaluationSummary] = []

    with RestaurantEnvironment(env_config) as env:
        all_tasks = env.load_scenarios()
        tasks = _filter_tasks(all_tasks, config)
        logger.info(
            "Running benchmark on %d/%d task(s) with %d trial(s) each.",
            len(tasks),
            len(all_tasks),
            config.n_trials,
        )

        for task in tasks:
            summary = TaskEvaluationSummary(task_id=task.task_id)
            env.set_scenario(task)

            for trial_id in range(1, config.n_trials + 1):
                logger.info(
                    "Task %d (user=%s) - trial %d/%d",
                    task.task_id,
                    task.user_id,
                    trial_id,
                    config.n_trials,
                )
                trajectory, token_usage = _run_trial(task, env, config)
                trial_result = evaluator.evaluate_task(
                    task=task,
                    trial_id=trial_id,
                    trajectory=trajectory,
                    token_usage=token_usage,
                    check_db=True,
                )
                summary.add_trial_result(trial_result)

            task_path = out_dir / f"task_{task.task_id}.json"
            task_path.write_text(
                json.dumps(
                    summary.to_dict(),
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )
            logger.info("Saved task %d summary -> %s", task.task_id, task_path)
            summaries.append(summary)

        benchmark = evaluator.evaluate_benchmark(summaries)
        bench_path = out_dir / "benchmark.json"
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


# CLI
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run the Momento restaurant-assistant benchmark pipeline.",
    )
    p.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a JSON config file. CLI flags override values from the file.",
    )

    # Agent settings
    p.add_argument("--agent-model", type=str, default=argparse.SUPPRESS)
    p.add_argument("--agent-base-url", type=str, default=argparse.SUPPRESS)
    p.add_argument("--agent-temperature", type=float, default=argparse.SUPPRESS)
    p.add_argument("--agent-max-tokens", type=int, default=argparse.SUPPRESS)
    p.add_argument("--agent-top-p", type=float, default=argparse.SUPPRESS)
    p.add_argument("--agent-top-k", type=int, default=argparse.SUPPRESS)
    p.add_argument("--agent-reasoning-effort", type=str, default=argparse.SUPPRESS)

    # Simulated user settings
    p.add_argument("--user-model", type=str, default=argparse.SUPPRESS)
    p.add_argument("--user-base-url", type=str, default=argparse.SUPPRESS)
    p.add_argument("--user-temperature", type=float, default=argparse.SUPPRESS)
    p.add_argument("--user-max-tokens", type=int, default=argparse.SUPPRESS)
    p.add_argument("--user-top-p", type=float, default=argparse.SUPPRESS)
    p.add_argument("--user-top-k", type=int, default=argparse.SUPPRESS)
    p.add_argument("--user-reasoning-effort", type=str, default=argparse.SUPPRESS)

    # Simulation limits
    p.add_argument("--max-turns", type=int, default=argparse.SUPPRESS)
    p.add_argument("--max-tool-rounds", type=int, default=argparse.SUPPRESS)

    # Memory management
    p.add_argument("--max-context-tokens", type=int, default=argparse.SUPPRESS)

    # Scenario selection
    p.add_argument("--start-index", type=int, default=argparse.SUPPRESS)
    p.add_argument("--end-index", type=int, default=argparse.SUPPRESS)
    p.add_argument(
        "--task-ids",
        type=int,
        nargs="+",
        default=argparse.SUPPRESS,
        help="Specific task IDs to run (overrides --start-index/--end-index).",
    )

    # Benchmark settings
    p.add_argument("--judge-model", type=str, default=argparse.SUPPRESS)
    p.add_argument("--judge-base-url", type=str, default=argparse.SUPPRESS)
    p.add_argument("--judge-temperature", type=float, default=argparse.SUPPRESS)
    p.add_argument("--judge-max-tokens", type=int, default=argparse.SUPPRESS)
    p.add_argument("--judge-top-p", type=float, default=argparse.SUPPRESS)
    p.add_argument("--judge-top-k", type=int, default=argparse.SUPPRESS)
    p.add_argument("--judge-reasoning-effort", type=str, default=argparse.SUPPRESS)
    p.add_argument("--n-trials", type=int, default=argparse.SUPPRESS)

    # Paths
    p.add_argument("--output-dir", type=str, default=argparse.SUPPRESS)
    p.add_argument("--prompt-path", type=str, default=argparse.SUPPRESS)
    p.add_argument("--policy-path", type=str, default=argparse.SUPPRESS)

    return p


def _config_from_args(args: argparse.Namespace) -> GenerationConfig:
    valid_fields = {f.name for f in fields(GenerationConfig)}
    overrides: Dict[str, Any] = {}

    # Load JSON config first (lowest precedence after dataclass defaults).
    config_path = getattr(args, "config", None)
    if config_path:
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Config file {config_path} must contain a JSON object.")
        for k, v in raw.items():
            key = k.replace("-", "_")
            if key in valid_fields:
                overrides[key] = v
            else:
                logger.debug("Ignoring unknown config key from file: %s", k)

    # CLI flags override JSON values.
    for k, v in vars(args).items():
        if k == "config":
            continue
        if k in valid_fields:
            overrides[k] = v

    return GenerationConfig(**overrides)


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = _config_from_args(args)
    run_benchmark(config, EnvironmentConfig(db=DBConfig.from_env()))


if __name__ == "__main__":
    main()
