from __future__ import annotations
import os
from typing import Literal

import litellm
from beartype.typing import Any, Dict, List, Optional, Tuple
from litellm.types.utils import Message
from momento.utils.error_handler import exponential_backoff


@exponential_backoff(retries=5, base_wait_time=1)
def model_inference(
    # required parameters
    model: str,
    messages: List[Dict[str, Any]],
    # optional parameters
    base_url: Optional[str] = None,
    temperature: Optional[float] = 0.0,
    top_p: Optional[float] = None,
    n: Optional[int] = 1,
    stream: Optional[bool] = None,
    max_tokens: Optional[int] = 4096,
    max_completion_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    api_key: Optional[str] = None,
    reasoning_effort: Optional[
        Literal["none", "minimal", "low", "medium", "high", "xhigh", "default"] | None
    ] = None,
    top_k: Optional[int] = None,
) -> Tuple[Message, Dict[str, int]]:

    completion = litellm.completion(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        n=n,
        stream=stream,
        max_tokens=max_tokens,
        max_completion_tokens=max_completion_tokens,
        tools=tools,
        tool_choice=tool_choice,
        api_base=base_url,
        api_key=api_key or os.getenv("API_KEY"),
        reasoning_effort=reasoning_effort,
        top_k=top_k,
    )
    message: Message = completion.choices[0].message  # type: ignore
    assert message is not None
    assert isinstance(message, Message)

    usage_obj = getattr(completion, "usage", None)
    if usage_obj:
        usage: Dict[str, int] = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
        }
    else:
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    return message, usage
