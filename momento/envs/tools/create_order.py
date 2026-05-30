import json
from typing import Any, Dict, List, Optional
from momento.envs.repository import (
    MembershipRepository,
    MenuItemRepository,
    OrderRepository,
    RestaurantRepository,
    UserRepository,
)
from momento.envs.repository.membership_repository import MEMBERSHIP_BENEFITS
from momento.envs.tools.base import Tool, PolicyViolationError
from momento.utils.utils import is_valid_uuid


class CreateOrder(Tool):
    @staticmethod
    def invoke(
        user_id: str,
        restaurant_id: str,
        items: List[Dict[str, Any]],
        fulfillment: str,
        delivery_provider: Optional[str] = None,
        delivery_address: Optional[str] = None,
        special_instructions: Optional[str] = None,
    ) -> str:
        user_repo = UserRepository()
        restaurant_repo = RestaurantRepository()
        menu_repo = MenuItemRepository()
        order_repo = OrderRepository()
        membership_repo = MembershipRepository()

        if not user_repo.exists(user_id):
            return "Error: user not found"

        if not is_valid_uuid(restaurant_id):
            return f"Error: invalid restaurant_id format '{restaurant_id}' - must be a valid UUID"

        if not restaurant_repo.exists(restaurant_id):
            return "Error: restaurant not found"

        if fulfillment not in ["pickup", "delivery"]:
            raise PolicyViolationError("Fulfillment must be 'pickup' or 'delivery'.")

        if fulfillment == "delivery" and not delivery_provider:
            raise PolicyViolationError(
                "delivery_provider is required for delivery orders."
            )

        if fulfillment == "delivery" and not delivery_address:
            raise PolicyViolationError(
                "delivery_address is required for delivery orders."
            )

        if fulfillment == "delivery":
            valid_providers = [p["id"] for p in order_repo.get_delivery_providers()]
            if delivery_provider not in valid_providers:
                raise PolicyViolationError(
                    f"Invalid delivery provider '{delivery_provider}'. "
                    "Policy requires calling get_delivery_providers and letting the user select a provider. "
                )

        if not items:
            return "Error: at least one item is required"

        order_items: List[Dict[str, Any]] = []
        total_price = 0.0

        for item in items:
            menu_item_id = item.get("menu_item_id")
            quantity = item.get("quantity", 1)

            if not menu_item_id:
                return "Error: each item must have a menu_item_id"

            if not is_valid_uuid(menu_item_id):
                return f"Error: invalid menu_item_id format '{menu_item_id}' - must be a valid UUID"

            if quantity < 1:
                return "Error: item quantity must be at least 1"

            menu_item = menu_repo.get_by_id(menu_item_id)
            if not menu_item:
                return f"Error: menu item {menu_item_id} not found"

            if str(menu_item["restaurant_id"]) != restaurant_id:
                raise PolicyViolationError(
                    f"Menu item {menu_item_id} does not belong to this restaurant. "
                    "All items must be from the same restaurant."
                )

            price = float(menu_item.get("price", 0))
            order_items.append(
                {
                    "menu_item_id": menu_item_id,
                    "name": menu_item["name"],
                    "price": price,
                    "quantity": quantity,
                    "notes": item.get("notes"),
                }
            )
            total_price += price * quantity

        effective_tier = membership_repo.get_effective_tier(user_id)
        benefits = MEMBERSHIP_BENEFITS.get(effective_tier, MEMBERSHIP_BENEFITS["basic"])

        discount_pct = benefits.get("order_discount_pct", 0)
        discount_amount = round(total_price * discount_pct / 100, 2)
        total_price = round(total_price - discount_amount, 2)

        membership_note = None
        if fulfillment == "delivery":
            providers_map = {p["id"]: p for p in order_repo.get_delivery_providers()}
            provider = providers_map.get(delivery_provider, {})
            delivery_price = float(provider.get("delivery_price", 0))

            if benefits.get("free_delivery"):
                membership_note = f"Free delivery applied ({effective_tier} membership)"
            else:
                total_price = round(total_price + delivery_price, 2)

        if discount_pct > 0:
            discount_msg = f"{effective_tier} membership discount: {discount_pct}% (-${discount_amount})"
            if special_instructions:
                special_instructions = f"{special_instructions} | {discount_msg}"
            else:
                special_instructions = discount_msg

        if membership_note:
            if special_instructions:
                special_instructions = f"{special_instructions} | {membership_note}"
            else:
                special_instructions = membership_note

        order = order_repo.create(
            user_id=user_id,
            restaurant_id=restaurant_id,
            items=order_items,
            fulfillment=fulfillment,
            total_price=total_price,
            delivery_provider_name=delivery_provider,
            delivery_address=delivery_address,
            special_instructions=special_instructions,
        )

        if not order:
            return "Error: failed to create order"

        return json.dumps(order, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "create_order",
                "description": ("Create a food order for pickup or delivery. "),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID placing the order.",
                        },
                        "restaurant_id": {
                            "type": "string",
                            "description": "Restaurant ID (UUID format).",
                        },
                        "items": {
                            "type": "array",
                            "description": "List of items to order.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "menu_item_id": {
                                        "type": "string",
                                        "description": "Menu item ID (UUID format).",
                                    },
                                    "quantity": {
                                        "type": "integer",
                                        "description": "Quantity of this item.",
                                        "minimum": 1,
                                        "default": 1,
                                    },
                                    "notes": {
                                        "type": "string",
                                        "description": "Special notes for this item.",
                                    },
                                },
                                "required": ["menu_item_id"],
                            },
                        },
                        "fulfillment": {
                            "type": "string",
                            "description": "Order fulfillment type.",
                            "enum": ["pickup", "delivery"],
                        },
                        "delivery_provider": {
                            "type": "string",
                            "description": "Delivery provider ID (use get_delivery_providers to see options).",
                        },
                        "delivery_address": {
                            "type": "string",
                            "description": "Delivery address (required for delivery orders).",
                        },
                        "special_instructions": {
                            "type": "string",
                            "description": "Special instructions for the order.",
                        },
                    },
                    "required": [
                        "user_id",
                        "restaurant_id",
                        "items",
                        "fulfillment",
                    ],
                },
            },
        }
