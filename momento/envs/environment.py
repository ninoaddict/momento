from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from datasets import load_dataset

import psycopg2

from momento.envs.data.seed_db import (
    apply_scenario_seed_data,
    apply_sql_directory,
    reset_database,
    seed_database,
    seed_sessions,
)
from momento.envs.repository.base import set_scenario_date
from momento.envs.tools import ALL_TOOLS
from momento.types import (
    DAGNode,
    EnvironmentConfig,
    ExpectedInformation,
    ScenarioSeedData,
    SessionMessage,
    SessionSeed,
    Task,
    TaskImage,
)
from momento.utils.logger import get_logger
from momento.envs.tools.base import PolicyViolationError

logger = get_logger(__name__)


class ToolRegistry:
    def __init__(self, tool_classes: Optional[List[Any]] = None):
        classes = tool_classes if tool_classes is not None else ALL_TOOLS
        self.tools: Dict[str, Any] = {
            tool.get_info()["function"]["name"]: tool for tool in classes
        }

    def get_tool_info(self) -> List[Dict[str, Any]]:
        return [tool.get_info() for tool in self.tools.values()]

    def invoke(self, name: str, arguments: Dict[str, Any]) -> str:
        tool = self.tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        try:
            return tool.invoke(**arguments)
        except PolicyViolationError as exc:
            return f"PolicyViolationError: {exc}"

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self.tools

    def __len__(self) -> int:
        return len(self.tools)


def _parse_sessions(raw_sessions: List[Dict[str, Any]]) -> List[SessionSeed]:
    sessions: List[SessionSeed] = []
    for s in raw_sessions:
        messages = [
            SessionMessage(
                seq=m["seq"],
                role=m["role"],
                content=m["content"],
            )
            for m in s.get("messages", [])
        ]
        sessions.append(
            SessionSeed(
                id=s["id"],
                user_id=s["user_id"],
                started_at=s["started_at"],
                ended_at=s["ended_at"],
                summary=s["summary"],
                extracted_facts=s.get("extracted_facts", {}),
                messages=messages,
            )
        )
    return sessions


def _parse_seed_data(raw: Dict[str, Any]) -> ScenarioSeedData:
    return ScenarioSeedData(
        orders=list(raw.get("orders", [])),
        order_items=list(raw.get("order_items", [])),
        reservations=list(raw.get("reservations", [])),
        memberships=list(raw.get("memberships", [])),
    )


def _coerce_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_task(data: Dict[str, Any], stem: str) -> Task:
    task_id = data.get("task_id")
    if task_id is None:
        parts = stem.rsplit("_", 1)
        task_id = int(parts[-1]) if parts[-1].isdigit() else 0

    action_dags: List[List[DAGNode]] = []
    for raw_dag in data.get("action_dags", []):
        nodes = [
            DAGNode(
                id=n["id"],
                tool=n["tool"],
                evaluation_type=n.get("evaluation_type", "arguments"),
                arguments=n.get("arguments", {}),
                is_subset=n.get("is_subset", False),
                expected_result=n.get("expected_result"),
                predecessors=n.get("predecessors", []),
            )
            for n in raw_dag
        ]
        action_dags.append(nodes)

    task_images: List[TaskImage] = []
    for idx, entry in enumerate(data.get("images", [])):
        task_images.append(
            TaskImage(
                id=entry.get("id", idx),
                path=entry["path"],
                description=entry.get("description", ""),
            )
        )

    expected_info: List[ExpectedInformation] = [
        ExpectedInformation(
            description=ei["description"],
            reference_answer=ei.get("reference_answer", ""),
        )
        for ei in data.get("expected_information", [])
    ]

    return Task(
        task_id=task_id,
        user_id=data["user_id"],
        instruction=data["instruction"],
        orders_hashed=data.get("orders_hashed", ""),
        reservations_hashed=data.get("reservations_hashed", ""),
        order_items_hashed=data.get("order_items_hashed", ""),
        memberships_hashed=data.get("memberships_hashed", ""),
        current_date=_coerce_date(data.get("current_date")),
        action_dags=action_dags,
        expected_information=expected_info,
        images=task_images,
        sessions=_parse_sessions(data.get("sessions", [])),
        seed_data=_parse_seed_data(data.get("seed_data", {})),
    )


