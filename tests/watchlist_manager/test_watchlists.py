import allure
import pytest

from framework import endpoint
from framework.data import nonexistent_int_id, unique_name
from services.object_manager.models import Predicate, PredicateList, Watchlist, WatchlistType

SERVICE = "object-manager"
WATCHLISTS = "/watchlist-manager/public/v1/watchlists"
WATCHLIST = "/watchlist-manager/public/v1/watchlists/{watchlist_id}"
WL_PREDICATES = "/watchlist-manager/public/v1/watchlists/{watchlist_id}/predicates"
PREDICATES = "/watchlist-manager/public/v1/predicates"
PREDICATE = "/watchlist-manager/public/v1/predicates/{predicate_id}"
COMPANY_PREDICATES = "/watchlist-manager/public/v1/company-predicates"


@allure.feature("watchlist-manager")
@allure.story("watchlists")
class TestWatchlists:
    @pytest.mark.smoke
    @pytest.mark.parametrize("object_type", [t.value for t in WatchlistType])
    @endpoint(SERVICE, "POST", WATCHLISTS)
    def test_create(self, watchlists_api, watchlist_factory, me, object_type):
        wl = Watchlist.model_validate(watchlist_factory(object_type=object_type))
        assert wl.object_type.value == object_type
        assert wl.created_user_id == me["id"]
        assert wl.deleted_at is None

    @endpoint(SERVICE, "POST", WATCHLISTS)
    def test_create_duplicate_name(self, watchlists_api, watchlist_factory):
        wl = watchlist_factory()
        watchlists_api.create_watchlist(wl["name"], wl["object_type"]).assert_status(400, 409)

    @pytest.mark.parametrize("object_type", ["person", "unknown"])
    @endpoint(SERVICE, "POST", WATCHLISTS)
    def test_create_unsupported_type(self, watchlists_api, object_type):
        watchlists_api.create_watchlist(unique_name("watchlist"), object_type).assert_validation_error("object_type")

    @endpoint(SERVICE, "POST", WATCHLISTS)
    def test_create_without_name(self, watchlists_api):
        watchlists_api.request("POST", WATCHLISTS, json_body={"object_type": "face"}).assert_validation_error("name")

    @endpoint(SERVICE, "POST", WATCHLISTS)
    def test_create_unauthorized(self, anon_watchlists, bad_token):
        anon_watchlists.with_token(bad_token).create_watchlist(unique_name("watchlist"), "face").assert_unauthorized()

    @endpoint(SERVICE, "PATCH", WATCHLIST)
    def test_rename(self, watchlists_api, watchlist_factory, me):
        wl = watchlist_factory()
        new_name = unique_name("watchlist_renamed")
        updated = watchlists_api.patch_watchlist(wl["id"], new_name).assert_status(200).assert_contract().json()
        assert updated["name"] == new_name
        assert updated["last_updated_user_id"] == me["id"]

    @pytest.mark.parametrize("name", ["x", "y" * 101], ids=["too_short", "too_long"])
    @endpoint(SERVICE, "PATCH", WATCHLIST)
    def test_rename_invalid_length(self, watchlists_api, watchlist_factory, name):
        # имя: 2..100 символов
        watchlists_api.patch_watchlist(watchlist_factory()["id"], name).assert_validation_error("name")

    @endpoint(SERVICE, "PATCH", WATCHLIST)
    def test_rename_not_found(self, watchlists_api):
        watchlists_api.patch_watchlist(nonexistent_int_id(), unique_name("x")).assert_error(404)

    @endpoint(SERVICE, "PATCH", WATCHLIST)
    def test_rename_to_existing_name(self, watchlists_api, watchlist_factory):
        a, b = watchlist_factory(), watchlist_factory()
        watchlists_api.patch_watchlist(b["id"], a["name"]).assert_status(400, 409)

    @endpoint(SERVICE, "DELETE", WATCHLIST)
    def test_delete(self, watchlists_api):
        wl = watchlists_api.create_watchlist(unique_name("watchlist"), "face").assert_status(201).json()
        watchlists_api.delete_watchlist(wl["id"]).assert_status(200)
        watchlists_api.patch_watchlist(wl["id"], unique_name("x")).assert_status(404)

    @endpoint(SERVICE, "DELETE", WATCHLIST)
    def test_delete_not_found(self, watchlists_api):
        watchlists_api.delete_watchlist(nonexistent_int_id()).assert_error(404)


