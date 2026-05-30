import json
from typing import Any, Dict
from momento.envs.repository.membership_repository import (
    MEMBERSHIP_BENEFITS,
    VALID_TIERS,
)
from momento.envs.tools.base import Tool


class GetMembershipBenefits(Tool):
    @staticmethod
    def invoke(
        tier: str,
    ) -> str:
        tier = tier.lower()
        if tier not in VALID_TIERS:
            return f"Error: invalid tier. Valid options: {', '.join(VALID_TIERS)}"

        benefits = MEMBERSHIP_BENEFITS[tier]
        return json.dumps(benefits, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_membership_benefits",
                "description": (
                    "Get the benefits associated with a membership tier. "
                    "Returns discount percentages, delivery perks, reservation bonuses, and monthly cost."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tier": {
                            "type": "string",
                            "description": "Membership tier to get benefits for.",
                            "enum": ["basic", "silver", "gold", "platinum"],
                        },
                    },
                    "required": ["tier"],
                },
            },
        }
