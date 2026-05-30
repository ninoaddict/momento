from typing import Any, Dict, List, Optional
from momento.envs.repository.base import BaseRepository


class RestaurantRepository(BaseRepository):
    def get_by_id(self, restaurant_id: str) -> Optional[Dict[str, Any]]:
        """Get restaurant by ID."""
        return self._fetch_one(
            "SELECT * FROM restaurants WHERE id = %s", (restaurant_id,)
        )

    def exists(self, restaurant_id: str) -> bool:
        """Check if restaurant exists."""
        result = self._fetch_one(
            "SELECT 1 FROM restaurants WHERE id = %s", (restaurant_id,)
        )
        return result is not None

    def find(
        self,
        name: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        cuisines: Optional[List[str]] = None,
        amenities: Optional[List[str]] = None,
        restaurant_ids: Optional[List[str]] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find restaurants matching the given criteria."""
        filters = []
        params: List[Any] = []

        if restaurant_ids:
            filters.append("id = ANY(%s)")
            params.append(restaurant_ids)
        if name:
            filters.append("name ILIKE %s")
            params.append(f"%{name}%")
        if city:
            filters.append("city ILIKE %s")
            params.append(f"%{city}%")
        if country:
            filters.append("country ILIKE %s")
            params.append(f"%{country}%")
        if cuisines:
            filters.append("cuisines && %s")
            params.append(cuisines)
        if amenities:
            filters.append("amenities @> %s")
            params.append(amenities)
        if min_price is not None:
            filters.append("price_range_lower >= %s")
            params.append(min_price)
        if max_price is not None:
            filters.append("price_range_upper <= %s")
            params.append(max_price)

        where_clause = " WHERE " + " AND ".join(filters) if filters else ""
        query = f"SELECT * FROM restaurants{where_clause}"
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        return self._fetch_all(query, tuple(params))

    def find_by_geo(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        name: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        cuisines: Optional[List[str]] = None,
        amenities: Optional[List[str]] = None,
        restaurant_ids: Optional[List[str]] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find restaurants within a geographic radius."""
        params: List[Any] = [latitude, longitude, latitude]

        # haversine formula for distance in km
        distance_expr = (
            "6371 * acos("
            "cos(radians(%s)) * cos(radians(lat)) * cos(radians(lon) - radians(%s)) "
            "+ sin(radians(%s)) * sin(radians(lat))"
            ")"
        )

        query = (
            "SELECT * FROM ("
            "SELECT *, "
            + distance_expr
            + " AS distance_km FROM restaurants WHERE lat IS NOT NULL AND lon IS NOT NULL"
            ") AS r"
        )

        filters = ["distance_km <= %s"]
        params.append(radius_km)

        if restaurant_ids:
            filters.append("id = ANY(%s)")
            params.append(restaurant_ids)
        if name:
            filters.append("name ILIKE %s")
            params.append(f"%{name}%")
        if city:
            filters.append("city ILIKE %s")
            params.append(f"%{city}%")
        if country:
            filters.append("country ILIKE %s")
            params.append(f"%{country}%")
        if cuisines:
            filters.append("cuisines && %s")
            params.append(cuisines)
        if amenities:
            filters.append("amenities @> %s")
            params.append(amenities)
        if min_price is not None:
            filters.append("price_range_lower >= %s")
            params.append(min_price)
        if max_price is not None:
            filters.append("price_range_upper <= %s")
            params.append(max_price)

        query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY distance_km ASC"
        if limit:
            query += " LIMIT %s"
            params.append(limit)

        return self._fetch_all(query, tuple(params))

    def get_capacity(self, restaurant_id: str) -> int:
        """Get restaurant capacity."""
        result = self._fetch_one(
            "SELECT capacity FROM restaurants WHERE id = %s", (restaurant_id,)
        )
        return int(result.get("capacity", 0)) if result else 0

    def get_opening_hours(self, restaurant_id: str) -> Optional[Dict[str, Any]]:
        """Get restaurant opening hours."""
        result = self._fetch_one(
            "SELECT opening_hours FROM restaurants WHERE id = %s", (restaurant_id,)
        )
        return result.get("opening_hours") if result else None
