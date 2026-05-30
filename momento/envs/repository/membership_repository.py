from __future__ import annotations

from typing import Any, Dict, List, Optional
from momento.envs.repository.base import BaseRepository, get_scenario_date

MEMBERSHIP_BENEFITS: Dict[str, Dict[str, Any]] = {
    "basic": {
        "tier": "basic",
        "order_discount_pct": 0,
        "priority_reservation": False,
        "free_delivery": False,
        "monthly_cost": 0.00,
        "description": "Default tier. No additional perks.",
    },
    "silver": {
        "tier": "silver",
        "order_discount_pct": 5,
        "priority_reservation": False,
        "free_delivery": False,
        "monthly_cost": 9.99,
        "description": "5% discount on orders.",
    },
    "gold": {
        "tier": "gold",
        "order_discount_pct": 10,
        "priority_reservation": True,
        "free_delivery": False,
        "monthly_cost": 19.99,
        "description": "10% discount on orders, priority reservation.",
    },
    "platinum": {
        "tier": "platinum",
        "order_discount_pct": 15,
        "priority_reservation": True,
        "free_delivery": True,
        "monthly_cost": 29.99,
        "description": "15% discount on orders, free delivery, priority reservation.",
    },
}

VALID_TIERS = list(MEMBERSHIP_BENEFITS.keys())


class MembershipRepository(BaseRepository):
    def _auto_expire(self, user_id: str) -> None:
        self._execute(
            """
            UPDATE memberships
            SET status = 'expired', updated_at = now()
            WHERE user_id = %s
              AND status = 'active'
              AND end_date IS NOT NULL
              AND end_date < %s::date
            """,
            (user_id, get_scenario_date()),
        )

    def get_active(self, user_id: str) -> Optional[Dict[str, Any]]:
        self._auto_expire(user_id)
        return self._fetch_one(
            """
            SELECT * FROM memberships
            WHERE user_id = %s AND status = 'active' AND tier <> 'basic'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )

    def get_effective_tier(self, user_id: str) -> str:
        membership = self.get_active(user_id)
        if membership:
            return membership["tier"]
        return "basic"

    def get_by_id(self, membership_id: str) -> Optional[Dict[str, Any]]:
        return self._fetch_one(
            "SELECT * FROM memberships WHERE id = %s",
            (membership_id,),
        )

    def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        self._auto_expire(user_id)
        return self._fetch_all(
            "SELECT * FROM memberships WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )

    def apply(
        self,
        user_id: str,
        tier: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._execute_returning(
            """
            INSERT INTO memberships (user_id, tier, status, start_date, end_date)
            VALUES (%s, %s, 'active', %s, %s)
            RETURNING *
            """,
            (user_id, tier, start_date, end_date),
        )

    def cancel_active(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Cancel the active non-basic membership for a user."""
        return self._execute_returning(
            """
            UPDATE memberships
            SET status = 'cancelled', updated_at = now()
            WHERE user_id = %s AND status = 'active' AND tier <> 'basic'
            RETURNING *
            """,
            (user_id,),
        )

    def renew_active(self, user_id: str, new_end_date: str) -> Optional[Dict[str, Any]]:
        """Extend the end date of the active non-basic membership for a user."""
        return self._execute_returning(
            """
            UPDATE memberships
            SET end_date = %s, updated_at = now()
            WHERE user_id = %s AND status = 'active' AND tier <> 'basic'
            RETURNING *
            """,
            (new_end_date, user_id),
        )

    @staticmethod
    def get_benefits(tier: str) -> Optional[Dict[str, Any]]:
        return MEMBERSHIP_BENEFITS.get(tier)
