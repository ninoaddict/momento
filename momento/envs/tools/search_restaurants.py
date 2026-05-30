import json
from typing import Any, Dict, List, Optional
from momento.envs.repository import RestaurantRepository
from momento.envs.tools.base import PolicyViolationError, Tool
from momento.utils.utils import is_valid_uuid


def _compact_restaurant(record: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "id": str(record.get("id")),
        "name": record.get("name"),
        "address": record.get("address"),
        "city": record.get("city"),
        "country": record.get("country"),
        "cuisines": record.get("cuisines", []),
        "price_range_lower": record.get("price_range_lower"),
        "price_range_upper": record.get("price_range_upper"),
        "amenities": record.get("amenities", []),
        "opening_hours": record.get("opening_hours"),
        "capacity": record.get("capacity"),
        "image_url": record.get("image_url", []),
        "description": record.get("description"),
    }
    if "distance_km" in record:
        result["distance_km"] = round(float(record["distance_km"]), 2)
    return result


class SearchRestaurants(Tool):
    @staticmethod
    def invoke(
        name: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        cuisines: Optional[List[str]] = None,
        amenities: Optional[List[str]] = None,
        restaurant_ids: Optional[List[str]] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> str:
        if name is None and city is None and country is None and cuisines is None and amenities is None and restaurant_ids is None and min_price is None and max_price is None and latitude is None and longitude is None and radius_km is None:
            raise PolicyViolationError("At least one search criterion must be provided.")

        if restaurant_ids:
            for rid in restaurant_ids:
                if not is_valid_uuid(rid):
                    return f"Error: invalid restaurant_id format '{rid}'- must be a valid UUID"

        restaurant_repo = RestaurantRepository()
        if latitude is not None and longitude is not None and radius_km is not None:
            results = restaurant_repo.find_by_geo(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                name=name,
                city=city,
                country=country,
                cuisines=cuisines,
                amenities=amenities,
                restaurant_ids=restaurant_ids,
                min_price=min_price,
                max_price=max_price,
                limit=limit,
            )
        else:
            results = restaurant_repo.find(
                name=name,
                city=city,
                country=country,
                cuisines=cuisines,
                amenities=amenities,
                restaurant_ids=restaurant_ids,
                min_price=min_price,
                max_price=max_price,
                limit=limit,
            )

        return json.dumps([_compact_restaurant(r) for r in results], default=str)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_restaurants",
                "description": (
                    "Search restaurants by various criteria including name, location, cuisine, amenities, "
                    "price range, and geographic coordinates. When latitude, longitude, and radius_km are "
                    "provided, returns restaurants within the specified radius sorted by distance."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Restaurant name or partial name to match (case-insensitive).",
                        },
                        "city": {
                            "type": "string",
                            "description": "City name to filter by (case-insensitive).",
                        },
                        "country": {
                            "type": "string",
                            "description": "Country name to filter by (case-insensitive).",
                        },
                        "cuisines": {
                            "type": "array",
                            "description": "Cuisine types to match (any matching cuisine), the string must be in lowercase.",
                            "items": {"type": "string"},
                        },
                        "amenities": {
                            "type": "array",
                            "description": "Required amenities (must all be present), the string must be in lowercase.",
                            "items": {"type": "string"},
                        },
                        "restaurant_ids": {
                            "type": "array",
                            "description": "Filter by specific restaurant IDs.",
                            "items": {"type": "string"},
                        },
                        "min_price": {
                            "type": "integer",
                            "description": "Minimum price range lower bound.",
                        },
                        "max_price": {
                            "type": "integer",
                            "description": "Maximum price range upper bound.",
                        },
                        "latitude": {
                            "type": "number",
                            "description": "Latitude for geographic search (requires longitude and radius_km).",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude for geographic search (requires latitude and radius_km).",
                        },
                        "radius_km": {
                            "type": "number",
                            "description": "Search radius in kilometers (requires latitude and longitude).",
                            "minimum": 0.1,
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
