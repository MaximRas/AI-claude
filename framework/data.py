"""Генераторы тестовых данных. Всё, что создают тесты, имеет префикс TEST_DATA_PREFIX —
так мусор легко найти и вычистить на стенде."""

from __future__ import annotations

import datetime as dt
import random
import string
import uuid

from config.settings import get_settings


def prefix() -> str:
    return get_settings().test_data_prefix


def unique_name(kind: str = "item", length: int = 8) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return f"{prefix()}{kind}_{suffix}"


def random_uuid() -> str:
    return str(uuid.uuid4())


def nonexistent_int_id() -> int:
    # Заведомо несуществующий, но валидный для int4/int8 id.
    return 2_000_000_000 + random.randint(0, 100_000_000)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(ts: dt.datetime) -> str:
    return ts.isoformat()


def time_range(hours: int = 24) -> tuple[str, str]:
    """(start, end) в ISO-формате: последние N часов."""
    end = utc_now()
    return iso(end - dt.timedelta(hours=hours)), iso(end)
