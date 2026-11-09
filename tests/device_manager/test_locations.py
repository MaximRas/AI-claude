import allure
import pytest

from framework import endpoint
from framework.data import random_uuid, unique_name
from services.object_manager.models import Location, LocationOut

SERVICE = "object-manager"
LOCATIONS = "/device-manager/public/locations"
LOCATION = "/device-manager/public/locations/{location_id}"
LOCATIONS_V2 = "/device-manager/public/v2/locations"


@allure.feature("device-manager")
@allure.story("locations")
class TestLocations:
    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/device-manager/private/health/")
    def test_health(self, anon_devices):
        assert anon_devices.health().assert_status(200).json()["type"] == "device-manager"

    @pytest.mark.smoke
    @endpoint(SERVICE, "POST", LOCATIONS)
    def test_create_location(self, location_factory):
        loc = Location.model_validate(location_factory(description="autotest", coordinates=[55.75, 37.61], ordering=1))
        assert loc.description == "autotest"
        assert loc.coordinates == [55.75, 37.61]
        assert loc.cameras == []

    @endpoint(SERVICE, "POST", LOCATIONS)
    def test_create_nested_location(self, location_factory):
        parent = location_factory()
        child = location_factory(parent_location_id=parent["id"])
        assert child["parent_location_id"] == parent["id"]

    @endpoint(SERVICE, "POST", LOCATIONS)
    def test_create_location_without_name(self, devices_api):
        devices_api.create_location({"description": "no name"}).assert_validation_error("name")

    @endpoint(SERVICE, "POST", LOCATIONS)
    def test_create_location_unknown_parent(self, devices_api, cleanup):
        resp = devices_api.create_location({"name": unique_name("location"), "parent_location_id": random_uuid()})
        if resp.status_code == 200:
            cleanup.add("location", lambda: devices_api.delete_location(resp.json()["id"]))
        resp.assert_status(400, 404)

    @endpoint(SERVICE, "POST", LOCATIONS)
    def test_create_location_unauthorized(self, anon_devices, bad_token):
        anon_devices.with_token(bad_token).create_location({"name": unique_name("location")}).assert_unauthorized()

    @endpoint(SERVICE, "GET", LOCATION)
    def test_get_location(self, devices_api, location_factory):
        created = location_factory()
        body = devices_api.get_location(created["id"]).assert_status(200).assert_contract().json()
        assert body["id"] == created["id"]
        assert body["name"] == created["name"]

    @endpoint(SERVICE, "GET", LOCATION)
    def test_get_location_with_nested(self, devices_api, location_factory):
        parent = location_factory()
        location_factory(parent_location_id=parent["id"])
        devices_api.get_location(parent["id"], with_nested=True).assert_status(200).assert_contract()

    @endpoint(SERVICE, "GET", LOCATION)
    def test_get_location_not_found(self, devices_api):
        devices_api.get_location(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "GET", LOCATION)
    def test_get_location_invalid_uuid(self, devices_api):
        devices_api.get_location("not-a-uuid").assert_status(404, 422)

    @endpoint(SERVICE, "PATCH", LOCATION)
    def test_patch_location(self, devices_api, location_factory):
        created = location_factory()
        new_name = unique_name("location_renamed")
        updated = devices_api.patch_location(created["id"], {"name": new_name}).assert_status(200).assert_contract().parse(Location)
        assert updated.name == new_name
        assert devices_api.get_location(created["id"]).json()["name"] == new_name

    @endpoint(SERVICE, "PATCH", LOCATION)
    def test_patch_location_not_found(self, devices_api):
        devices_api.patch_location(random_uuid(), {"name": unique_name("location")}).assert_error(404)

    @pytest.mark.parametrize("name", ["x", "y" * 100], ids=["too_short", "too_long"])
    @endpoint(SERVICE, "PATCH", LOCATION)
    def test_patch_location_name_length(self, devices_api, location_factory, name):
        # имя: 2..99 символов
        devices_api.patch_location(location_factory()["id"], {"name": name}).assert_validation_error("name")

    @endpoint(SERVICE, "DELETE", LOCATION)
    def test_delete_location(self, devices_api):
        created = devices_api.create_location({"name": unique_name("location")}).assert_status(200).json()
        devices_api.delete_location(created["id"]).assert_status(202)
        devices_api.get_location(created["id"]).assert_status(404)

    @endpoint(SERVICE, "DELETE", LOCATION)
    def test_delete_location_not_found(self, devices_api):
        devices_api.delete_location(random_uuid()).assert_error(404)


@allure.feature("device-manager")
@allure.story("locations v2")
class TestLocationsV2:
    @endpoint(SERVICE, "GET", LOCATIONS_V2)
    def test_list_contains_created(self, devices_api, location_factory):
        created = location_factory()
        items = devices_api.locations().assert_status(200).assert_contract().parse(list[LocationOut])
        assert created["id"] in {i.id for i in items}

    @endpoint(SERVICE, "PATCH", LOCATIONS_V2)
    def test_batch_update(self, devices_api, location_factory):
        a, b = location_factory(), location_factory()
        payload = [{"id": a["id"], "ordering": 10}, {"id": b["id"], "ordering": 11}]
        updated = devices_api.patch_locations(payload).assert_status(200).assert_contract().json()
        by_id = {i["id"]: i for i in updated}
        assert by_id[a["id"]]["ordering"] == 10
        assert by_id[b["id"]]["ordering"] == 11

    @endpoint(SERVICE, "PATCH", LOCATIONS_V2)
    def test_batch_update_without_id(self, devices_api):
        devices_api.patch_locations([{"name": "x"}]).assert_status(422)