def load_scenarios(repo_id: str) -> List[Task]:
    logger.info("Loading scenarios from Hugging Face repo '%s'", repo_id)
    dataset = load_dataset(repo_id, split="test")
    tasks = [_parse_task(dict(row), f"scenario_{row['task_id']}") for row in dataset] # type: ignore
    tasks.sort(key=lambda t: t.task_id)
    logger.info("Loaded %d scenario(s) from %s", len(tasks), repo_id)
    return tasks


class RestaurantEnvironment:
    def __init__(self, config: Optional[EnvironmentConfig] = None):
        self.config = config or EnvironmentConfig()
        self._apply_env_vars()
        self.tool_registry = ToolRegistry()
        self._ready = False
        self._current_task: Optional[Task] = None

    def _apply_env_vars(self) -> None:
        # push db connection info to env vars for repositories and db seed
        os.environ.update(self.config.db.to_env())

    def start_containers(self) -> None:
        name = self.config.docker_container_name
        logger.info("Starting Docker container '%s'", name)

        subprocess.run(
            ["docker", "rm", "-f", name],
            check=False,
            capture_output=True,
        )

        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-e",
                f"POSTGRES_USER={self.config.db.user}",
                "-e",
                f"POSTGRES_PASSWORD={self.config.db.password}",
                "-e",
                f"POSTGRES_DB={self.config.db.database}",
                "-e",
                "TZ=UTC",
                "-p",
                f"{self.config.db.port}:5432",
                self.config.docker_image,
                "postgres",
                "-c",
                "timezone=UTC",
            ],
            check=True,
            capture_output=True,
        )
        logger.info("Docker container started.")

    def stop_containers(self) -> None:
        name = self.config.docker_container_name
        logger.info("Stopping Docker container '%s'", name)
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
        logger.info("Docker container stopped.")

    def wait_for_db(self) -> None:
        dsn = self.config.db.to_dsn_kwargs()
        deadline = time.time() + self.config.docker_timeout
        last_err: Exception | None = None

        while time.time() < deadline:
            try:
                conn = psycopg2.connect(**dsn)
                conn.close()
                logger.info("Database is ready.")
                return
            except psycopg2.OperationalError as exc:
                last_err = exc
                time.sleep(1)

        raise TimeoutError(
            f"Database not ready after {self.config.docker_timeout}s "
            f"(last error: {last_err})"
        )

    def check_connection(self) -> bool:
        try:
            conn = psycopg2.connect(**self.config.db.to_dsn_kwargs())
            conn.close()
            return True
        except psycopg2.OperationalError:
            return False

    def set_scenario(self, task: Task) -> None:
        """Bind a scenario for the trial loop. Wipes and reseeds sessions (once per scenario)."""
        self._current_task = task
        seed_sessions(task.sessions)
        logger.info(
            "Scenario %d set (user=%s, sessions=%d).",
            task.task_id,
            task.user_id,
            len(task.sessions),
        )

    def reset(self) -> None:
        """Reset per-trial transactional state. Sessions are NOT touched."""
        reset_database()
        apply_sql_directory(Path(self.config.seeds_dir))
        if self._current_task is not None:
            apply_scenario_seed_data(self._current_task.seed_data)
            set_scenario_date(self._current_task.current_date)
        logger.info("Database reset to initial state.")

    def setup(self) -> None:
        self.start_containers()
        self.wait_for_db()
        seed_database(schema_path=Path(self.config.schema_path))
        self._ready = True
        logger.info("Environment setup complete.")

    def teardown(self) -> None:
        self.stop_containers()
        self._ready = False
        self._current_task = None
        logger.info("Environment teardown complete.")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def load_scenarios(self) -> List[Task]:
      return load_scenarios("adrilmanurung/momento")

    def __enter__(self) -> RestaurantEnvironment:
        self.setup()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.teardown()

    def __repr__(self) -> str:
        status = "ready" if self._ready else "not ready"
        return (
            f"RestaurantEnvironment("
            f"db={self.config.db.host}:{self.config.db.port}, "
            f"tools={len(self.tool_registry)}, "
            f"{status})"
        )
