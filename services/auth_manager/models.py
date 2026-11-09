from __future__ import annotations

from enum import Enum

from services.base import ApiModel


class Roles(str, Enum):
    ADMIN = "admin"
    REGULAR = "regular"


class CompanyTypes(str, Enum):
    INTEGRATOR = "integrator"
    USER = "user"


class AuthOut(ApiModel):
    access_token: str
    refresh_token: str
    user_id: str


class MeOut(ApiModel):
    user_id: str


class RoleOut(ApiModel):
    id: str
    name: str
    description: str
    rank: int


class UserOut(ApiModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str
    role: Roles
    rank: int
    photo_url: str | None = None
    timezone: str


class CompanyOut(ApiModel):
    id: int
    name: str


class CompanyDetailsOut(ApiModel):
    id: int
    name: str
    role: Roles


class UserCompanySchema(ApiModel):
    id: int
    name: str
    company_type: CompanyTypes
    rank: int
    retention_period: int
    role: Roles | None = None


class VersionSchema(ApiModel):
    tag: str
    branch: str
    commit: str
    assembly_date: str
    author: str
    trigger: str


class LicenseOut(ApiModel):
    id: str
    days: int
    cameras_count: int
    activated_at: str
    expired_at: str
    trial: bool | None = None
    is_enabled: bool | None = None
    is_expired: bool | None = None


class StateDeleteResultSchema(ApiModel):
    deleted: int
