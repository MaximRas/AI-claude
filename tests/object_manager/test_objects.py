import allure
import pytest

from framework import endpoint
from framework.data import nonexistent_int_id, unique_name
from services.object_manager.models import ObjectOut

SERVICE = "object-manager"


@allure.feature("object-manager")
@allure.story("get object")
class TestGetObject:
    @pytest.mark.parametrize(
        "method_name",
        [
            pytest.param("get_object_v1", marks=endpoint(SERVICE, "GET", "/object-manager/public/objects/{object_id}"), id="v1"),
            pytest.param("get_object", marks=endpoint(SERVICE, "GET", "/object-manager/public/v3/objects/{object_id}"), id="v3"),
        ],
    )
    def test_get_existing(self, om_api, any_object, method_name):
        obj = getattr(om_api, method_name)(any_object["id"]).assert_status(200).assert_contract().parse(ObjectOut)
        assert obj.id == any_object["id"]
        assert obj.track_id == any_object["track_id"]
        assert obj.camera == any_object["camera_id"]

    @endpoint(SERVICE, "GET", "/object-manager/public/v3/objects/{object_id}")
    def test_get_not_found(self, om_api):
        om_api.get_object(nonexistent_int_id()).assert_error(404)

    @endpoint(SERVICE, "GET", "/object-manager/public/objects/{object_id}")
    def test_get_v1_not_found(self, om_api):
        om_api.get_object_v1(nonexistent_int_id()).assert_error(404)

    @endpoint(SERVICE, "GET", "/object-manager/public/v3/objects/{object_id}")
    def test_get_invalid_id(self, om_api):
        om_api.request("GET", "/object-manager/public/v3/objects/{object_id}", path_params={"object_id": "abc"}).assert_status(422)

    @endpoint(SERVICE, "GET", "/object-manager/public/v3/objects/{object_id}")
    def test_get_unauthorized(self, anon_om, bad_token):
        anon_om.with_token(bad_token).get_object(1).assert_unauthorized()

    @endpoint(SERVICE, "GET", "/object-manager/public/objects/{object_id}/cameras")
    def test_object_cameras(self, om_api, any_object):
        cameras = om_api.object_cameras(any_object["id"]).assert_status(200).assert_contract().json()
        assert any_object["camera_id"] in {c["id"] for c in cameras}

    @endpoint(SERVICE, "GET", "/object-manager/public/objects/{object_id}/cameras")
    def test_object_cameras_not_found(self, om_api):
        om_api.object_cameras(nonexistent_int_id()).assert_status(404)


@allure.feature("object-manager")
@allure.story("modify object")
class TestModifyObject:
    """Меняем только notes и сразу возвращаем исходное значение."""

    @pytest.mark.parametrize(
        "method_name",
        [
            pytest.param("modify_object_v2", marks=endpoint(SERVICE, "PATCH", "/object-manager/public/v2/objects/{object_id}"), id="v2"),
            pytest.param("modify_object", marks=endpoint(SERVICE, "PATCH", "/object-manager/public/v3/objects/{object_id}"), id="v3"),
        ],
    )
    def test_update_notes(self, om_api, any_object, cleanup, method_name):
        original_notes = (any_object.get("meta") or {}).get("notes")
        modify = getattr(om_api, method_name)
        cleanup.add("restore notes", lambda: modify(any_object["id"], {"metadata": {"notes": original_notes or ""}}))

        notes = unique_name("notes")
        updated = modify(any_object["id"], {"metadata": {"notes": notes}}).assert_status(201).assert_contract().json()
        assert updated["meta"].get("notes") == notes
        assert om_api.get_object(any_object["id"]).json()["meta"].get("notes") == notes

    @endpoint(SERVICE, "PATCH", "/object-manager/public/v3/objects/{object_id}")
    def test_update_not_found(self, om_api):
        om_api.modify_object(nonexistent_int_id(), {"metadata": {"notes": "x"}}).assert_error(404)

    @endpoint(SERVICE, "PATCH", "/object-manager/public/v3/objects/{object_id}")
    def test_update_wrong_type(self, om_api, any_object):
        om_api.modify_object(any_object["id"], {"parent_id": "not-an-int"}).assert_validation_error("parent_id")


