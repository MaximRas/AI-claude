"""Самотесты инструментов анализа (без стенда и git)."""

import pytest

from tools.mr_impact import extract_routes, parse_unified_diff
from tools.spec_diff import diff_specs

pytestmark = pytest.mark.selftest

ROUTER_SRC = """
from fastapi import APIRouter
router = APIRouter(prefix="/svc/public/v1", tags=["x"])

@router.get("/items/{item_id}")
async def get_item(item_id: int):
    return load(item_id)

@router.post(
    "/items",
    status_code=201,
)
async def create_item(body: ItemIn):
    return save(body)
"""


def test_extract_routes_with_prefix():
    routes = {(r.method, r.path, r.func) for r in extract_routes(ROUTER_SRC, "api.py")}
    assert routes == {("GET", "/svc/public/v1/items/{item_id}", "get_item"), ("POST", "/svc/public/v1/items", "create_item")}


def test_parse_unified_diff_line_numbers():
    diff = """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -1,3 +1,4 @@
 a
-b
+B
+C
 d
"""
    fd = parse_unified_diff(diff)["x.py"]
    assert fd.added == {2, 3}
    assert fd.removed == {2}


def _spec(props, required=(), enum=None, extra_path=False):
    schemas = {"Item": {"type": "object", "properties": props, "required": list(required)}, "Kind": {"enum": enum or ["a"]}}
    paths = {"/items": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}}}}}}
    if extra_path:
        paths["/items/{id}"] = {"delete": {"parameters": [{"in": "path", "name": "id", "required": True, "schema": {"type": "integer"}}]}}
    return {"paths": paths, "components": {"schemas": schemas}}


def test_spec_diff_detects_fields_and_usage():
    old = _spec({"id": {"type": "integer"}, "kind": {"$ref": "#/components/schemas/Kind"}})
    new = _spec(
        {"id": {"type": "string"}, "kind": {"$ref": "#/components/schemas/Kind"}, "name": {"type": "string"}},
        required=["name"],
        enum=["a", "b"],
        extra_path=True,
    )
    report = diff_specs(old, new)
    assert [e["path"] for e in report["added_endpoints"]] == ["/items/{id}"]
    changes = {s["name"]: s for s in report["changed_schemas"]}
    assert any("+name" in c for c in changes["Item"]["changes"])
    assert any("integer -> string" in c for c in changes["Item"]["changes"])
    assert any("добавлены значения ['b']" in c for c in changes["Kind"]["changes"])
    assert changes["Kind"]["used_by"] == ["GET /items"], "Kind используется транзитивно через Item"
    assert report["changed_endpoints"][0]["path"] == "/items"


def test_spec_diff_ignores_descriptions():
    old = _spec({"id": {"type": "integer", "description": "old"}})
    new = _spec({"id": {"type": "integer", "description": "new", "title": "Id"}})
    assert not diff_specs(old, new)["has_changes"]


def test_layout_baseline_compare():
    from tools.layout_baseline import compare

    before = {
        "companies": {
            "1": {
                "errors": [],
                "layouts": {"L1": {"name": "a", "grid": [["w", 0, 0, 4, 4]], "is_shared": True, "access": [["company", "viewer", None]]}},
                "widgets": {"W1": {"name": "w", "is_shared": False}},
            }
        }
    }
    after = {
        "companies": {
            "1": {
                "errors": [],
                "layouts": {"L1": {"name": "a", "grid": [["w", 0, 0, 4, 5]], "is_shared": False, "access": []}, "L2": {"name": "new"}},
                "widgets": {},
            }
        }
    }
    problems = compare(before, after)
    assert any("grid" in p for p in problems)
    assert any("is_shared: True -> False" in p for p in problems)
    assert any("access" in p for p in problems)
    assert any("widget W1" in p and "пропал" in p for p in problems)
    assert not any("L2" in p for p in problems), "новые сущности не считаются расхождением"
    assert compare(before, before) == []
