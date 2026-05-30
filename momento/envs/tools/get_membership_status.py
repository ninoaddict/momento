import json
from typing import Any, Dict
from momento.envs.repository import MembershipRepository, UserRepository
from momento.envs.repository.membership_repository import MEMBERSHIP_BENEFITS
from momento.envs.tools.base import Tool


class GetMembershipStatus(Tool):
    @staticmethod
    def invoke(
        user_id: str,
    ) -> str:
        user_repo = UserRepository()
        membership_repo = MembershipRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        active = membership_repo.get_active(user_id)

        if active:
            tier = active["tier"]
            benefits = MEMBERSHIP_BENEFITS.get(tier, {})
            result = {
                "membership_id": str(active["id"]),
                "user_id": active["user_id"],
                "tier": tier,
                "status": active["status"],
                "start_date": active.get("start_date"),
                "end_date": active.get("end_date"),
                "benefits": benefits,
                "created_at": active.get("created_at"),
                "updated_at": active.get("updated_at"),
            }
        else:
            benefits = MEMBERSHIP_BENEFITS["basic"]
            result = {
                "membership_id": None,
                "user_id": user_id,
                "tier": "basic",
                "status": "active",
                "start_date": None,
                "end_date": None,
                "benefits": benefits,
                "created_at": None,
                "updated_at": None,
            }

        return json.dumps(result, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_membership_status",
                "description": (
                    "Check the current membership status for a user. "
                    "Returns the active membership tier, its benefits, and validity dates. "
                    "If no active membership exists, the user is implicitly on the BASIC tier."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID to check membership status for.",
                        },
                    },
                    "required": ["user_id"],
                },
            },
        }
