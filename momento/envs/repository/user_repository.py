from typing import Any, Dict, List, Optional
from momento.envs.repository.base import BaseRepository


class UserRepository(BaseRepository):
    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        return self._fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        return self._fetch_one("SELECT * FROM users WHERE email = %s", (email,))

    def exists(self, user_id: str) -> bool:
        """Check if user exists."""
        result = self._fetch_one("SELECT 1 FROM users WHERE id = %s", (user_id,))
        return result is not None

    def get_payment_methods(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all payment methods for a user."""
        return self._fetch_all(
            "SELECT * FROM payment_methods WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )

    def get_payment_method(
        self, user_id: str, payment_method_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific payment method for a user."""
        return self._fetch_one(
            "SELECT * FROM payment_methods WHERE id = %s AND user_id = %s",
            (payment_method_id, user_id),
        )
