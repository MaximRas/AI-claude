from __future__ import annotations

from enum import Enum
from typing import Any

from services.base import ApiModel


class AccessRole(str, Enum):
    VIEWER = "viewer"
    EDITOR = "editor"
    OWNER = "owner"


class AccessScope(str, Enum):
    COMPANY = "company"
    USER = "user"


class ListScope(str, Enum):
    ALL = "all"
    MY = "my"
    SHARED = "shared"


class Created(ApiModel):
    id: str


class GridItem(ApiModel):
    w: int
    h: int
    x: int
    y: int
    id: str


# Поля старого API виджетов. С layout-manager 1.4.x (MR «отказ от legacy-полей») их нет в ответах,
# а во входящих запросах они игнорируются.
LEGACY_WIDGET_FIELDS = frozenset({"online", "filters", "timeslice", "timeslice_id", "detalization"})


class WidgetItem(ApiModel):
    id: str
    name: str
    type: str
    state: dict[str, Any] = {}
    user_id: str
    created_at: str
    access_role: AccessRole
    is_shared: bool
    parent_layout_id: str | None = None


class LayoutItem(ApiModel):
    id: str
    name: str
    grid: list[GridItem]
    ordering: int | None = None
    user_id: str
    state: dict[str, Any] = {}
    created_at: str
    access_role: AccessRole
    is_shared: bool


class BasePagination(ApiModel):
    offset: int
    size: int
    amount: int


class WidgetsPage(ApiModel):
    pagination: BasePagination
    items: list[WidgetItem]


class LayoutsPage(ApiModel):
    pagination: BasePagination
    items: list[LayoutItem]


class AccessEntry(ApiModel):
    id: int
    scope: AccessScope
    role: AccessRole
    user_id: str | None = None
    created_by: str
    created_at: str


class DetailingOut(ApiModel):
    name: str
    value: int
    default: bool
