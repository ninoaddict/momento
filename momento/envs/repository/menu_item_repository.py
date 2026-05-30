from typing import Any, Dict, List, Optional
from momento.envs.repository.base import BaseRepository


class MenuItemRepository(BaseRepository):
    def get_by_id(self, menu_item_id: str) -> Optional[Dict[str, Any]]:
        """Get menu item by ID."""
        return self._fetch_one(
            "SELECT * FROM menu_items WHERE id = %s", (menu_item_id,)
        )

    def exists(self, menu_item_id: str) -> bool:
        """Check if menu item exists."""
        result = self._fetch_one(
            "SELECT 1 FROM menu_items WHERE id = %s", (menu_item_id,)
        )
        return result is not None

    def list_by_restaurant(self, restaurant_id: str) -> List[Dict[str, Any]]:
        """List all menu items for a restaurant."""
        return self._fetch_all(
            "SELECT * FROM menu_items WHERE restaurant_id = %s ORDER BY name",
            (restaurant_id,),
        )

    def find(
        self,
        name: Optional[str] = None,
        categories: Optional[List[str]] = None,
        cuisines: Optional[List[str]] = None,
        restaurant_ids: Optional[List[str]] = None,
        image_labels: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters = []
        params: List[Any] = []

        if restaurant_ids:
            filters.append("restaurant_id = ANY(%s::uuid[])")
            params.append(restaurant_ids)
        if name:
            filters.append("name ILIKE %s")
            params.append(f"%{name}%")
        if categories:
            filters.append("categories && %s")
            params.append(categories)
        if cuisines:
            filters.append("cuisines && %s")
            params.append(cuisines)

        # image labels search across name, description, categories, cuisines
        if image_labels:
            label_filters = []
            for label in image_labels:
                label_filters.append("name ILIKE %s")
                params.append(f"%{label}%")
                label_filters.append("description ILIKE %s")
                params.append(f"%{label}%")
            label_filters.append("categories && %s")
            params.append(image_labels)
            label_filters.append("cuisines && %s")
            params.append(image_labels)
            filters.append("(" + " OR ".join(label_filters) + ")")

        where_clause = " WHERE " + " AND ".join(filters) if filters else ""
        query = f"SELECT * FROM menu_items{where_clause}"
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        return self._fetch_all(query, tuple(params))

    def get_unique_cuisines(self) -> List[str]:
        """Get all unique cuisines from all menu items."""
        results = self._fetch_all(
            "SELECT DISTINCT unnest(cuisines) AS cuisine FROM menu_items WHERE cuisines IS NOT NULL ORDER BY cuisine"
        )
        return [row["cuisine"] for row in results if row["cuisine"]]

    def get_unique_categories(self) -> List[str]:
        """Get all unique categories from all menu items."""
        results = self._fetch_all(
            "SELECT DISTINCT unnest(categories) AS category FROM menu_items WHERE categories IS NOT NULL ORDER BY category"
        )
        return [row["category"] for row in results if row["category"]]
