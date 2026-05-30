import json
from typing import Any, Dict
from momento.envs.repository import MenuItemRepository, RestaurantRepository
from momento.envs.tools.base import Tool
from momento.utils.utils import is_valid_uuid


class GetRestaurantDetails(Tool):
    @staticmethod
    def invoke(
        restaurant_id: str
    ) -> str:
        if not is_valid_uuid(restaurant_id):
            return f"Error: invalid restaurant_id format '{restaurant_id}' - must be a valid UUID"

        restaurant_repo = RestaurantRepository()
        menu_repo = MenuItemRepository()

        restaurant = restaurant_repo.get_by_id(restaurant_id)
        if not restaurant:
            return "Error: restaurant not found"

        result = {
            "id": str(restaurant["id"]),
            "name": restaurant.get("name"),
            "description": restaurant.get("description"),
            "address": restaurant.get("address"),
            "city": restaurant.get("city"),
            "country": restaurant.get("country"),
            "lat": restaurant.get("lat"),
            "lon": restaurant.get("lon"),
            "cuisines": restaurant.get("cuisines", []),
            "price_range_lower": restaurant.get("price_range_lower"),
            "price_range_upper": restaurant.get("price_range_upper"),
            "opening_hours": restaurant.get("opening_hours"),
            "capacity": restaurant.get("capacity"),
            "amenities": restaurant.get("amenities", []),
            "image_url": restaurant.get("image_url", []),
        }

        return json.dumps(result, default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_restaurant_details",
                "description": "Get detailed information about a restaurant.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "restaurant_id": {
                            "type": "string",
                            "description": "Restaurant ID (UUID format).",
                        },
                    },
                    "required": ["restaurant_id"],
                },
            },
        }
