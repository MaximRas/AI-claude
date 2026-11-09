"""Камеры. Чтение — безопасно. Создание/удаление камер влияет на лицензии
компании, поэтому помечено `destructive` (запуск только при ALLOW_DESTRUCTIVE=true)."""

import allure
import pytest

from framework import endpoint
from framework.data import random_uuid, unique_name
from services.object_manager.models import CameraSchema, ListCamerasTypes

SERVICE = "object-manager"
CAMERAS = "/device-manager/public/cameras"
CAMERA = "/device-manager/public/cameras/{camera_id}"


@allure.feature("device-manager")
@allure.story("cameras: read")
class TestCamerasRead:
    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", CAMERAS)
    def test_list(self, devices_api):
        devices_api.cameras().assert_status(200).assert_contract().parse(list[CameraSchema])

    @pytest.mark.parametrize("cameras_type", [t.value for t in ListCamerasTypes])
    @endpoint(SERVICE, "GET", CAMERAS)
    def test_list_by_type(self, devices_api, cameras_type):
        devices_api.cameras(cameras_type=cameras_type).assert_status(200).assert_contract()

    @endpoint(SERVICE, "GET", CAMERAS)
    def test_list_invalid_type(self, devices_api):
        devices_api.cameras(cameras_type="bogus").assert_status(422)

    @endpoint(SERVICE, "GET", CAMERAS)
    def test_list_unauthorized(self, anon_devices, bad_token):
        anon_devices.with_token(bad_token).cameras().assert_unauthorized()

    @endpoint(SERVICE, "GET", CAMERA)
    def test_get(self, devices_api, any_camera):
        cam = devices_api.get_camera(any_camera["id"]).assert_status(200).assert_contract().parse(CameraSchema)
        assert cam.id == any_camera["id"]

    @endpoint(SERVICE, "GET", CAMERA)
    def test_get_not_found(self, devices_api):
        devices_api.get_camera(random_uuid()).assert_error(404)


@allure.feature("device-manager")
@allure.story("cameras: write")
@pytest.mark.destructive
class TestCamerasWrite:
    @pytest.fixture
    def camera(self, devices_api, cleanup):
        camera_id = random_uuid()
        body = devices_api.create_camera(camera_id, {"name": unique_name("camera")}).assert_status(201).json()
        cleanup.add(f"camera {camera_id}", lambda: devices_api.delete_camera(camera_id, force=True))
        return body

    @endpoint(SERVICE, "PUT", CAMERA)
    def test_create(self, camera):
        CameraSchema.model_validate(camera)
        assert camera["name"].startswith("autotest_")

    @endpoint(SERVICE, "PATCH", CAMERA)
    def test_rename(self, devices_api, camera):
        name = unique_name("camera_renamed")
        devices_api.patch_camera(camera["id"], {"name": name}).assert_status(200).assert_contract()
        assert devices_api.get_camera(camera["id"]).json()["name"] == name

    @endpoint(SERVICE, "PATCH", CAMERAS)
    def test_batch_update(self, devices_api, camera, location_factory):
        loc = location_factory()
        updated = devices_api.patch_cameras([{"id": camera["id"], "locations": [loc["id"]]}]).assert_status(200).assert_contract().json()
        assert loc["id"] in updated[0]["locations"]

    @endpoint(SERVICE, "DELETE", CAMERA)
    @endpoint(SERVICE, "PATCH", "/device-manager/public/cameras/{camera_id}/restore")
    def test_delete_and_restore(self, devices_api, camera):
        devices_api.delete_camera(camera["id"]).assert_status(202)
        restored = devices_api.restore_camera(camera["id"]).assert_status(200).assert_contract().json()
        assert restored["id"] == camera["id"]

    @endpoint(SERVICE, "DELETE", CAMERAS)
    @endpoint(SERVICE, "PATCH", "/device-manager/public/cameras/restore")
    def test_batch_delete_and_restore(self, devices_api, camera):
        devices_api.delete_cameras([camera["id"]]).assert_status(202)
        devices_api.restore_cameras([camera["id"]]).assert_status(200).assert_contract()

    @endpoint(SERVICE, "POST", "/device-manager/public/cameras/{camera_id}/thumbnail")
    def test_thumbnail(self, devices_api, camera):
        # минимальный валидный JPEG (1x1)
        jpeg = bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c"
            "20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100"
            "000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114"
            "328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a63646566"
            "6768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3"
            "d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fbd3ffd9"
        )
        body = devices_api.add_camera_thumbnail(camera["id"], jpeg).assert_status(201).assert_contract().json()
        assert body["thumbnail_url"]
