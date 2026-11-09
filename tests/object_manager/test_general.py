import allure
import pytest

from framework import endpoint
from services.object_manager.models import ObjectType

SERVICE = "object-manager"


@allure.feature("object-manager")
@allure.story("general")
class TestGeneral:
    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/object-manager/private/health/")
    def test_health(self, anon_om):
        body = anon_om.health().assert_status(200).json()
        assert body["type"] == "object-manager"

    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/object-manager/public/object-types")
    def test_object_types(self, anon_om):
        types = anon_om.object_types().assert_status(200).assert_contract().json()
        assert set(types) == {t.value for t in ObjectType}

    @endpoint(SERVICE, "GET", "/object-manager/public/analytics")
    def test_analytics(self, om_api):
        plugins = om_api.analytics().assert_status(200).assert_contract().json()
        assert all(p["id"] and p["name"] for p in plugins)

    @endpoint(SERVICE, "GET", "/object-manager/public/analytics")
    def test_analytics_unauthorized(self, anon_om, bad_token):
        anon_om.with_token(bad_token).analytics().assert_unauthorized()

    @endpoint(SERVICE, "GET", "/object-manager/private/v1/version/")
    def test_private_version(self, om_private):
        om_private.version().assert_status(200).assert_contract()
