from __future__ import annotations

import json
from typing import Any, List, Optional
from litellm import token_counter

def estimate_tokens(obj: Any) -> int:
    if isinstance(obj, str):
        return max(1, len(obj) // 4)
    try:
        text = json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        text = str(obj)
    return max(1, len(text) // 4)


def count_message_tokens(
    model: str,
    messages: List[Any],
    tools: Optional[List[Any]] = None,
) -> int:
    try:
        return token_counter(model=model, messages=messages, tools=tools or [])
    except Exception:
        total = sum(
            4 + estimate_tokens(m.get("content") or "")
            for m in messages
        )
        if tools:
            total += estimate_tokens(tools)
        return total

