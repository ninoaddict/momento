import json
from typing import Any, Dict, List, Optional, Union
from momento.envs.repository import MenuItemRepository
from momento.envs.tools.base import PolicyViolationError, Tool
from momento.utils.utils import is_valid_uuid


def _compact_menu_item(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(record.get("id")),
        "restaurant_id": str(record.get("restaurant_id")),
        "name": record.get("name"),
        "description": record.get("description"),
        "categories": record.get("categories", []),
        "cuisines": record.get("cuisines", []),
        "price": float(record.get("price", 0)) if record.get("price") else None,
        "image_url": record.get("image_url", []),
    }


def _parse_image_labels(image_labels: Optional[Union[List[str], str]]) -> List[str]:
    if not image_labels:
        return []
    if isinstance(image_labels, list):
        return [str(item) for item in image_labels]
    return [str(image_labels)]


class QueryMenuItems(Tool):
    @staticmethod
    def invoke(
        name: Optional[str] = None,
        categories: Optional[List[str]] = None,
        cuisines: Optional[List[str]] = None,
        restaurant_ids: Optional[List[str]] = None,
        image_labels: Optional[Union[List[str], str]] = None,
        limit: Optional[int] = None,
    ) -> str:
        if name is None and categories is None and cuisines is None and restaurant_ids is None and image_labels is None:
            raise PolicyViolationError("At least one search criterion must be provided")

        if restaurant_ids:
            for rid in restaurant_ids:
                if not is_valid_uuid(rid):
                    return f"Error: invalid restaurant_id format '{rid}' - must be a valid UUID"

        menu_repo = MenuItemRepository()

        labels = _parse_image_labels(image_labels)
        results = menu_repo.find(
            name=name,
            categories=categories,
            cuisines=cuisines,
            restaurant_ids=restaurant_ids,
            image_labels=labels if labels else None,
            limit=limit,
        )

        return json.dumps([_compact_menu_item(r) for r in results], default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "query_menu_items",
                "description": (
                    "Query menu items by name, category, cuisine, restaurant, or image-derived labels."
                    "Image labels are extracted from food images and can be used to find similar menu items."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Menu item name or partial name to match (case-insensitive).",
                        },
                        "categories": {
                            "type": "array",
                            "description": "Categories to match (e.g., 'appetizer', 'main course', 'dessert'), the string must be in lowercase.",
                            "items": {"type": "string"},
                        },
                        "cuisines": {
                            "type": "array",
                            "description": "Cuisine types to match (e.g., 'Italian', 'Japanese'), the string must be in lowercase.",
                            "items": {"type": "string"},
                        },
                        "restaurant_ids": {
                            "type": "array",
                            "description": "Filter by specific restaurant IDs.",
                            "items": {"type": "string"},
                        },
                        "image_labels": {
                            "type": ["array", "string"],
                            "description": (
                                "Image-derived labels or keywords from food images. "
                                "Can be a list of labels or a descriptive text string."
                            ),
                            "items": {"type": "string"},
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return.",
                            "minimum": 1,
                        },
                    },
                },
            },
        }
