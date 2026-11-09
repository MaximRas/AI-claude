import allure
import pytest

from framework import endpoint
from framework.data import random_uuid, time_range
from services.object_manager.models import FiltersOrderingsSchema, PaginatedObjects, SplitObjectType

SERVICE = "object-manager"
V3_SEARCH = "/object-manager/public/v3/search/{object_type}"
V2_SEARCH = "/object-manager/public/v2/search/{object_type}"


@allure.feature("object-manager")
@allure.story("search v3")
class TestSearchV3:
    @pytest.mark.smoke
    @pytest.mark.parametrize("object_type", [t.value for t in SplitObjectType])
    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_default(self, om_api, object_type):
        page = om_api.search(object_type).assert_status(200).assert_contract().parse(PaginatedObjects)
        assert page.pagination.size <= 10
        assert all(item.type.value == object_type for item in page.items)

    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_pagination(self, om_api):
        first = om_api.search("face", {"pagination": {"pgoffset": 0, "pgsize": 2}}).assert_status(200).json()
        second = om_api.search("face", {"pagination": {"pgoffset": 2, "pgsize": 2}}).assert_status(200).json()
        assert len(first["items"]) <= 2
        ids1, ids2 = {i["id"] for i in first["items"]}, {i["id"] for i in second["items"]}
        assert not ids1 & ids2, "страницы пересекаются"

    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_ordering_timestamp_desc(self, om_api):
        items = (
            om_api.search("face", {"orderings": {"timestamp": "timestamp desc"}, "pagination": {"pgoffset": 0, "pgsize": 20}})
            .assert_status(200)
            .json()["items"]
        )
        ts = [i["timestamp"] for i in items]
        assert ts == sorted(ts, reverse=True)

    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_by_time_range(self, om_api):
        start, end = time_range(hours=24)
        om_api.search("vehicle", {"timestamp_filters": {"timestamp_start": start, "timestamp_end": end}}).assert_status(200).assert_contract()

    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_unknown_camera_returns_empty(self, om_api):
        body = om_api.search("face", {"camera_filters": {"camera": [random_uuid()]}}).assert_status(200).json()
        assert body["items"] == []

    @pytest.mark.parametrize("object_type", ["group_of_people", "unclassified", "cat"])
    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_unsupported_type(self, om_api, object_type):
        om_api.search(object_type).assert_status(422)

    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_invalid_pagination(self, om_api):
        om_api.search("face", {"pagination": {"pgoffset": "x"}}).assert_status(422)

    @endpoint(SERVICE, "POST", V3_SEARCH)
    def test_search_unauthorized(self, anon_om, bad_token):
        anon_om.with_token(bad_token).search("face").assert_unauthorized()


@allure.feature("object-manager")
@allure.story("search: поиск находит существующие объекты")
class TestSearchFindsKnownObjects:
    """Объект берётся в обход поиска (names -> GET по id) и ищется по его камере и времени.
    Ловит класс багов «поиск пустой, хотя объекты есть» (backend 2.0, split-таблицы)."""

    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(V2_SEARCH, marks=endpoint(SERVICE, "POST", V2_SEARCH), id="v2"),
            pytest.param(V3_SEARCH, marks=endpoint(SERVICE, "POST", V3_SEARCH), id="v3"),
        ],
    )
    def test_search_finds_object_by_camera_and_time(self, om_api, known_object, path):
        import datetime as dt

        ts = known_object["timestamp"]
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()  # noqa: E731
        body = {
            "timestamp_filters": {"timestamp_start": iso(ts - 60), "timestamp_end": iso(ts + 60)},
            "camera_filters": {"camera": [known_object["camera_id"]]},
            "pagination": {"pgoffset": 0, "pgsize": 100},
        }
        page = om_api.request("POST", path, path_params={"object_type": known_object["type"]}, json_body=body).assert_status(200).assert_contract().json()
        ids = {i["id"] for i in page["items"]}
        assert known_object["id"] in ids or known_object.get("parent_id") in ids, (
            f"объект {known_object['id']} ({known_object['type']}) не найден поиском по своей камере и времени, amount={page['pagination']['amount']}"
        )

    @endpoint(SERVICE, "POST", V3_SEARCH)
    @endpoint(SERVICE, "POST", V2_SEARCH)
    def test_v2_v3_consistent(self, om_api, known_object):
        body = {"orderings": {"timestamp": "timestamp desc"}, "pagination": {"pgoffset": 0, "pgsize": 20}}
        v2 = om_api.search_v2(known_object["type"], body).assert_status(200).json()
        v3 = om_api.search(known_object["type"], body).assert_status(200).json()
        assert v2["pagination"]["amount"] == v3["pagination"]["amount"]
        assert [i["id"] for i in v2["items"]] == [i["id"] for i in v3["items"]]

    @endpoint(SERVICE, "GET", "/object-manager/public/v3/objects/{object_id}")
    @endpoint(SERVICE, "GET", "/object-manager/public/objects/{object_id}")
    def test_get_v1_equals_v3(self, om_api, known_object):
        v1 = om_api.get_object_v1(known_object["id"]).assert_status(200).assert_contract().json()
        v3 = om_api.get_object(known_object["id"]).assert_status(200).assert_contract().json()
        assert v1 == v3, f"различия: {[k for k in set(v1) | set(v3) if v1.get(k) != v3.get(k)]}"


@allure.feature("object-manager")
@allure.story("search v2")
class TestSearchV2:
    @endpoint(SERVICE, "POST", V2_SEARCH)
    def test_search_v2(self, om_api):
        om_api.search_v2("face").assert_status(200).assert_contract().parse(PaginatedObjects)


@allure.feature("object-manager")
@allure.story("names")
class TestNames:
    @endpoint(SERVICE, "GET", "/object-manager/public/v2/names/{object_type}")
    def test_names(self, om_api):
        items = om_api.names("face", limit=5, offset=0).assert_status(200).assert_contract().json()
        assert len(items) <= 5

    @endpoint(SERVICE, "GET", "/object-manager/public/v2/names/{object_type}")
    def test_names_text_filter(self, om_api):
        items = om_api.names("face", text="zzz_no_such_name_zzz").assert_status(200).json()
        assert items == []


@allure.feature("object-manager")
@allure.story("filters")
class TestFilters:
    @endpoint(SERVICE, "GET", "/object-manager/public/search/filters/{object_type}")
    def test_filters_v1(self, om_api):
        body = om_api.filters_v1("face").assert_status(200).assert_contract().json()
        assert body["object_type"] == "face"
        assert body["filters"]

    @pytest.mark.parametrize("object_type", ["face", "vehicle", "person"])
    @endpoint(SERVICE, "POST", "/object-manager/public/v2/filters/{object_type}")
    def test_filters_v2(self, om_api, object_type):
        filters = om_api.filters(object_type).assert_status(200).assert_contract().parse(FiltersOrderingsSchema)
        assert filters.common_filters

    @pytest.mark.parametrize("widget_type", ["pie_chart", "hist_chart", "line_chart", "numeric"])
    @endpoint(SERVICE, "POST", "/object-manager/public/v2/filters/{object_type}/{widget_type}")
    def test_widget_filters(self, om_api, widget_type):
        om_api.widget_filters("face", widget_type).assert_status(200).assert_contract()

    @endpoint(SERVICE, "POST", "/object-manager/public/v2/filters/{object_type}/{widget_type}")
    def test_widget_filters_unknown_widget(self, om_api):
        om_api.widget_filters("face", "unknown_widget").assert_status(400, 422)
