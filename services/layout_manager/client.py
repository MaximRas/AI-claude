"""Клиент layout-manager. Пути — как в specs/layout-manager.json."""

from __future__ import annotations

from framework.http_client import ApiResponse
from framework.routing import LAYOUT_MANAGER
from services.base import ServiceClient, drop_none


class LayoutManagerClient(ServiceClient):
    SERVICE = LAYOUT_MANAGER

    # --- general ---
    def health(self) -> ApiResponse:
        return self.request("GET", "/private/health", auth=False)

    def version(self) -> ApiResponse:
        return self.request("GET", "/public/version", auth=False)

    def detailing(self, timestamp_start: int, timestamp_end: int) -> ApiResponse:
        return self.request("GET", "/public/detailing", params={"timestamp_start": timestamp_start, "timestamp_end": timestamp_end})

    # --- widgets ---
    def create_widget(self, payload: dict) -> ApiResponse:
        return self.request("POST", "/public/v4/widgets", json_body=payload)

    def get_widget(self, widget_id: str) -> ApiResponse:
        return self.request("GET", "/public/v4/widgets/{widget_id}", path_params={"widget_id": widget_id})

    def edit_widget(self, widget_id: str, payload: dict) -> ApiResponse:
        return self.request("PATCH", "/public/v4/widgets/{widget_id}", path_params={"widget_id": widget_id}, json_body=payload)

    def delete_widget(self, widget_id: str) -> ApiResponse:
        return self.request("DELETE", "/public/v4/widgets/{widget_id}", path_params={"widget_id": widget_id})

    def copy_widget(self, widget_id: str, payload: dict | None = None) -> ApiResponse:
        return self.request("POST", "/public/v4/widgets/{widget_id}/copy", path_params={"widget_id": widget_id}, json_body=payload or {})

    def list_widgets(
        self, pgoffset: int = 0, pgsize: int = 10, scope: str | None = None, role: list[str] | None = None, embedded: bool | None = None
    ) -> ApiResponse:
        filters = drop_none({"scope": scope, "role": role, "embedded": embedded})
        return self.request("POST", "/public/v4/widgets/list", json_body={"pagination": {"pgoffset": pgoffset, "pgsize": pgsize}, "filters": filters})

    # --- layouts ---
    def create_layout(self, payload: dict) -> ApiResponse:
        return self.request("POST", "/public/v4/layouts", json_body=payload)

    def get_layout(self, layout_id: str) -> ApiResponse:
        return self.request("GET", "/public/v4/layouts/{layout_id}", path_params={"layout_id": layout_id})

    def modify_layout(self, layout_id: str, payload: dict) -> ApiResponse:
        return self.request("PATCH", "/public/v4/layouts/{layout_id}", path_params={"layout_id": layout_id}, json_body=payload)

    def modify_layouts(self, layouts: list[dict]) -> ApiResponse:
        return self.request("PATCH", "/public/v4/layouts", json_body={"layouts": layouts})

    def delete_layout(self, layout_id: str) -> ApiResponse:
        return self.request("DELETE", "/public/v4/layouts/{layout_id}", path_params={"layout_id": layout_id})

    def layout_widgets(self, layout_id: str) -> ApiResponse:
        return self.request("GET", "/public/v4/layouts/{layout_id}/widgets", path_params={"layout_id": layout_id})

    def copy_layout(self, layout_id: str, payload: dict) -> ApiResponse:
        return self.request("POST", "/public/v4/layouts/{layout_id}/copy", path_params={"layout_id": layout_id}, json_body=payload)

    def list_layouts(self, pgoffset: int = 0, pgsize: int = 10, scope: str | None = None, role: list[str] | None = None) -> ApiResponse:
        filters = drop_none({"scope": scope, "role": role})
        return self.request("POST", "/public/v4/layouts/list", json_body={"pagination": {"pgoffset": pgoffset, "pgsize": pgsize}, "filters": filters})

    # --- access (widgets / layouts) ---
    def _access_path(self, kind: str, suffix: str = "") -> str:
        assert kind in ("widgets", "layouts")
        param = "widget_id" if kind == "widgets" else "layout_id"
        return f"/public/v4/{kind}/{{{param}}}/access{suffix}"

    def _id_param(self, kind: str, entity_id: str) -> dict:
        return {"widget_id" if kind == "widgets" else "layout_id": entity_id}

    def get_access(self, kind: str, entity_id: str) -> ApiResponse:
        return self.request("GET", self._access_path(kind), path_params=self._id_param(kind, entity_id))

    def grant_access(self, kind: str, entity_id: str, scope: str, role: str, user_id: str | None = None) -> ApiResponse:
        return self.request(
            "POST",
            self._access_path(kind),
            path_params=self._id_param(kind, entity_id),
            json_body=drop_none({"scope": scope, "role": role, "user_id": user_id}),
        )

    def revoke_all_access(self, kind: str, entity_id: str, mode: str | None = None) -> ApiResponse:
        return self.request("DELETE", self._access_path(kind), path_params=self._id_param(kind, entity_id), params=drop_none({"mode": mode}))

    def patch_access(self, kind: str, entity_id: str, entry_id: int, role: str) -> ApiResponse:
        return self.request(
            "PATCH",
            self._access_path(kind, "/{entry_id}"),
            path_params={**self._id_param(kind, entity_id), "entry_id": entry_id},
            json_body={"role": role},
        )

    def revoke_access(self, kind: str, entity_id: str, entry_id: int) -> ApiResponse:
        return self.request(
            "DELETE",
            self._access_path(kind, "/{entry_id}"),
            path_params={**self._id_param(kind, entity_id), "entry_id": entry_id},
        )
