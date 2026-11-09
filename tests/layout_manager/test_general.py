import time

import allure
import pytest

from framework import endpoint
from services.auth_manager.models import VersionSchema
from services.layout_manager.models import DetailingOut

SERVICE = "layout-manager"


@allure.feature("layout-manager")
@allure.story("general")
class TestGeneral:
    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/private/health")
    def test_health(self, anon_layout):
        assert anon_layout.health().assert_status(200).json()["type"] == "layout_manager"

    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/public/version")
    def test_version(self, anon_layout):
        anon_layout.version().assert_status(200).assert_contract().parse(VersionSchema)

    # GET /public/report-timeslices удалён (MR «отказ от legacy-полей виджетов»). Эндпоинта больше нет в спеке,
    # поэтому без @endpoint: тест фиксирует, что ручка не вернулась.
    def test_report_timeslices_removed(self, layout_api):
        layout_api.request("GET", "/public/report-timeslices").assert_error(404)

    @endpoint(SERVICE, "GET", "/public/detailing")
    def test_detailing(self, layout_api):
        end = int(time.time())
        items = layout_api.detailing(end - 86400, end).assert_status(200).assert_contract().parse(list[DetailingOut])
        assert items, "для суточного интервала должна быть хотя бы одна детализация"
        assert sum(1 for i in items if i.default) == 1, "ровно одна детализация по умолчанию"

    @endpoint(SERVICE, "GET", "/public/detailing")
    def test_detailing_missing_params(self, layout_api):
        layout_api.request("GET", "/public/detailing").assert_validation_error("timestamp_start", "timestamp_end")
