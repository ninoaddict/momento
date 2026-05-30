import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class GenerationConfig:
    # Agent settings
    agent_model: str = "qwen/qwen3-vl-30b-a3b-thinking"
    agent_base_url: Optional[str] = None
    agent_temperature: float = 0.0
    agent_max_tokens: int = 4096
    agent_top_p: Optional[float] = None
    agent_top_k: Optional[int] = None
    agent_reasoning_effort: Optional[str] = None

    # Simulated user settings
    user_model: str = "openai/gpt-4o-mini"
    user_base_url: Optional[str] = None
    user_temperature: float = 0.0
    user_max_tokens: int = 4096
    user_top_p: Optional[float] = None
    user_top_k: Optional[int] = None
    user_reasoning_effort: Optional[str] = None

    # Simulation limits
    max_turns: int = 15
    max_tool_rounds: int = 15

    # Memory management
    max_context_tokens: int = 32768  # agent model context window size

    # Scenario selection
    start_index: int = 0
    end_index: int = -1  # -1 means all
    task_ids: Optional[List[int]] = None

    # Benchmark settings
    judge_model: str = "openai/gpt-4o-mini"
    judge_base_url: Optional[str] = None
    judge_temperature: float = 0.0
    judge_max_tokens: int = 4096
    judge_top_p: Optional[float] = None
    judge_top_k: Optional[int] = None
    judge_reasoning_effort: Optional[str] = None
    n_trials: int = 3

    # Paths
    output_dir: str = "results"
    prompt_path: str = "momento/prompts/agent.md"
    policy_path: str = "momento/prompts/policy.md"


@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = 5433
    user: str = "restaurant"
    password: str = "restaurant"
    database: str = "restaurant"

    @classmethod
    def from_env(cls) -> "DBConfig":
        return cls(
            host=os.getenv("PGHOST", "localhost"),
            port=int(os.getenv("PGPORT", "5433")),
            user=os.getenv("PGUSER", "restaurant"),
            password=os.getenv("PGPASSWORD", "restaurant"),
            database=os.getenv("PGDATABASE", "restaurant"),
        )

    def to_env(self) -> Dict[str, str]:
        return {
            "PGHOST": self.host,
            "PGPORT": str(self.port),
            "PGUSER": self.user,
            "PGPASSWORD": self.password,
            "PGDATABASE": self.database,
        }

    def to_dsn_kwargs(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "dbname": self.database,
        }


@dataclass
class EnvironmentConfig:
    db: DBConfig = field(default_factory=DBConfig)

    docker_image: str = "pgvector/pgvector:pg16"
    docker_container_name: str = "momento-postgres"
    schema_path: str = "momento/db/schema.sql"
    seeds_dir: str = "momento/db/seeds"
    scenarios_dir: str = "momento/envs/scenarios"
    docker_timeout: int = 30