def _named_references(om_api, n: int = 2) -> list[dict]:
    """Именованные эталонные объекты (кластеры) лица: names -> GET по id."""
    out = []
    for item in om_api.names("face", limit=50).assert_status(200).json():
        obj = om_api.get_object(item["id"])
        if obj.status_code == 200 and obj.json().get("is_reference") and (obj.json().get("meta") or {}).get("name"):
            out.append(obj.json())
        if len(out) == n:
            return out
    pytest.skip("нужно минимум два именованных кластера лиц")


def _child_of(om_api, reference: dict) -> dict:
    page = om_api.search("face", {"common_filters": {"name": reference["meta"]["name"]}, "pagination": {"pgoffset": 0, "pgsize": 100}})
    for item in page.assert_status(200).json()["items"]:
        if item.get("parent_id") == reference["id"]:
            return item
    pytest.skip(f"у кластера {reference['id']} нет дочерних объектов")


@allure.feature("object-manager")
@allure.story("кластеры: ручное склеивание")
class TestClusterManualMerge:
    """Перенос объекта в другой кластер / отвязка от кластера через PATCH parent_id. Всё возвращается в cleanup."""

    @endpoint(SERVICE, "PATCH", "/object-manager/public/v3/objects/{object_id}")
    def test_move_to_another_cluster(self, om_api, cleanup):
        a, b = _named_references(om_api)
        child = _child_of(om_api, a)
        cleanup.add("вернуть объект в исходный кластер", lambda: om_api.modify_object(child["id"], {"parent_id": a["id"]}))

        om_api.modify_object(child["id"], {"parent_id": b["id"]}).assert_status(201).assert_contract()
        for getter in (om_api.get_object, om_api.get_object_v1):
            moved = getter(child["id"]).assert_status(200).json()
            assert moved["parent_id"] == b["id"]
            assert moved["meta"].get("name") == b["meta"]["name"], "имя наследуется от нового кластера"
        by_b = om_api.search("face", {"common_filters": {"name": b["meta"]["name"]}, "pagination": {"pgoffset": 0, "pgsize": 200}}).json()["items"]
        by_a = om_api.search("face", {"common_filters": {"name": a["meta"]["name"]}, "pagination": {"pgoffset": 0, "pgsize": 200}}).json()["items"]
        assert child["id"] in {i["id"] for i in by_b}, "объект ищется по имени нового кластера"
        assert child["id"] not in {i["id"] for i in by_a}, "объект больше не ищется по имени старого кластера"

    @endpoint(SERVICE, "PATCH", "/object-manager/public/v3/objects/{object_id}")
    def test_reset_parent(self, om_api, cleanup):
        (a,) = _named_references(om_api, 1)
        child = _child_of(om_api, a)
        cleanup.add("вернуть объект в кластер", lambda: om_api.modify_object(child["id"], {"parent_id": a["id"]}))
        om_api.modify_object(child["id"], {"to_reset_parent_id": True}).assert_status(201)
        assert om_api.get_object(child["id"]).json()["parent_id"] is None

    @endpoint(SERVICE, "PATCH", "/object-manager/public/v3/objects/{object_id}")
    def test_move_to_unknown_parent(self, om_api):
        (a,) = _named_references(om_api, 1)
        child = _child_of(om_api, a)
        om_api.modify_object(child["id"], {"parent_id": nonexistent_int_id()}).assert_error(404, message_contains="does not exist")
        assert om_api.get_object(child["id"]).json()["parent_id"] == a["id"], "неудачный PATCH не должен менять parent"

    @endpoint(SERVICE, "PATCH", "/object-manager/public/v3/objects/{object_id}")
    @endpoint(SERVICE, "GET", "/object-manager/public/v2/names/{object_type}")
    def test_rename_cluster_visible_in_names(self, om_api, cleanup):
        """object-ng 03.11.2026: после переименования кластера names (автокомплит) отдаёт старое имя."""
        (a,) = _named_references(om_api, 1)
        cleanup.add("вернуть имя кластера", lambda: om_api.modify_object(a["id"], {"metadata": {"name": a["meta"]["name"]}}))
        new_name = unique_name("cluster")
        om_api.modify_object(a["id"], {"metadata": {"name": new_name}}).assert_status(201)
        found = om_api.names("face", text=new_name).assert_status(200).json()
        assert a["id"] in {x["id"] for x in found}, "переименованный кластер не находится в names по новому имени"
