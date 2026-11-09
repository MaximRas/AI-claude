"""Клиенты сервиса object-manager.

Один сервис (specs/object-manager.json) обслуживает несколько доменов:
object-manager, device-manager, watchlist-manager, chartilla. Для удобства —
отдельный клиент на домен; все используют одну спеку.
"""

from __future__ import annotations

from framework.http_client import ApiResponse
from framework.routing import OBJECT_MANAGER
from services.base import ServiceClient, drop_none


class ObjectManagerClient(ServiceClient):
    SERVICE = OBJECT_MANAGER

    # --- general ---
    def health(self) -> ApiResponse:
        return self.request("GET", "/object-manager/private/health/", auth=False)

    def object_types(self) -> ApiResponse:
        return self.request("GET", "/object-manager/public/object-types", auth=False)

    def analytics(self) -> ApiResponse:
        return self.request("GET", "/object-manager/public/analytics")

    # --- objects (public) ---
    def get_object_v1(self, object_id: int) -> ApiResponse:
        return self.request("GET", "/object-manager/public/objects/{object_id}", path_params={"object_id": object_id})

    def get_object(self, object_id: int) -> ApiResponse:
        return self.request("GET", "/object-manager/public/v3/objects/{object_id}", path_params={"object_id": object_id})

    def object_cameras(self, object_id: int) -> ApiResponse:
        return self.request("GET", "/object-manager/public/objects/{object_id}/cameras", path_params={"object_id": object_id})

    def modify_object_v2(self, object_id: int, payload: dict) -> ApiResponse:
        return self.request("PATCH", "/object-manager/public/v2/objects/{object_id}", path_params={"object_id": object_id}, json_body=payload)

    def modify_object(self, object_id: int, payload: dict) -> ApiResponse:
        return self.request("PATCH", "/object-manager/public/v3/objects/{object_id}", path_params={"object_id": object_id}, json_body=payload)

    # --- search ---
    def search_v2(self, object_type: str, body: dict | None = None) -> ApiResponse:
        return self.request("POST", "/object-manager/public/v2/search/{object_type}", path_params={"object_type": object_type}, json_body=body or {})

    def search(self, object_type: str, body: dict | None = None) -> ApiResponse:
        return self.request("POST", "/object-manager/public/v3/search/{object_type}", path_params={"object_type": object_type}, json_body=body or {})

    def names(
        self, object_type: str, text: str | None = None, sort_order: str | None = None, limit: int | None = None, offset: int | None = None
    ) -> ApiResponse:
        return self.request(
            "GET",
            "/object-manager/public/v2/names/{object_type}",
            path_params={"object_type": object_type},
            params=drop_none({"text": text, "sort_order": sort_order, "limit": limit, "offset": offset}),
        )

    # --- filters ---
    def filters_v1(self, object_type: str, filters: list[str] | None = None) -> ApiResponse:
        return self.request(
            "GET",
            "/object-manager/public/search/filters/{object_type}",
            path_params={"object_type": object_type},
            params=drop_none({"filters": filters}),
        )

    def filters(self, object_type: str, body: dict | None = None) -> ApiResponse:
        return self.request("POST", "/object-manager/public/v2/filters/{object_type}", path_params={"object_type": object_type}, json_body=body or {})

    def widget_filters(self, object_type: str, widget_type: str, body: dict | None = None) -> ApiResponse:
        return self.request(
            "POST",
            "/object-manager/public/v2/filters/{object_type}/{widget_type}",
            path_params={"object_type": object_type, "widget_type": widget_type},
            json_body=body or {},
        )


