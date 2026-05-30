from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from momento.agent.memory import ConversationCompressor, LongTermMemory
from momento.envs.environment import ToolRegistry
from momento.types import Action, GenerationConfig
from momento.utils.inference import model_inference
from momento.utils.logger import get_logger
from momento.utils.token_utils import count_message_tokens
from momento.utils.utils import strip_thinking

logger = get_logger(__name__)


_RECALL_PLACEHOLDER = "{relevant_user_context}"
_EMPTY_RECALL_NOTE = "(no relevant past context retrieved for this turn)"


class Agent:
    def __init__(
        self,
        config: GenerationConfig,
        tool_registry: ToolRegistry,
        user_id: str,
        current_date: str,
    ) -> None:
        self.config = config
        self.tool_registry = tool_registry
        self.user_id = user_id
        self.current_date = current_date

        base_url = config.agent_base_url or os.environ.get("AGENT_BASE_URL") or ""
        self.model = config.agent_model
        self.base_url = base_url
        self.temperature = config.agent_temperature
        self.max_tokens = config.agent_max_tokens
        self.top_p = config.agent_top_p
        self.top_k = config.agent_top_k
        self.reasoning_effort = config.agent_reasoning_effort
        self.api_key = os.getenv("AGENT_API_KEY")
        self.max_tool_rounds = config.max_tool_rounds

        policy = Path(config.policy_path).read_text(encoding="utf-8")
        self._system_template = self._load_prompt(
            config.prompt_path,
            user_id=user_id,
            current_date=current_date,
            policy=policy,
            max_tool_rounds=str(self.max_tool_rounds),
        )

        self._tools: List[Dict[str, Any]] = self.tool_registry.get_tool_info()

        self.token_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        self.long_term_memory = LongTermMemory(
            user_id=user_id,
            current_date=current_date,
            sql_model=config.agent_model,
            base_url=self.base_url,
            token_usage=self.token_usage,
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            reasoning_effort=self.reasoning_effort,
            api_key=self.api_key,
        )
        self.compressor = ConversationCompressor(
            agent_model=self.model,
            summarizer_model=config.agent_model,
            agent_context_tokens=config.max_context_tokens,
            max_response_tokens=self.max_tokens,
            base_url=self.base_url,
            token_usage=self.token_usage,
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            reasoning_effort=self.reasoning_effort,
            api_key=self.api_key,
        )

        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._render_system_prompt("")},
        ]
        self.turn_id: int = 0
        self.actions: List[Action] = []
        self.policy_violations: List[Dict[str, Any]] = []

    # Public API
    def step(self, user_message: str, images: Optional[List[str]] = None) -> str:
        """Process one user turn and return the agent's reply.

        Args:
            user_message: The user's text message.
            images: Optional list of base64 data URLs for images.
        """
        self.turn_id += 1

        recall_block = self.long_term_memory.recall(user_message)
        logger.debug("Recall block for turn %d: %s", self.turn_id, recall_block)
        self.messages[0] = {
            "role": "system",
            "content": self._render_system_prompt(recall_block),
        }

        user_content = self._build_user_content(user_message, images)
        self.messages.append({"role": "user", "content": user_content})

        tools = self._tools or None
        tool_choice = "auto" if tools else None
        _images_stripped = False

        for _ in range(self.max_tool_rounds):
            try:
                response, usage = model_inference(
                    model=self.model,
                    messages=self.messages,
                    base_url=self.base_url,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                    api_key=self.api_key,
                    top_p=self.top_p,
                    top_k=self.top_k,
                    reasoning_effort=self.reasoning_effort, # type: ignore
                )
            except Exception as exc:
                logger.error("LLM inference failed on turn %d: %s", self.turn_id, exc)
                error_reply = (
                    "I'm sorry, something went wrong while processing your request. "
                    "Please try again."
                )
                self.messages.append({"role": "assistant", "content": error_reply})
                return error_reply

            if images and not _images_stripped:
                self._strip_images_from_last_user_message()
                _images_stripped = True

            for key, value in usage.items():
                self.token_usage[key] += value

            if response.tool_calls:
                resdict = response.to_dict()
                self.messages.append(
                    {
                        "role": resdict.get("role", "assistant"),
                        "content": resdict.get("content"),
                        "tool_calls": resdict.get("tool_calls"),
                        "function_call": resdict.get("function_call"),
                    }
                )
                _call_cache: Dict[str, str] = {}
                for tc in response.tool_calls:
                    key = f"{tc.function.name}:{tc.function.arguments}"
                    if key in _call_cache:
                        logger.debug(
                            "Duplicate tool call skipped: %s", tc.function.name
                        )
                        self.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": _call_cache[key],
                            }
                        )
                        continue
                    self._handle_tool_call(tc)
                    last = self.messages[-1]
                    if last.get("role") == "tool":
                        _call_cache[key] = last["content"]

                self._maybe_compress()
                continue

            reply = strip_thinking(response.content or "")
            self.messages.append({"role": "assistant", "content": reply})
            self._maybe_compress()
            return reply

        logger.warning(
            "Turn %d: hit max tool rounds (%d), requesting final answer.",
            self.turn_id,
            self.max_tool_rounds,
        )
        nudge: Dict[str, Any] = {
            "role": "user",
            "content": (
                "[System: Maximum tool calls reached. Summarize what you have "
                "gathered and give the user your best response now. "
                "Do not attempt further tool calls.]"
            ),
        }
        self.messages.append(nudge)
        try:
            response, usage = model_inference(
                model=self.model,
                messages=self.messages,
                base_url=self.base_url,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=self.api_key,
                top_p=self.top_p,
                top_k=self.top_k,
                reasoning_effort=self.reasoning_effort, # type: ignore
            )
            for key in self.token_usage:
                self.token_usage[key] += usage.get(key, 0)
            reply = strip_thinking(response.content or "")
        except Exception:
            reply = (
                "I've been working on your request but ran into a limit. "
                "Could you please rephrase or simplify your request?"
            )
        finally:
            self.messages.pop()

        self.messages.append({"role": "assistant", "content": reply})
        self._maybe_compress()
        return reply

    def reset(self) -> None:
        """Reset conversation state while keeping the system prompt template."""
        self.messages = [
            {"role": "system", "content": self._render_system_prompt("")},
        ]
        self.turn_id = 0
        self.actions.clear()
        self.policy_violations.clear()
        self.token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self.compressor.token_usage = self.token_usage
        self.long_term_memory.token_usage = self.token_usage
        self.long_term_memory.reset()

    # Internals
    def _render_system_prompt(self, recall_block: str) -> str:
        block = recall_block.strip() if recall_block else _EMPTY_RECALL_NOTE
        return self._system_template.replace(_RECALL_PLACEHOLDER, block)

    def _strip_images_from_last_user_message(self) -> None:
        for msg in reversed(self.messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                msg["content"] = [
                    (
                        part
                        if part.get("type") != "image_url"
                        else {"type": "text", "text": "[image]"}
                    )
                    for part in msg["content"]
                ]
                break

    def _maybe_compress(self) -> None:
        if len(self.messages) <= 1:
            return
        head = self.messages[:1]
        history = self.messages[1:]
        head_tokens = count_message_tokens(self.model, head, tools=self._tools or None)
        compressed = self.compressor.maybe_compress(history, head_tokens)
        if compressed is not history:
            self.messages = head + compressed

    def _handle_tool_call(self, tc: Any) -> None:
        """Invoke a single tool call and append the (possibly truncated) result."""
        func_name = tc.function.name or ""
        try:
            func_args = _json.loads(tc.function.arguments)
        except _json.JSONDecodeError as exc:
            logger.warning(
                "Could not parse arguments for %s: %s - raw: %r",
                func_name,
                exc,
                tc.function.arguments,
            )
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Error: could not parse arguments for {func_name}",
                }
            )
            return

        logger.debug("Tool call: %s(%s)", func_name, func_args)

        try:
            result = self.tool_registry.invoke(func_name, func_args)
        except Exception as exc:
            result = f"Error executing {func_name}: {exc}"

        self.actions.append(Action(name=func_name, arguments=func_args, result=result))

        is_violation = isinstance(result, str) and result.startswith(
            "PolicyViolationError:"
        )
        if is_violation:
            self.policy_violations.append(
                {
                    "tool": func_name,
                    "arguments": func_args,
                    "violation": result,
                }
            )

        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            }
        )

    @staticmethod
    def _build_user_content(message: str, images: Optional[List[str]] = None) -> Any:
        """Build user message content, including image urls if provided."""
        if not images:
            return message

        content: List[Dict[str, Any]] = [{"type": "text", "text": message}]
        for img_url in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": img_url},
                }
            )
        return content

    @staticmethod
    def _load_prompt(path: str, **kwargs: str) -> str:
        text = Path(path).read_text(encoding="utf-8")
        for key, value in kwargs.items():
            text = text.replace(f"{{{key}}}", value)
        return text
