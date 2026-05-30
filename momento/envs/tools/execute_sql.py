import json
from typing import Any, Dict, Optional
from momento.envs.repository.base import get_connection
from momento.envs.tools.base import Tool, PolicyViolationError

BLOCKED_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "EXECUTE",
    "CALL",
    "SET ",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "LOCK",
    "VACUUM",
    "REINDEX",
    "CLUSTER",
    "REFRESH",
    "NOTIFY",
    "LISTEN",
    "UNLISTEN",
]


def _is_read_only(sql: str) -> bool:
    normalised = sql.strip().upper()
    for keyword in BLOCKED_KEYWORDS:
        if normalised.startswith(keyword) or f" {keyword}" in normalised:
            return False
    return normalised.startswith("SELECT") or normalised.startswith("WITH")


class ExecuteSQL(Tool):
    @staticmethod
    def invoke(
        query: str,
        max_rows: Optional[int] = 100,
    ) -> str:
        if not query or not query.strip():
            return "Error: query must not be empty"

        if not _is_read_only(query):
            raise PolicyViolationError(
                "Only read-only SELECT queries are allowed. "
                "Data-modifying statements (INSERT, UPDATE, DELETE, etc.) are prohibited."
            )

        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    columns = (
                        [desc[0] for desc in cursor.description]
                        if cursor.description
                        else []
                    )
                    rows = cursor.fetchmany(max_rows)
                    result = {
                        "columns": columns,
                        "rows": [
                            {col: val for col, val in zip(columns, row)}
                            for row in rows
                        ],
                        "row_count": len(rows),
                    }
                    return json.dumps(result, default=str)
        except Exception as exc:
            return f"Error: {exc}"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "execute_sql",
                "description": (
                    "Execute a read-only SQL SELECT query against the restaurant database. "
                    "Only SELECT statements are allowed; any data-modifying statement will be rejected. "
                    "Use get_database_schema first to understand available tables and columns. "
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "A read-only SQL SELECT query. "
                                "Must be a valid PostgreSQL query. "
                                "Do NOT include INSERT, UPDATE, DELETE, DROP, or other mutating statements."
                            ),
                        },
                        "max_rows": {
                            "type": "integer",
                            "default": 100,
                        },
                    },
                    "required": ["query"],
                },
            },
        }