class DeviceManagerClient(ServiceClient):
    SERVICE = OBJECT_MANAGER

    def health(self) -> ApiResponse:
        return self.request("GET", "/device-manager/private/health/", auth=False)

    # --- locations ---
    def create_location(self, payload: dict) -> ApiResponse:
        return self.request("POST", "/device-manager/public/locations", json_body=payload)

    def get_location(self, location_id: str, with_nested: bool | None = None, cameras_type: str | None = None) -> ApiResponse:
        return self.request(
            "GET",
            "/device-manager/public/locations/{location_id}",
            path_params={"location_id": location_id},
            params=drop_none({"with_nested": with_nested, "cameras_type": cameras_type}),
        )

    def patch_location(self, location_id: str, payload: dict) -> ApiResponse:
        return self.request("PATCH", "/device-manager/public/locations/{location_id}", path_params={"location_id": location_id}, json_body=payload)

    def delete_location(self, location_id: str) -> ApiResponse:
        return self.request("DELETE", "/device-manager/public/locations/{location_id}", path_params={"location_id": location_id})

    def locations(self) -> ApiResponse:
        return self.request("GET", "/device-manager/public/v2/locations")

    def patch_locations(self, items: list[dict]) -> ApiResponse:
        return self.request("PATCH", "/device-manager/public/v2/locations", json_body=items)

    # --- cameras ---
    def cameras(self, cameras_type: str | None = None) -> ApiResponse:
        return self.request("GET", "/device-manager/public/cameras", params=drop_none({"cameras_type": cameras_type}))

    def get_camera(self, camera_id: str) -> ApiResponse:
        return self.request("GET", "/device-manager/public/cameras/{camera_id}", path_params={"camera_id": camera_id})

    def create_camera(self, camera_id: str, payload: dict) -> ApiResponse:
        return self.request("PUT", "/device-manager/public/cameras/{camera_id}", path_params={"camera_id": camera_id}, json_body=payload)

    def patch_camera(self, camera_id: str, payload: dict, license_provider: str | None = None) -> ApiResponse:
        return self.request(
            "PATCH",
            "/device-manager/public/cameras/{camera_id}",
            path_params={"camera_id": camera_id},
            params=drop_none({"license_provider": license_provider}),
            json_body=payload,
        )

    def patch_cameras(self, items: list[dict]) -> ApiResponse:
        return self.request("PATCH", "/device-manager/public/cameras", json_body=items)

    def delete_camera(self, camera_id: str, force: bool | None = None) -> ApiResponse:
        return self.request("DELETE", "/device-manager/public/cameras/{camera_id}", path_params={"camera_id": camera_id}, params=drop_none({"force": force}))

    def delete_cameras(self, camera_ids: list[str], force: bool | None = None) -> ApiResponse:
        return self.request("DELETE", "/device-manager/public/cameras", params=drop_none({"force": force}), json_body={"camera_ids": camera_ids})

    def restore_camera(self, camera_id: str) -> ApiResponse:
        return self.request("PATCH", "/device-manager/public/cameras/{camera_id}/restore", path_params={"camera_id": camera_id})

    def restore_cameras(self, camera_ids: list[str]) -> ApiResponse:
        return self.request("PATCH", "/device-manager/public/cameras/restore", json_body={"camera_ids": camera_ids})

    def add_camera_thumbnail(self, camera_id: str, content: bytes, filename: str = "thumb.jpg") -> ApiResponse:
        return self.request(
            "POST",
            "/device-manager/public/cameras/{camera_id}/thumbnail",
            path_params={"camera_id": camera_id},
            files={"thumbnail": (filename, content, "image/jpeg")},
        )

    # --- servers / sites ---
    def create_server(self, external_uuid: str, name: str) -> ApiResponse:
        return self.request("POST", "/device-manager/public/servers", json_body={"external_uuid": external_uuid, "name": name})

    def list_servers(self, pgoffset: int = 0, pgsize: int = 10) -> ApiResponse:
        return self.request("POST", "/device-manager/public/servers/list", json_body={"pagination": {"pgoffset": pgoffset, "pgsize": pgsize}})

    def get_server(self, external_uuid: str) -> ApiResponse:
        return self.request("GET", "/device-manager/public/servers/{external_uuid}", path_params={"external_uuid": external_uuid})

    def update_server(self, external_uuid: str, name: str) -> ApiResponse:
        return self.request(
            "PATCH",
            "/device-manager/public/servers/{external_uuid}",
            path_params={"external_uuid": external_uuid},
            json_body={"name": name},
        )

    def create_site(self, external_uuid: str, name: str) -> ApiResponse:
        return self.request("POST", "/device-manager/public/sites", json_body={"external_uuid": external_uuid, "name": name})

    def list_sites(self, pgoffset: int = 0, pgsize: int = 10) -> ApiResponse:
        return self.request("POST", "/device-manager/public/sites/list", json_body={"pagination": {"pgoffset": pgoffset, "pgsize": pgsize}})

    def get_site(self, external_uuid: str) -> ApiResponse:
        return self.request("GET", "/device-manager/public/sites/{external_uuid}", path_params={"external_uuid": external_uuid})

    def update_site(self, external_uuid: str, name: str) -> ApiResponse:
        return self.request("PATCH", "/device-manager/public/sites/{external_uuid}", path_params={"external_uuid": external_uuid}, json_body={"name": name})


