import json
from typing import Any, Dict
from momento.envs.repository import MembershipRepository, UserRepository
from momento.envs.repository.membership_repository import VALID_TIERS
from momento.envs.tools.base import Tool, PolicyViolationError


class ApplyMembership(Tool):
    @staticmethod
    def invoke(
        user_id: str,
        tier: str,
        start_date: str,
        end_date: str,
    ) -> str:
        user_repo = UserRepository()
        membership_repo = MembershipRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        tier = tier.lower()
        if tier not in VALID_TIERS:
            raise PolicyViolationError(f"Invalid tier '{tier}'. Valid tiers are: {', '.join(VALID_TIERS)}")

        if tier == "basic":
            raise PolicyViolationError(
                "BASIC is the implicit default tier and cannot be applied explicitly."
            )

        # at most one ACTIVE non-BASIC membership per user
        existing = membership_repo.get_active(user_id)
        if existing:
            raise PolicyViolationError(
                f"User already has an active '{existing['tier']}' membership "
                f"(id: {existing['id']}). Cancel or let it expire before applying a new one."
            )

        membership = membership_repo.apply(
            user_id=user_id,
            tier=tier,
            start_date=start_date,
            end_date=end_date,
        )

        if not membership:
            return "Error: failed to apply membership"

        return json.dumps(membership, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "apply_membership",
                "description": (
                    "Apply a new membership tier for a user. "
                    "Valid tiers are silver, gold, and platinum. "
                    "A user can have at most one active non-basic membership. "
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID to apply the membership for.",
                        },
                        "tier": {
                            "type": "string",
                            "description": "Membership tier to apply.",
                            "enum": ["silver", "gold", "platinum"],
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Membership start date in YYYY-MM-DD format.",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Membership end date in YYYY-MM-DD format. Required for all non-basic tiers.",
                        },
                    },
                    "required": ["user_id", "tier", "start_date", "end_date"],
                },
            },
        }
