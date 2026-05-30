from typing import Any, Dict, List, Optional
from momento.envs.repository.base import BaseRepository, get_connection

DELIVERY_PROVIDERS = [
    {
        "id": "swiftdrop",
        "name": "SwiftDrop",
        "description": "Fast and reliable delivery service",
        "delivery_price": 3.99,
    },
    {
        "id": "foodfly",
        "name": "FoodFly",
        "description": "Premium food delivery with temperature control",
        "delivery_price": 5.99,
    },
    {
        "id": "quickdish",
        "name": "QuickDish",
        "description": "Budget-friendly delivery option",
        "delivery_price": 1.99,
    },
    {
        "id": "mealdash",
        "name": "MealDash",
        "description": "Express delivery for urgent orders",
        "delivery_price": 4.99,
    },
    {
        "id": "carryeats",
        "name": "CarryEats",
        "description": "Eco-friendly delivery service",
        "delivery_price": 2.99,
    },
]


class OrderRepository(BaseRepository):
    def get_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order by ID with items."""
        order = self._fetch_one("SELECT * FROM orders WHERE id = %s", (order_id,))
        if order:
            order["items"] = self._fetch_all(
                "SELECT * FROM order_items WHERE order_id = %s", (order_id,)
            )
        return order

    def get_for_user(self, order_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get order only if it belongs to the specified user."""
        order = self._fetch_one(
            "SELECT * FROM orders WHERE id = %s AND user_id = %s",
            (order_id, user_id),
        )
        if order:
            order["items"] = self._fetch_all(
                "SELECT * FROM order_items WHERE order_id = %s", (order_id,)
            )
        return order

    def list_by_user(
        self, user_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all orders for a user, optionally filtered by status."""
        if status:
            orders = self._fetch_all(
                "SELECT * FROM orders WHERE user_id = %s AND status = %s ORDER BY created_at DESC",
                (user_id, status),
            )
        else:
            orders = self._fetch_all(
                "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
        for order in orders:
            order["items"] = self._fetch_all(
                "SELECT * FROM order_items WHERE order_id = %s", (str(order["id"]),)
            )
        return orders

    def create(
        self,
        user_id: str,
        restaurant_id: str,
        items: List[Dict[str, Any]],
        fulfillment: str,
        total_price: float,
        delivery_provider_name: Optional[str] = None,
        delivery_address: Optional[str] = None,
        special_instructions: Optional[str] = None,
        currency: str = "USD",
    ) -> Optional[Dict[str, Any]]:
        """Create a new order with items."""
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO orders (
                        user_id, restaurant_id, fulfillment, status,
                        total_price, currency, delivery_provider_name,
                        delivery_address, special_instructions
                    ) VALUES (%s, %s, %s, 'created', %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        user_id,
                        restaurant_id,
                        fulfillment,
                        total_price,
                        currency,
                        delivery_provider_name,
                        delivery_address,
                        special_instructions,
                    ),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                order = dict(row)
                order_id = str(order["id"])

                # Create order items
                order_items = []
                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO order_items (
                            order_id, menu_item_id, name, price, quantity, notes
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            order_id,
                            item.get("menu_item_id"),
                            item["name"],
                            item["price"],
                            item["quantity"],
                            item.get("notes"),
                        ),
                    )
                    item_row = cursor.fetchone()
                    if item_row:
                        order_items.append(dict(item_row))

                conn.commit()
                order["items"] = order_items
                return order

    def update_status(self, order_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update order status."""
        return self._execute_returning(
            """
            UPDATE orders
            SET status = %s, updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (status, order_id),
        )

    def cancel(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Cancel an order."""
        return self.update_status(order_id, "cancelled")

    def get_delivery_providers(self) -> List[Dict[str, Any]]:
        """Get available delivery providers."""
        return DELIVERY_PROVIDERS

    def is_cancellable(self, order: Dict[str, Any]) -> bool:
        """Check if an order can be cancelled."""
        # Only orders in created or confirmed status can be cancelled
        cancellable_statuses = ["created", "confirmed"]
        return order.get("status") in cancellable_statuses
