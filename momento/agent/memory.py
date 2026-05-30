from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from momento.utils.inference import model_inference
from momento.utils.logger import get_logger
from momento.utils.token_utils import count_message_tokens
from momento.utils.utils import strip_thinking
from momento.envs.repository.base import get_recall_connection
from momento.envs.repository.session_repository import SessionRepository
from momento.envs.services.embedding import embed_text, to_pg_vector

logger = get_logger(__name__)


_RECALL_EMBEDDING_PLACEHOLDER = ":query_embedding"
_RECALL_USER_ID_PLACEHOLDER = ":user_id"
RECALL_INSTRUCTION = "Given a user message, retrieve past chat session summaries that are relevant to it."


class LongTermMemory:
    SQL_PROMPT = (
        "You generate a single PostgreSQL SELECT that retrieves past chat "
        "sessions relevant to the user's latest message.\n\n"
        "Hard rules:\n"
        "- Output ONLY the SQL. No prose. No markdown fences. No semicolon"
        "  inside or at the end.\n"
        "- One statement starting with SELECT. WITH / CTE are not allowed.\n"
        "- Only reference these tables: sessions.\n"
        "- Use the placeholder :query_embedding (cast as ::vector) wherever"
        "  you want the semantic vector. Never write a literal vector.\n"
        "- Use the placeholder :user_id for the authenticated user. Always"
        "  include `WHERE user_id = :user_id` (combine with AND for other"
        "  predicates).\n"
        "- Always SELECT at minimum: id, user_id, started_at, ended_at,"
        "  summary, extracted_facts.\n"
        "- Always include a LIMIT (3 is a good default).\n"
        "- Resolve any relative date the user mentioned using the TODAY value"
        "  provided in the user message as a date literal (e.g. '2026-05-18'::date)."
        "  NEVER use CURRENT_DATE or NOW(). Use Postgres date arithmetic (e.g."
        "  '<today>'::date - INTERVAL '7 days', EXTRACT(DOW FROM started_at),"
        "  EXTRACT(HOUR FROM started_at)).\n\n"
        "Schema:\n"
        "  sessions(id UUID, user_id TEXT, started_at TIMESTAMPTZ,\n"
        "           ended_at TIMESTAMPTZ, summary TEXT,\n"
        "           extracted_facts JSONB, embedding vector(1024))\n"
        "Note: started_at is when the session began, ended_at is when it ended. extracted_facts is a JSON object with key details from the session.\n\n"
        "Examples:\n"
        "  User: 'what I always ask on Friday night'\n"
        "  SQL: SELECT id, user_id, started_at, ended_at, summary, extracted_facts,\n"
        "              1 - (embedding <=> :query_embedding::vector) AS similarity\n"
        "       FROM sessions\n"
        "       WHERE user_id = :user_id\n"
        "       ORDER BY embedding <=> :query_embedding::vector\n"
        "       LIMIT 3\n\n"
        "  User: 'what did we discuss last week'\n"
        "  SQL: SELECT id, user_id, started_at, ended_at, summary, extracted_facts,\n"
        "              1 - (embedding <=> :query_embedding::vector) AS similarity\n"
        "       FROM sessions\n"
        "       WHERE user_id = :user_id\n"
        "         AND started_at >= '2026-05-11'::date\n"
        "       ORDER BY embedding <=> :query_embedding::vector\n"
        "       LIMIT 3"
    )

    def __init__(
        self,
        user_id: str,
        current_date: str,
        min_similarity: float = 0.0,
        sql_model: Optional[str] = None,
        base_url: Optional[str] = None,
        token_usage: Optional[Dict[str, int]] = None,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.user_id = user_id
        self.current_date = current_date
        self.min_similarity = min_similarity
        self.sql_model = sql_model
        self.base_url = base_url
        self.token_usage = token_usage if token_usage is not None else {}
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.reasoning_effort = reasoning_effort
        self.api_key = api_key or os.getenv("AGENT_API_KEY")
        self._last_query: Optional[str] = None
        self._last_block: str = ""

    def recall(self, query: str) -> str:
        query = (query or "").strip()
        if not query:
            return self._last_block
        if query == self._last_query:
            return self._last_block

        try:
            embedding = embed_text(query, instruction=RECALL_INSTRUCTION)
        except Exception as exc:
            logger.warning("Embedding failed during recall: %s", exc)
            self._last_query = query
            self._last_block = ""
            return ""

        sql = self._generate_sql(query)
        results: Optional[List[Dict[str, Any]]] = None
        if sql:
            results = self._execute_safe(sql, embedding)

        executed_sql: Optional[str] = sql if results is not None else None
        if results is None:
            results = self._fallback_recall(embedding)

        results = [
            r for r in results if (r.get("similarity") or 0.0) >= self.min_similarity
        ]
        block = self._format(results, sql=executed_sql)
        self._last_query = query
        self._last_block = block
        return block

    def reset(self) -> None:
        self._last_query = None
        self._last_block = ""

    def _generate_sql(self, query: str) -> Optional[str]:
        if not self.sql_model:
            return None
        try:
            response, usage = model_inference(
                model=self.sql_model,
                messages=[
                    {"role": "system", "content": self.SQL_PROMPT},
                    {
                        "role": "user",
                        "content": f"TODAY: {self.current_date}\nUSER MESSAGE: {query}",
                    },
                ],
                base_url=self.base_url,
                temperature=self.temperature,
                max_tokens=1024,
                api_key=self.api_key,
                top_p=self.top_p,
                top_k=self.top_k,
                reasoning_effort=self.reasoning_effort, # type: ignore
            )
            for key, value in usage.items():
                self.token_usage[key] = self.token_usage.get(key, 0) + value
            raw = strip_thinking(response.content or "")
            sql = _strip_code_fences(raw).strip().rstrip(";").strip()
            return sql or None
        except Exception as exc:
            logger.warning("Recall SQL generation failed: %s", exc)
            return None

    def _execute_safe(
        self, inner_sql: str, embedding: List[float]
    ) -> Optional[List[Dict[str, Any]]]:
        embed_str = to_pg_vector(embedding)
        prepared, placeholder_params = _substitute_placeholders(
            inner_sql,
            {
                _RECALL_EMBEDDING_PLACEHOLDER: embed_str,
                _RECALL_USER_ID_PLACEHOLDER: self.user_id,
            },
        )
        wrapped = (
            "SELECT * FROM (\n"
            + prepared
            + "\n) AS recall_sub WHERE recall_sub.user_id = %s"
        )
        params: Tuple[Any, ...] = tuple(placeholder_params) + (self.user_id,)

        conn = None
        try:
            conn = get_recall_connection()
            with conn.cursor() as cursor:
                cursor.execute(wrapped, params)
                rows = [dict(r) for r in cursor.fetchall()]
            conn.rollback()
            return rows
        except Exception as exc:
            logger.warning("Recall SQL execution failed (%s): %r", exc, inner_sql)
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _fallback_recall(self, embedding: List[float]) -> List[Dict[str, Any]]:
        try:
            return SessionRepository().find_relevant(
                user_id=self.user_id,
                query_embedding=embedding,
                top_k=3,
            )
        except Exception as exc:
            logger.warning("Fallback recall failed: %s", exc)
            return []

    @staticmethod
    def _format(
        results: List[Dict[str, Any]],
        sql: Optional[str] = None,
    ) -> str:
        if not results:
            return ""
        lines: List[str] = ["# Past sessions:"]
        for i, r in enumerate(results, 1):
            started = r.get("started_at", "?")
            ended = r.get("ended_at", "")
            summary = (r.get("summary") or "").strip()
            facts = r.get("extracted_facts") or {}
            if isinstance(facts, str):
                try:
                    facts = json.loads(facts)
                except json.JSONDecodeError:
                    facts = {}
            sim = r.get("similarity")
            sim_str = f", similarity={sim:.2f}" if isinstance(sim, (int, float)) else ""
            lines.append(f"[Session {i}: {started} -> {ended}{sim_str}]")
            if summary:
                lines.append(f"Summary: {summary}")
            if isinstance(facts, dict) and facts:
                fact_lines = [f"- {k}: {v}" for k, v in facts.items() if v]
                if fact_lines:
                    lines.append("Facts:")
                    lines.extend(fact_lines)
            lines.append("")
        return "\n".join(lines).strip()


class ConversationCompressor:
    SUMMARIZER_PROMPT = (
        "You are a memory compression system. Summarize the following "
        "conversation messages into a compact structured memory.\n\n"
        "Rules:\n"
        "- Preserve ALL entity names and their IDs exactly.\n"
        "- Preserve tool call names, key parameters, and their results.\n"
        "- Preserve user decisions, confirmations, and stated preferences.\n"
        "- Label each fact with the speaker role: [USER], [ASSISTANT], or [TOOL].\n"
        "- Remove filler, pleasantries, and redundant restatements.\n"
        "- Do NOT hallucinate or infer information not present in the input.\n"
        "- Output concise bullet points grouped by topic."
    )

    def __init__(
        self,
        agent_model: str,
        summarizer_model: str,
        agent_context_tokens: int,
        max_response_tokens: int,
        base_url: Optional[str] = None,
        token_usage: Optional[Dict[str, int]] = None,
        keep_ratio: float = 0.8,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.agent_model = agent_model
        self.summarizer_model = summarizer_model
        self.agent_context_tokens = agent_context_tokens
        self.max_response_tokens = max_response_tokens
        self.base_url = base_url
        self.token_usage = token_usage if token_usage is not None else {}
        self.keep_ratio = keep_ratio
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.reasoning_effort = reasoning_effort
        self.api_key = api_key or os.getenv("AGENT_API_KEY")

        self._summarizer_overhead = count_message_tokens(
            self.summarizer_model,
            [
                {"role": "system", "content": self.SUMMARIZER_PROMPT},
                {"role": "user", "content": "Messages to compress:\n"},
            ],
        )

    def maybe_compress(
        self,
        history: List[Dict[str, Any]],
        head_tokens: int,
    ) -> List[Dict[str, Any]]:
        """Return a possibly-compressed copy of ``history``.

        ``head_tokens`` is the token cost of everything that precedes
        ``history`` in the agent's message list (system prompt + tools + any
        sticky retrieval block). It is subtracted from the agent context
        window when deciding how much of ``history`` to keep.
        """
        available = self.agent_context_tokens - head_tokens - self.max_response_tokens
        if available <= 0:
            logger.warning("Fixed tokens exceed context window; skipping compression.")
            return history

        history_tokens = count_message_tokens(self.agent_model, history)
        if history_tokens <= available:
            return history

        groups = _build_groups(history)
        if len(groups) < 2:
            return history

        keep_budget = int(available * self.keep_ratio)
        kept_groups: List[List[Dict[str, Any]]] = []
        kept_tokens = 0
        for g in reversed(groups):
            g_tokens = count_message_tokens(self.agent_model, g)
            if kept_tokens + g_tokens <= keep_budget or not kept_groups:
                kept_groups.insert(0, g)
                kept_tokens += g_tokens

        to_summarize_groups = groups[: len(groups) - len(kept_groups)]
        if not to_summarize_groups:
            return history

        summarizer_budget = (
            self.agent_context_tokens
            - self._summarizer_overhead
            - self.max_response_tokens
        )
        to_summarize: List[Dict[str, Any]] = []
        leftover_groups: List[List[Dict[str, Any]]] = []
        budget_used = 0
        for idx, g in enumerate(to_summarize_groups):
            g_tokens = count_message_tokens(self.agent_model, g)
            if to_summarize and budget_used + g_tokens > summarizer_budget:
                leftover_groups = to_summarize_groups[idx:]
                break
            budget_used += g_tokens
            to_summarize.extend(g)

        if not to_summarize:
            return history

        summary_text = self._summarize(to_summarize)
        summary_msg: Dict[str, Any] = {
            "role": "system",
            "content": (
                "[Conversation summary - older messages compressed]\n" + summary_text
            ),
        }

        remaining: List[Dict[str, Any]] = [summary_msg]
        for g in leftover_groups + kept_groups:
            remaining.extend(g)

        logger.debug(
            "Compressed %d messages into a summary; %d messages remain.",
            len(to_summarize),
            len(remaining),
        )
        return remaining

    def _summarize(self, messages: List[Dict[str, Any]]) -> str:
        turns_text = _messages_to_text(messages)
        try:
            response, usage = model_inference(
                model=self.summarizer_model,
                messages=[
                    {"role": "system", "content": self.SUMMARIZER_PROMPT},
                    {"role": "user", "content": f"Messages to compress:\n{turns_text}"},
                ],
                base_url=self.base_url,
                temperature=self.temperature,
                max_tokens=self.max_response_tokens,
                api_key=self.api_key,
                top_p=self.top_p,
                top_k=self.top_k,
                reasoning_effort=self.reasoning_effort, # type: ignore
            )
            for key, value in usage.items():
                self.token_usage[key] = self.token_usage.get(key, 0) + value
            return strip_thinking(response.content or "")
        except Exception as exc:
            logger.warning("Memory summarization failed, falling back to tail: %s", exc)
            lines = turns_text.strip().splitlines()
            return "\n".join(lines[-20:]) if len(lines) > 20 else turns_text


def _build_groups(history: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    i = 0
    while i < len(history):
        msg = history[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            group = [msg]
            i += 1
            while i < len(history) and history[i].get("role") == "tool":
                group.append(history[i])
                i += 1
            groups.append(group)
        else:
            groups.append([msg])
            i += 1
    return groups


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text[3:]
        for tag in ("sql", "postgres", "postgresql", "json"):
            if text[: len(tag)].lower() == tag:
                text = text[len(tag) :]
                break
        text = text.lstrip("\r\n")
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _substitute_placeholders(
    sql: str, mapping: Dict[str, Any]
) -> Tuple[str, List[Any]]:
    if not mapping:
        return sql, []
    keys = sorted(mapping.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    params: List[Any] = []

    def _repl(match: "re.Match[str]") -> str:
        params.append(mapping[match.group(0)])
        return "%s"

    return pattern.sub(_repl, sql), params


def _messages_to_text(messages: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")

        if tool_calls:
            calls: List[str] = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {}).get("name", "?")
                    args = tc.get("function", {}).get("arguments", "")
                else:
                    func = getattr(tc, "function", None)
                    fn = getattr(func, "name", "?")
                    args = getattr(func, "arguments", "")
                calls.append(f"{fn}({args})")
            parts.append(f"[{role}] tool_calls: {'; '.join(calls)}")
        elif role == "TOOL":
            tool_id = msg.get("tool_call_id", "")
            parts.append(f"[TOOL {tool_id}] {content}")
        else:
            parts.append(f"[{role}] {content or ''}")
    return "\n".join(parts)
