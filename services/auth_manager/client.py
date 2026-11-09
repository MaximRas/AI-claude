"""Клиент auth-manager. Пути — как в specs/auth-manager.json."""

from __future__ import annotations

from framework.http_client import ApiResponse
from framework.routing import AUTH_MANAGER
from services.base import ServiceClient, drop_none


class AuthManagerClient(ServiceClient):
    SERVICE = AUTH_MANAGER

    # --- general ---
    def health(self) -> ApiResponse:
        return self.request("GET", "/private/health/", auth=False)

    def version(self) -> ApiResponse:
        return self.request("GET", "/public/v1/version", auth=False)

    # --- auth ---
    def auth(self, login: str | None, password: str | None) -> ApiResponse:
        return self.request("POST", "/public/auth", json_body=drop_none({"login": login, "password": password}), auth=False)

    def refresh_token(self, access_token: str, refresh_token: str) -> ApiResponse:
        return self.request(
            "POST",
            "/public/auth/refresh-token",
            headers={"access-token": access_token, "refresh-token": refresh_token},
            auth=False,
        )

    def me(self) -> ApiResponse:
        return self.request("GET", "/public/me")

    def check_registered(self, email: str) -> ApiResponse:
        return self.request("POST", "/public/v1/users/check-registered", json_body={"email": email}, auth=False)

    # --- справочники ---
    def roles(self) -> ApiResponse:
        return self.request("GET", "/public/roles")

    def company_types(self) -> ApiResponse:
        return self.request("GET", "/public/v1/company-types")

    # --- пользователи ---
    def users(self, pgoffset: int | None = None, pgsize: int | None = None) -> ApiResponse:
        return self.request("GET", "/public/users", params=drop_none({"pgoffset": pgoffset, "pgsize": pgsize}))

    def user(self, user_id: str) -> ApiResponse:
        return self.request("GET", "/public/users/{user_id}", path_params={"user_id": user_id})

    def edit_user(self, user_id: str, payload: dict) -> ApiResponse:
        return self.request("PATCH", "/public/users/{user_id}", path_params={"user_id": user_id}, json_body=payload)

    def current_user(self) -> ApiResponse:
        return self.request("GET", "/public/v1/user")

    def company_users(self, company_id: int, body: dict | None = None) -> ApiResponse:
        return self.request("POST", "/public/v1/company/{company_id}/users", path_params={"company_id": company_id}, json_body=body or {})

    # --- компании ---
    def company(self) -> ApiResponse:
        return self.request("GET", "/public/company")

    def user_company(self) -> ApiResponse:
        return self.request("GET", "/public/v1/user/company")

    def user_companies(self, body: dict | None = None) -> ApiResponse:
        return self.request("POST", "/public/v1/user/companies", json_body=body or {})

    def available_companies(self) -> ApiResponse:
        return self.request("GET", "/public/context/available-companies")

    def set_active_company(self, company_id: int) -> ApiResponse:
        return self.request("PATCH", "/public/context/active-company", json_body={"company": company_id})

    # --- лицензии ---
    def licenses(self) -> ApiResponse:
        return self.request("GET", "/public/licenses")

    def licenses_list(self, body: dict | None = None) -> ApiResponse:
        return self.request("POST", "/public/v1/licenses/list", json_body=body or {})

    def demo_licenses_summary(self) -> ApiResponse:
        return self.request("GET", "/public/v1/demo-licenses/summary")

    # --- gateway tokens ---
    def gateway_tokens(self, pgoffset: int | None = None, pgsize: int | None = None) -> ApiResponse:
        return self.request("GET", "/public/v1/gateway_tokens", params=drop_none({"pgoffset": pgoffset, "pgsize": pgsize}))

    # --- state (v1) ---
    def get_user_state_v1(self) -> ApiResponse:
        return self.request("GET", "/public/v1/users/state")

    def set_user_state_v1(self, state: dict) -> ApiResponse:
        return self.request("POST", "/public/v1/users/state", json_body={"state": state})

    # --- state (v2, key-value) ---
    def upsert_user_state(self, items: dict) -> ApiResponse:
        return self.request("PUT", "/public/v2/users/state", json_body={"items": items})

    def select_user_state(self, keys: list[str] | None = None) -> ApiResponse:
        return self.request("POST", "/public/v2/users/state", json_body=drop_none({"keys": keys}))

    def delete_user_state(self, keys: list[str] | None = None) -> ApiResponse:
        return self.request("DELETE", "/public/v2/users/state", json_body=drop_none({"keys": keys}))

    def upsert_company_state(self, items: dict) -> ApiResponse:
        return self.request("PUT", "/public/v2/companies/state", json_body={"items": items})

    def select_company_state(self, keys: list[str] | None = None) -> ApiResponse:
        return self.request("POST", "/public/v2/companies/state", json_body=drop_none({"keys": keys}))

    def delete_company_state(self, keys: list[str] | None = None) -> ApiResponse:
        return self.request("DELETE", "/public/v2/companies/state", json_body=drop_none({"keys": keys}))
