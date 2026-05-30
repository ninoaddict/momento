from __future__ import annotations

from typing import Any, Optional

from momento.envs.repository.base import BaseRepository
from momento.envs.services.embedding import to_pg_vector


class SessionRepository(BaseRepository):
    def find_relevant(
        self,
        user_id: str,
        query_embedding: list[float],
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:

        vec = to_pg_vector(query_embedding)

        conditions = ["s.user_id = %s", "s.embedding IS NOT NULL"]
        params: list[Any] = [vec, user_id]

        if from_date:
            conditions.append("s.started_at >= %s::date")
            params.append(from_date)
        if to_date:
            conditions.append("s.started_at <= %s::date")
            params.append(to_date)

        params.extend([vec, top_k])
        where = " AND ".join(conditions)

        sql = f"""
            SELECT
                s.id::text,
                s.user_id,
                s.started_at::text,
                s.ended_at::text,
                s.summary,
                s.extracted_facts,
                1 - (s.embedding <=> %s::vector) AS similarity
            FROM sessions s
            WHERE {where}
            ORDER BY s.embedding <=> %s::vector
            LIMIT %s
        """
        return self._fetch_all(sql, tuple(params))