@allure.feature("watchlist-manager")
@allure.story("predicates")
class TestPredicates:
    @pytest.mark.smoke
    @endpoint(SERVICE, "POST", PREDICATES)
    def test_create(self, predicate_factory, watchlist_factory):
        wl = watchlist_factory()
        pred = Predicate.model_validate(predicate_factory(watchlist_id=wl["id"]))
        assert pred.watchlist_id == wl["id"]
        assert pred.filter

    @endpoint(SERVICE, "POST", PREDICATES)
    def test_create_empty_filter(self, watchlists_api, watchlist_factory):
        wl = watchlist_factory()
        watchlists_api.create_predicate(wl["id"], {}).assert_validation_error("filter")

    @endpoint(SERVICE, "POST", PREDICATES)
    def test_create_for_unknown_watchlist(self, watchlists_api):
        watchlists_api.create_predicate(nonexistent_int_id(), {"name": "x"}).assert_error(404)

    @endpoint(SERVICE, "PATCH", PREDICATE)
    def test_modify(self, watchlists_api, predicate_factory):
        pred = predicate_factory()
        new_filter = {"person_age": [20, 30], "name": "autotest_updated"}
        updated = watchlists_api.patch_predicate(pred["id"], new_filter).assert_status(200).assert_contract().json()
        assert updated["filter"]["name"] == "autotest_updated"

    @endpoint(SERVICE, "PATCH", PREDICATE)
    def test_modify_not_found(self, watchlists_api):
        watchlists_api.patch_predicate(nonexistent_int_id(), {"name": "x"}).assert_error(404)

    @endpoint(SERVICE, "DELETE", PREDICATE)
    def test_delete(self, watchlists_api, watchlist_factory):
        wl = watchlist_factory()
        pred = watchlists_api.create_predicate(wl["id"], {"name": "autotest"}).assert_status(201).json()
        watchlists_api.delete_predicate(pred["id"]).assert_status(200)
        ids = {p["id"] for p in watchlists_api.watchlist_predicates(wl["id"]).json()["items"]}
        assert pred["id"] not in ids

    @endpoint(SERVICE, "DELETE", PREDICATE)
    def test_delete_not_found(self, watchlists_api):
        watchlists_api.delete_predicate(nonexistent_int_id()).assert_error(404)

    @endpoint(SERVICE, "POST", WL_PREDICATES)
    def test_watchlist_predicates(self, watchlists_api, watchlist_factory, predicate_factory):
        wl = watchlist_factory()
        created = [predicate_factory(watchlist_id=wl["id"])["id"] for _ in range(3)]
        page = watchlists_api.watchlist_predicates(wl["id"], ordering="created_at desc").assert_status(200).assert_contract().parse(PredicateList)
        assert [p.id for p in page.items] == list(reversed(created))
        assert page.pagination.amount == 3

    @endpoint(SERVICE, "POST", WL_PREDICATES)
    def test_watchlist_predicates_pagination(self, watchlists_api, watchlist_factory, predicate_factory):
        wl = watchlist_factory()
        for _ in range(3):
            predicate_factory(watchlist_id=wl["id"])
        page = watchlists_api.watchlist_predicates(wl["id"], pgoffset=1, pgsize=1).assert_status(200).json()
        assert len(page["items"]) == 1
        assert page["pagination"]["offset"] == 1

    @endpoint(SERVICE, "POST", WL_PREDICATES)
    def test_watchlist_predicates_not_found(self, watchlists_api):
        watchlists_api.watchlist_predicates(nonexistent_int_id()).assert_error(404)

    @endpoint(SERVICE, "POST", WL_PREDICATES)
    def test_watchlist_predicates_bad_ordering(self, watchlists_api, watchlist_factory):
        wl = watchlist_factory()
        watchlists_api.watchlist_predicates(wl["id"], ordering="name").assert_status(422)

    @endpoint(SERVICE, "POST", COMPANY_PREDICATES)
    def test_company_predicates_contains_created(self, watchlists_api, predicate_factory):
        pred = predicate_factory()
        page = watchlists_api.company_predicates(ordering="created_at desc", pgsize=50).assert_status(200).assert_contract().json()
        assert pred["id"] in {p["id"] for p in page["items"]}