class WatchlistManagerClient(ServiceClient):
    SERVICE = OBJECT_MANAGER

    def create_watchlist(self, name: str, object_type: str) -> ApiResponse:
        return self.request("POST", "/watchlist-manager/public/v1/watchlists", json_body={"name": name, "object_type": object_type})

    def patch_watchlist(self, watchlist_id: int, name: str) -> ApiResponse:
        return self.request(
            "PATCH",
            "/watchlist-manager/public/v1/watchlists/{watchlist_id}",
            path_params={"watchlist_id": watchlist_id},
            json_body={"name": name},
        )

    def delete_watchlist(self, watchlist_id: int) -> ApiResponse:
        return self.request("DELETE", "/watchlist-manager/public/v1/watchlists/{watchlist_id}", path_params={"watchlist_id": watchlist_id})

    def watchlist_predicates(self, watchlist_id: int, ordering: str | None = None, pgoffset: int = 0, pgsize: int = 10) -> ApiResponse:
        return self.request(
            "POST",
            "/watchlist-manager/public/v1/watchlists/{watchlist_id}/predicates",
            path_params={"watchlist_id": watchlist_id},
            json_body=drop_none({"ordering": ordering, "pagination": {"pgoffset": pgoffset, "pgsize": pgsize}}),
        )

    def create_predicate(self, watchlist_id: int, filter_: dict) -> ApiResponse:
        return self.request("POST", "/watchlist-manager/public/v1/predicates", json_body={"watchlist_id": watchlist_id, "filter": filter_})

    def patch_predicate(self, predicate_id: int, filter_: dict) -> ApiResponse:
        return self.request(
            "PATCH",
            "/watchlist-manager/public/v1/predicates/{predicate_id}",
            path_params={"predicate_id": predicate_id},
            json_body={"filter": filter_},
        )

    def delete_predicate(self, predicate_id: int) -> ApiResponse:
        return self.request("DELETE", "/watchlist-manager/public/v1/predicates/{predicate_id}", path_params={"predicate_id": predicate_id})

    def company_predicates(self, ordering: str | None = None, pgoffset: int = 0, pgsize: int = 10) -> ApiResponse:
        return self.request(
            "POST",
            "/watchlist-manager/public/v1/company-predicates",
            json_body=drop_none({"ordering": ordering, "pagination": {"pgoffset": pgoffset, "pgsize": pgsize}}),
        )


class ChartillaClient(ServiceClient):
    SERVICE = OBJECT_MANAGER

    def chart(self, object_type: str, chart_type: str, body: dict) -> ApiResponse:
        return self.request(
            "POST",
            "/chartilla/public/v2/chart/{object_type}/{chart_type}",
            path_params={"object_type": object_type, "chart_type": chart_type},
            json_body=body,
        )


class ObjectManagerPrivateClient(ServiceClient):
    """Private API object-manager (межсервисное). Через gateway НЕ доступно —
    тесты на него помечаются @endpoint(...) с /private/ путём и автоматически
    пропускаются при API_ROUTING=gateway; работают при API_ROUTING=direct."""

    SERVICE = OBJECT_MANAGER

    def version(self) -> ApiResponse:
        return self.request("GET", "/object-manager/private/v1/version/", auth=False)

    def create_object(self, payload: dict) -> ApiResponse:
        return self.request("POST", "/object-manager/private/v4/objects", json_body=payload, auth=False)

    def get_object(self, object_id: int) -> ApiResponse:
        return self.request("GET", "/object-manager/private/v4/objects/{object_id}", path_params={"object_id": object_id}, auth=False)

    def modify_object(self, object_id: int, payload: dict) -> ApiResponse:
        return self.request("PATCH", "/object-manager/private/v4/objects/{object_id}", path_params={"object_id": object_id}, json_body=payload, auth=False)

    def orphan_objects(self, object_type: str | None = None, pgoffset: int = 0, pgsize: int = 10) -> ApiResponse:
        return self.request(
            "GET",
            "/object-manager/private/v4/objects/orphan",
            params=drop_none({"object_type": object_type, "pgoffset": pgoffset, "pgsize": pgsize}),
            auth=False,
        )

    def reference_objects(self, object_type: str | None = None, pgoffset: int = 0, pgsize: int = 10, with_embedding: bool | None = None) -> ApiResponse:
        return self.request(
            "GET",
            "/object-manager/private/v4/objects/reference",
            params=drop_none({"object_type": object_type, "pgoffset": pgoffset, "pgsize": pgsize, "with_embedding": with_embedding}),
            auth=False,
        )

    def private_cameras(self, company_id: int, cameras_type: str | None = None) -> ApiResponse:
        return self.request("GET", "/device-manager/private/cameras", params=drop_none({"company_id": company_id, "cameras_type": cameras_type}), auth=False)
