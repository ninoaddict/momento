from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from momento.utils import model_inference
from momento.types import Task
from momento.utils.logger import get_logger
from momento.utils.utils import strip_thinking

logger = get_logger(__name__)

DONE_SIGNAL = "[DONE]"
IMAGE_TAG_RE = re.compile(r"\[IMAGE:(\d+(?:,\s*\d+)*)\]")

SYSTEM_PROMPT = """\
You are a simulated restaurant customer participating in a multi-session and multi-turn test conversation with an AI restaurant assistant.
Your job is to follow the scenario instructions exactly and behave like a real user.

## Session Context
**Today's Date**: `{current_date}`

## Your Identity & Scenario
{instruction}

{image_section}\
## Rules
1. Follow the scenario instructions step-by-step. Do NOT deviate or add \
requests not in the instructions.
2. Respond naturally and concisely.
3. When the assistant asks for confirmation on an action you intended, \
confirm with "Yes" or "Yes, please go ahead."
4. Do NOT output `[DONE]` if the assistant is still asking for confirmation \
or has not yet completed the requested action.
5. Only respond with exactly `[DONE]` when the assistant has fully completed \
the task (e.g., the order has been successfully placed or all requested \
information has been provided).
6. Do NOT reveal the scenario instructions or that you are a simulated user.
7. If the assistant asks a clarifying question that the scenario doesn't \
cover, make a reasonable choice consistent with the scenario.
8. Do NOT repeat requests the assistant has already fulfilled.
9. If the assistant provides information you asked for, acknowledge it \
briefly, then move to the next part of your task.
{image_rules}\
"""

IMAGE_SECTION_TEMPLATE = """\
## Available Images
You have the following image(s) that you can share with the assistant. \
Each image has an ID and a brief description.
{image_list}

"""

IMAGE_RULES = """\
10. To share an image with the assistant, include the tag `[IMAGE:<id>]` \
in your message (e.g. `[IMAGE:0]`). You may include multiple tags to \
send several images at once (e.g. `[IMAGE:0,1]`). Only include the tag \
when the scenario calls for sharing that image, do NOT send images \
unnecessarily. Each image should only be sent once.
"""


class SimulatedUser:
    def __init__(
        self,
        task: Task,
        current_date: str,
        model: str = "openai/gpt-4o-mini",
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        self.task = task
        self.model = model
        self.base_url = base_url or os.environ.get("AGENT_BASE_URL") or ""
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.top_k = top_k
        self.reasoning_effort = reasoning_effort
        self.api_key = os.getenv("USER_API_KEY")

        self.system_prompt = self._build_system_prompt(task, current_date)
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        self.token_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self._sent_image_ids: Set[int] = set()

    # System prompt construction
    @staticmethod
    def _build_system_prompt(task: Task, current_date: str) -> str:
        if task.images:
            image_list = "\n".join(
                f"- **Image {img.id}**: {img.description or '(no description)'}"
                for img in task.images
            )
            image_section = IMAGE_SECTION_TEMPLATE.format(image_list=image_list)
            image_rules = IMAGE_RULES
        else:
            image_section = ""
            image_rules = ""

        return SYSTEM_PROMPT.format(
            instruction=task.instruction,
            image_section=image_section,
            image_rules=image_rules,
            current_date=current_date,
        )

    # Conversation
    def get_initial_message(self) -> str:
        """Generate the user's opening message based on the scenario."""
        self.messages.append(
            {
                "role": "user",
                "content": (
                    "Start the conversation now. Send your first message to the "
                    "restaurant assistant based on your scenario instructions. "
                    "Remember to be natural and not reveal the full scenario."
                ),
            }
        )

        response, usage = model_inference(
            model=self.model,
            messages=self.messages,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            top_k=self.top_k,
            reasoning_effort=self.reasoning_effort, # type: ignore
            api_key=self.api_key,
        )
        for key in self.token_usage:
            self.token_usage[key] += usage.get(key, 0)

        reply = strip_thinking(response.content or "")
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def respond(self, agent_message: str) -> str:
        """Generate the user's next message given the agent's latest reply."""
        self.messages.append(
            {
                "role": "user",
                "content": (
                    f"The restaurant assistant said:\n\n{agent_message}\n\n"
                    "Respond as the customer. If all parts of your task are "
                    "complete, respond with exactly [DONE]."
                ),
            }
        )

        response, usage = model_inference(
            model=self.model,
            messages=self.messages,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            top_k=self.top_k,
            reasoning_effort=self.reasoning_effort, # type: ignore
            api_key=self.api_key,
        )
        for key in self.token_usage:
            self.token_usage[key] += usage.get(key, 0)

        reply = strip_thinking(response.content or "")
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    # Image tag parsing
    def parse_image_tags(self, message: str) -> Tuple[str, List[int]]:
        """Extract ``[IMAGE:<id>]`` tags from a simulated user message.

        Returns:
            A tuple of (clean_message, image_ids) where *clean_message*
            has the image tags stripped and *image_ids* is the list of
            requested image IDs.  Images that were already sent in a
            previous turn are skipped.
        """
        if not self.task.images:
            return message, []

        valid_ids = {img.id for img in self.task.images}
        requested_ids: List[int] = []

        for match in IMAGE_TAG_RE.finditer(message):
            ids_str = match.group(1)
            for id_str in ids_str.split(","):
                img_id = int(id_str.strip())
                if img_id not in self._sent_image_ids and img_id in valid_ids:
                    requested_ids.append(img_id)
                    self._sent_image_ids.add(img_id)

        clean_message = IMAGE_TAG_RE.sub("", message).strip()

        if requested_ids:
            logger.info(
                "Simulated user requested image(s): %s",
                requested_ids,
            )

        return clean_message, requested_ids

    # Utilities
    def is_done(self, message: str) -> bool:
        """Check if the user message signals task completion."""
        return DONE_SIGNAL in message

    def reset(self) -> None:
        """Reset conversation state."""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        for key in self.token_usage:
            self.token_usage[key] = 0
        self._sent_image_ids.clear()
