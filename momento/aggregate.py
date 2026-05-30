from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_task_summaries(folder: Path) -> List[Dict[str, Any]]:
    files = sorted(folder.glob("task_*.json"))
    summaries: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            summaries.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: failed to read {path}: {exc}")
    return summaries


def _summary_db_state_match(s: Dict[str, Any]) -> float:
    trials = s.get("trials") or []
    if trials:
        passed = sum(
            1.0 for t in trials if (t.get("db_state_result") or {}).get("passed", False)
        )
        return passed / len(trials)
    if "db_state_match" in s:
        return float(s["db_state_match"])
    return 0.0


def _trial_information_coverage(trial: Dict[str, Any]) -> float:
    ic = trial.get("information_coverage_result") or {}
    if "coverage_score" in ic:
        return float(ic["coverage_score"])
    total = int(ic.get("total_items", 0))
    if total == 0:
        return 1.0
    return float(ic.get("covered_items", 0)) / total


def _summary_information_coverage(s: Dict[str, Any]) -> float:
    trials = s.get("trials") or []
    if trials:
        return sum(_trial_information_coverage(t) for t in trials) / len(trials)
    if "information_coverage" in s:
        return float(s["information_coverage"])
    return 0.0


def _trial_tool_recall(trial: Dict[str, Any]) -> float:
    tr = trial.get("tool_recall_result") or {}
    if "recall" in tr:
        return float(tr["recall"])
    total = int(tr.get("total_nodes", 0))
    if total == 0:
        return 1.0
    return float(tr.get("correct_nodes", 0)) / total


def _summary_tool_recall(s: Dict[str, Any]) -> float:
    trials = s.get("trials") or []
    if trials:
        return sum(_trial_tool_recall(t) for t in trials) / len(trials)
    if "tool_recall" in s:
        return float(s["tool_recall"])
    return 0.0


def _aggregate(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_tasks = len(summaries)
    metrics: Dict[str, Any] = {
        "average_db_state_match": 0.0,
        "average_information_coverage": 0.0,
        "average_tool_recall": 0.0,
        "average_pass_at_k": {},
        "average_pass_hat_k": {},
        "total_tokens": {},
    }

    if total_tasks == 0:
        return {
            "total_tasks": 0,
            "metrics": metrics
        }

    db_sum = sum(_summary_db_state_match(s) for s in summaries)
    ic_sum = sum(_summary_information_coverage(s) for s in summaries)
    recall_sum = sum(_summary_tool_recall(s) for s in summaries)
    metrics["average_db_state_match"] = db_sum / total_tasks
    metrics["average_information_coverage"] = ic_sum / total_tasks
    metrics["average_tool_recall"] = recall_sum / total_tasks

    max_k = max((len(s.get("trials", [])) for s in summaries), default=0)
    avg_pass_at_k: Dict[int, float] = {}
    avg_pass_hat_k: Dict[int, float] = {}
    for k in range(1, max_k + 1):
        key = str(k)
        pak_sum = sum(
            float(s.get("pass_at_k", {}).get(key, 0.0)) for s in summaries
        )
        phk_sum = sum(
            float(s.get("pass_hat_k", {}).get(key, 0.0)) for s in summaries
        )
        avg_pass_at_k[k] = pak_sum / total_tasks
        avg_pass_hat_k[k] = phk_sum / total_tasks
    metrics["average_pass_at_k"] = avg_pass_at_k
    metrics["average_pass_hat_k"] = avg_pass_hat_k

    total_tokens: Dict[str, int] = {}
    for s in summaries:
        for trial in s.get("trials", []):
            for token_key, count in (trial.get("token_usage") or {}).items():
                total_tokens[token_key] = total_tokens.get(token_key, 0) + int(count)
    metrics["total_tokens"] = total_tokens

    return {
        "total_tasks": total_tasks,
        "metrics": metrics,
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "folder",
        type=str,
        help="Path to the run folder containing task_*.json files.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path. Defaults to <folder>/partial_benchmark.json.",
    )
    args = parser.parse_args(argv)

    folder = Path(args.folder)
    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")

    summaries = _load_task_summaries(folder)
    if not summaries:
        print(f"No task_*.json files found in {folder}")
        return

    benchmark = _aggregate(summaries)
    output_path = (
        Path(args.output) if args.output else folder / "partial_benchmark.json"
    )
    output_path.write_text(
        json.dumps(benchmark, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    m = benchmark["metrics"]
    print(f"Aggregated {len(summaries)} task(s) from {folder}")
    print(f"  average_db_state_match:       {m['average_db_state_match']:.4f}")
    print(f"  average_information_coverage: {m['average_information_coverage']:.4f}")
    print(f"  average_tool_recall:          {m['average_tool_recall']:.4f}")
    if m["average_pass_at_k"]:
        pak = {k: round(v, 4) for k, v in m["average_pass_at_k"].items()}
        print(f"  average_pass_at_k:            {pak}")
    if m["average_pass_hat_k"]:
        phk = {k: round(v, 4) for k, v in m["average_pass_hat_k"].items()}
        print(f"  average_pass_hat_k:           {phk}")
    if m["total_tokens"]:
        print(f"  total_tokens:                 {m['total_tokens']}")
    print(f"Saved partial benchmark -> {output_path}")


if __name__ == "__main__":
    main()
