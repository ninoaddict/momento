# Momento: Evaluating Persistent Memory and Reasoning with Multi-Session Agentic Conversations

<p align="center">
  <img src="./assets/architecture.png" alt="Overview of the Momento Architecture" width="85%"/>
</p>

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Key Finding](#key-finding)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [1. Clone the repository](#1-clone-the-repository)
  - [2. Install dependencies (with `uv`)](#2-install-dependencies-with-uv)
  - [3. Download the scenario images](#3-download-the-scenario-images)
  - [4. Configure environment variables (`.env`)](#4-configure-environment-variables-env)
  - [5. Configure the run (`config.json`)](#5-configure-the-run-configjson)
- [Running the Benchmark](#running-the-benchmark)
- [Aggregating Partial Results](#aggregating-partial-results)
- [Re-evaluation / Post-evaluation](#re-evaluation--post-evaluation)
- [Repository Structure](#repository-structure)
- [Citation](#citation)
- [Contact](#contact)

## Overview

**Momento** is a benchmark and evaluation framework for persistent agentic task completion in multi-session, multi-modal service environments. Unlike prior work on conversational agents, Momento requires agents to take consequential, tool-mediated actions grounded in structured domain data, while resolving temporal dependencies and evolving user goals that emerge only across sessions.

The benchmark is built around a restaurant-assistant domain backed by a real PostgreSQL database. An agent under test interacts with a rich toolset (reservations, orders, memberships, restaurant search, menu queries, etc.), driven by an LLM-based simulated user, across sessions that are temporally separated. 

We evaluate agent performance using three metrics: DB State, which checks whether the final database state matches the goal; Output, which measures whether the response satisfies the user request; and Tool Recall, which evaluates whether the correct tools are invoked in the correct order. Tool matching uses arguments for mutation tools and execution results for query tools. A task is considered successful only if all three metrics are satisfied.

## Key Finding

Experimental results reveal that current agents fail primarily through misestimation of user state, treating prior session history as a reliable proxy for current context rather than stale information requiring re-validation, highlighting a substantial gap between current agent capabilities and realistic long-horizon human-agent interaction.

## Setup

### Prerequisites

- **Python 3.10+**
- **Docker**: the environment automatically spins up a PostgreSQL container (`pgvector/pgvector:pg16`) to host the restaurant database, seed data, and per-session memory store. Docker must be installed and running.
- **LLM API access**: an OpenAI-compatible endpoint (e.g., [OpenRouter](https://openrouter.ai)) for the agent, simulated user, and judge models. Momento uses [LiteLLM](https://github.com/BerriAI/litellm) under the hood, so any LiteLLM-supported provider works.

### 1. Clone the repository

```bash
git clone https://github.com/ninoaddict/momento.git
cd momento
```

### 2. Install dependencies (with `uv`)

[`uv`](https://github.com/astral-sh/uv) is the recommended way to manage the environment.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# On Windows (PowerShell):
#   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Create and activate a virtual environment
uv venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\Activate.ps1     # Windows (PowerShell)

# Install dependencies
uv pip install -r requirements.txt
```

<details>
<summary>Alternative: plain <code>pip</code></summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

</details>

### 3. Download the scenario images

The scenarios themselves are loaded automatically from Hugging Face (`adrilmanurung/momento`) the first time you run the benchmark, **no manual download is needed for the scenario data**.

However, the multi-modal **images are not bundled** with the scenarios. You must download `images.zip` from the dataset and extract it into `momento/images`:

1. Download `images.zip` from [`adrilmanurung/momento`](https://huggingface.co/datasets/adrilmanurung/momento).
2. Extract its contents into `momento/images/` so that the image files sit directly inside that folder.

```bash
# From the repository root, after downloading images.zip
mkdir -p momento/images
unzip images.zip -d momento/images
```

The resulting layout should look like:

```
momento/images/
├── 960px-Katsudon_001.jpg
├── 960px-Onigiri_002.jpg
├── ...
```

> At runtime, image references in a task (often `http(s)` URLs) are resolved by filename against `momento/images/`. If a local file is missing, that image is skipped with a warning, so make sure the extraction completed successfully.

### 4. Configure environment variables (`.env`)

Copy `.env.example` to `.env` and fill in your API keys. The database section can usually be left at its defaults — those values are passed straight to the Docker container that the environment launches.

```bash
cp .env.example .env
```

```dotenv
# Database
# Either set DATABASE_URL (takes priority) or the individual PG* vars below.
# DATABASE_URL=postgresql://restaurant:restaurant@localhost:5433/restaurant

PGHOST=localhost
PGPORT=5433
PGUSER=restaurant
PGPASSWORD=restaurant
PGDATABASE=restaurant

# Read-only user for memory/session recall queries
PG_RECALL_USER=recall_reader
PG_RECALL_PASSWORD=recall_reader

# LLM API keys
# Keys for each role; falls back to API_KEY when the role-specific key is unset.
AGENT_API_KEY=
USER_API_KEY=
JUDGE_API_KEY=
API_KEY=
```

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | No | Full Postgres DSN. If set, it takes priority over the individual `PG*` variables. |
| `PGHOST` | No | Database host (default `localhost`). |
| `PGPORT` | No | Host port mapped to the container's Postgres (default `5433`). |
| `PGUSER` | No | Database superuser used for seeding/state checks (default `restaurant`). |
| `PGPASSWORD` | No | Password for `PGUSER` (default `restaurant`). |
| `PGDATABASE` | No | Database name (default `restaurant`). |
| `PG_RECALL_USER` | No | Read-only role the agent's memory/recall layer uses for text-to-SQL queries over past sessions (default `recall_reader`). This role is created automatically by the schema. |
| `PG_RECALL_PASSWORD` | No | Password for the recall role (default `recall_reader`). |
| `AGENT_API_KEY` | Yes\* | API key for the agent model. Falls back to `API_KEY` if unset. |
| `USER_API_KEY` | Yes\* | API key for the simulated-user model. Falls back to `API_KEY` if unset. |
| `JUDGE_API_KEY` | Yes\* | API key for the judge model. Falls back to `API_KEY` if unset. |
| `API_KEY` | Yes\* | Shared fallback API key used by any role whose specific key is unset. |

\* You need at least one valid key per role. Setting only `API_KEY` is enough if all three roles share the same provider.

### 5. Configure the run (`config.json`)

The benchmark is driven by a JSON config (see [`configs/sample_config.json`](configs/sample_config.json)). Every field is optional — omitted fields fall back to the dataclass defaults in [`momento/types/config.py`](momento/types/config.py). CLI flags override values from the config file.

A typical config:

```json
{
  "agent-model": "google/gemma-4-31b-it",
  "agent-base-url": "https://openrouter.ai/api/v1",
  "agent-temperature": 1.0,
  "agent-max-tokens": 8192,
  "agent-top-p": 0.95,
  "agent-top-k": 64,

  "user-model": "google/gemma-4-31b-it",
  "user-base-url": "https://openrouter.ai/api/v1",
  "user-temperature": 1.0,
  "user-max-tokens": 8192,

  "max-turns": 15,
  "max-tool-rounds": 15,
  "max-context-tokens": 128000,

  "start-index": 0,
  "end-index": -1,
  "task-ids": null,

  "judge-model": "google/gemma-4-31b-it",
  "judge-base-url": "https://openrouter.ai/api/v1",
  "judge-temperature": 0.0,
  "n-trials": 3,

  "output-dir": "results",
  "prompt_path": "momento/prompts/agent.md",
  "policy_path": "momento/prompts/policy.md"
}
```

#### Config fields

**Agent settings** (the model under evaluation)

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `agent-model` | string | `qwen/qwen3-vl-30b-a3b-thinking` | Model identifier (LiteLLM format) for the agent. |
| `agent-base-url` | string \| null | `null` | OpenAI-compatible base URL for the agent provider. |
| `agent-temperature` | float | `0.0` | Sampling temperature. |
| `agent-max-tokens` | int | `4096` | Max tokens generated per agent response. |
| `agent-top-p` | float \| null | `null` | Nucleus-sampling `top_p` (provider-dependent). |
| `agent-top-k` | int \| null | `null` | `top_k` sampling (provider-dependent). |
| `agent-reasoning-effort` | string \| null | `null` | Reasoning-effort hint for reasoning models (e.g. `low`/`medium`/`high`), if supported. |

**Simulated user settings** (the LLM that role-plays the user)

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `user-model` | string | `openai/gpt-4o-mini` | Model identifier for the simulated user. |
| `user-base-url` | string \| null | `null` | Base URL for the user provider. |
| `user-temperature` | float | `0.0` | Sampling temperature. |
| `user-max-tokens` | int | `4096` | Max tokens per user response. |
| `user-top-p` | float \| null | `null` | Nucleus-sampling `top_p`. |
| `user-top-k` | int \| null | `null` | `top_k` sampling. |
| `user-reasoning-effort` | string \| null | `null` | Reasoning-effort hint for the user model. |

**Simulation limits**

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `max-turns` | int | `15` | Maximum number of user-agent turns per trial before the conversation is cut off. |
| `max-tool-rounds` | int | `15` | Maximum number of tool-calling rounds the agent may take within a single turn. |

**Memory management**

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `max-context-tokens` | int | `32768` | Agent model context-window size; used to manage/trim conversation context. Set to your model's actual context length. |

**Scenario selection**

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `start-index` | int | `0` | Index of the first task to run (within the sorted scenario list). |
| `end-index` | int | `-1` | Index of the last task (exclusive); `-1` means run to the end. |
| `task-ids` | list[int] \| null | `null` | Explicit list of task IDs to run. Overrides `start-index`/`end-index` when set. |

**Benchmark / judge settings**

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `judge-model` | string | `openai/gpt-4o-mini` | LLM-as-Judge model used for information-coverage scoring. |
| `judge-base-url` | string \| null | `null` | Base URL for the judge provider. |
| `judge-temperature` | float | `0.0` | Judge sampling temperature (keep low for determinism). |
| `judge-max-tokens` | int | `4096` | Max tokens per judge response. |
| `judge-top-p` | float \| null | `null` | Nucleus-sampling `top_p` for the judge. |
| `judge-top-k` | int \| null | `null` | `top_k` for the judge. |
| `judge-reasoning-effort` | string \| null | `null` | Reasoning-effort hint for the judge. |
| `n-trials` | int | `3` | Number of independent trials run per task (used to compute `Pass@k` and `Pass^k`). |

**Paths**

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `output-dir` | string | `results` | Directory where per-task summaries (`task_*.json`) and the final `benchmark.json` are written. |
| `prompt_path` | string | `momento/prompts/agent.md` | Path to the agent system prompt. |
| `policy_path` | string | `momento/prompts/policy.md` | Path to the domain policy the agent must follow. |

> **Note on key naming:** both hyphenated (`agent-model`) and underscored (`agent_model`) keys are accepted in the config file — they are normalized internally. The CLI flags use hyphens (e.g. `--agent-model`).

## Running the Benchmark

Make sure Docker is running (the environment launches and seeds a Postgres container automatically), then run [`momento/run.py`](momento/run.py):

```bash
# Run with a config file
python -m momento.run --config configs/sample_config.json
```

You can override any config value with a CLI flag (flags take precedence over the file):

```bash
# Override the agent model and run only a few tasks
python -m momento.run \
  --config configs/sample_config.json \
  --agent-model "openai/gpt-5.4-mini" \
  --task-ids 1 2 3 \
  --n-trials 3
```

What happens during a run:

1. The environment starts the Postgres container, applies the schema (including the read-only `recall_reader` role), and seeds base data.
2. Scenarios are downloaded from Hugging Face (`adrilmanurung/momento`) and filtered by your selection settings.
3. For each task, the session history is seeded, then `n-trials` independent trials are run. Each trial resets the transactional DB state, runs the agent↔simulated-user loop, and is evaluated on DB state, information coverage, and tool recall.
4. A per-task summary is written to `<output-dir>/task_<id>.json` **as each task completes**, and a final aggregate is written to `<output-dir>/benchmark.json`.

Because every task is checkpointed to disk as it finishes, you can safely interrupt a long run and still aggregate whatever has completed (see below).

## Aggregating Partial Results

If a run is interrupted (or you want an intermediate snapshot before `benchmark.json` is produced), use [`momento/aggregate.py`](momento/aggregate.py) to compute benchmark-level metrics from the `task_*.json` files already written to a run folder:

```bash
# Aggregate every task_*.json in the results folder
python -m momento.aggregate results

# Write the aggregate somewhere specific
python -m momento.aggregate results --output results/partial_benchmark.json
```

| Argument | Description |
| --- | --- |
| `folder` (positional) | Path to the run folder containing `task_*.json` files. |
| `--output` | Output file path. Defaults to `<folder>/partial_benchmark.json`. |

It prints and saves averaged metrics: `average_db_state_match`, `average_information_coverage`, `average_tool_recall`, `average_pass_at_k`, `average_pass_hat_k`, and `total_tokens`. This is purely a read-and-aggregate step — it does **not** re-run any model or touch the database.

## Re-evaluation / Post-evaluation

After a run, you may want to **re-score saved trajectories** without re-running the (expensive) agent simulations, for example, after editing a scenario's `action_dags` or `expected_information`, or to re-run the LLM judge with a different model. Use [`momento/evaluation.py`](momento/evaluation.py):

```bash
# Re-evaluate a run folder against the current scenario definitions
python -m momento.evaluation results

# Re-run with a specific judge model, writing to a custom output dir
python -m momento.evaluation results \
  --judge-model "google/gemma-4-31b-it" \
  --judge-base-url "https://openrouter.ai/api/v1" \
  --output-dir results/reevaluated
```

| Argument | Default | Description |
| --- | --- | --- |
| `folder` (positional) | - | Run folder containing the `task_*.json` files to re-evaluate. |
| `--scenarios-dir` | `momento/envs/scenarios` | Directory containing scenario definitions (used for validation). |
| `--output-dir` | `<folder>/reevaluated` | Where re-evaluated summaries and `benchmark.json` are written. |
| `--judge-model` | `openai/gpt-4o-mini` | LLM judge model for information coverage. |
| `--judge-base-url` | `null` | LLM judge API base URL. |
| `--skip-info-coverage` | off | Skip re-running the LLM judge; reuse the saved information-coverage scores (saves API cost). |
| `--use-db` | off | Spin up the live environment, replay each trial's recorded actions against a freshly reset DB, and recompute DB-state hashes. **Requires Docker.** |

How re-evaluation handles each metric:

- **Tool recall** is always recomputed against the current scenario `action_dags`.
- **Information coverage** is recomputed via the LLM judge unless `--skip-info-coverage` is passed (in which case the saved scores are reused).
- **DB state** is carried over from the original run by default. Pass `--use-db` to replay the recorded actions and recompute it from scratch (this is the only mode that needs Docker).

## Repository Structure

- **`momento/run.py`**: main benchmark driver (agent and simulated-user loop, per-trial evaluation, result writing).
- **`momento/aggregate.py`**: aggregate `task_*.json` files into benchmark-level metrics (partial/intermediate results).
- **`momento/evaluation.py`**: re-evaluate saved trajectories against current scenario definitions.
- **`momento/agent/`**: the agent under test and its long-term memory/recall layer.
- **`momento/user/`**: the LLM-based simulated user.
- **`momento/eval/`**: evaluator implementing DB-state, information-coverage, and tool-recall scoring.
- **`momento/envs/`**: the restaurant environment: Docker/Postgres lifecycle, repositories, the agent toolset, and scenario loading.
- **`momento/db/`**: database schema (`schema.sql`) and seed data (`seeds/`).
- **`momento/prompts/`**: agent system prompt (`agent.md`) and domain policy (`policy.md`).
- **`momento/images/`**: multi-modal scenario images (downloaded separately, see [Setup](#3-download-the-scenario-images)).
- **`momento/types/`**: dataclasses for configs, tasks, and evaluation results.
- **`configs/`**: example run configurations.

## Contact

For questions or issues, please open an issue on GitHub or contact [Adril Putra Merin](mailto:adrilbless37@gmail.com).
