from __future__ import annotations

from enum import Enum
from typing import Any

from services.base import ApiModel


class ObjectType(str, Enum):
    FACE = "face"
    VEHICLE = "vehicle"
    PERSON = "person"
    GROUP_OF_PEOPLE = "group_of_people"
    UNCLASSIFIED = "unclassified"


class SplitObjectType(str, Enum):
    """Типы, доступные в v3 search (split-таблицы)."""

    FACE = "face"
    VEHICLE = "vehicle"
    PERSON = "person"


class WidgetType(str, Enum):
    PIE_CHART = "pie_chart"
    HIST_CHART = "hist_chart"
    LINE_CHART = "line_chart"
    NUMERIC = "numeric"


class WatchlistType(str, Enum):
    FACE = "face"
    VEHICLE = "vehicle"


class CameraStatus(str, Enum):
    DELETED = "deleted"
    FORCE_DELETED = "force_deleted"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class ListCamerasTypes(str, Enum):
    REGULAR = "regular"
    ARCHIVED = "archived"
    BOTH = "both"


class GroupingField(str, Enum):
    AGE = "age"
    GENDER = "gender"
    MASK = "mask"
    GLASSES = "glasses"
    BEARD = "beard"
    TYPE = "type"
    VEHICLE_TYPE = "vehicle_type"
    MANUFACTURER = "manufacturer"
    MODEL = "model"
    COLOR = "color"
    CAMERA_ID = "camera_id"


class Pagination(ApiModel):
    offset: int
    size: int
    amount: int | None = None


class ObjectOut(ApiModel):
    id: int
    timestamp: int
    last_seen: int
    image_path: str
    image_url: str
    analytics: list[str]
    type: ObjectType
    meta: dict[str, Any] = {}
    is_reference: bool = False
    parent_id: int | None = None
    camera: str
    track_id: str


class ObjectResponseSchema(ApiModel):
    id: int
    image_path: str
    image_url: str
    type: ObjectType
    meta: dict[str, Any] = {}
    is_reference: bool
    camera_id: str
    camera_is_fake: bool
    track_id: str
    parent_id: int | None = None


class PaginatedObjects(ApiModel):
    pagination: Pagination
    items: list[ObjectResponseSchema]


class LocationOut(ApiModel):
    id: str
    name: str | None = None
    description: str | None = None
    coordinates: list[float] | None = None
    parent_location_id: str | None = None
    ordering: int | None = None


class Location(LocationOut):
    name: str
    cameras: list[dict] = []


class CameraSchema(ApiModel):
    id: str
    name: str | None = None
    locations: list[str]
    is_new: bool
    is_fake: bool
    status: str | None = None
    thumbnail_url: str | None = None


class ServerOut(ApiModel):
    external_uuid: str
    name: str
    created_at: str
    updated_at: str | None = None


SiteOut = ServerOut


class Watchlist(ApiModel):
    id: int
    object_type: WatchlistType
    name: str
    created_at: str
    company_id: int
    created_user_id: str
    deleted_at: str | None = None


class Predicate(ApiModel):
    id: int
    watchlist_id: int
    filter: dict[str, Any]
    created_at: str
    created_user_id: str
    deleted_at: str | None = None


class PredicateList(ApiModel):
    items: list[Predicate]
    pagination: Pagination


class FilterOrderings(ApiModel):
    name: str
    type: str
    label: str
    tooltip: str


class FiltersOrderingsSchema(ApiModel):
    common_filters: list[FilterOrderings]
    object_type_filters: list[FilterOrderings]
    orderings: list[FilterOrderings]


class ChartSeries(ApiModel):
    name: str
    data: list[Any]


class ChartData(ApiModel):
    """pie: {group_by, series:[{name,data}]}; hist/line: {categories, series...}; numeric: {series: <число>}."""

    series: list[ChartSeries] | int | float | None = None
    group_by: list[str] | None = None
    categories: list[Any] | None = None
