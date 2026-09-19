import pytest
import pytest_asyncio
from dependencies.auth import (
    UserInfo,
    require_authentication,
    get_current_user_optional,
)


@pytest_asyncio.fixture
async def group_client(test_client_with_data):
    client, app = test_client_with_data
    actor = {"id": "alice"}
    app.dependency_overrides[require_authentication] = lambda: UserInfo(
        user_id=actor["id"], username=actor["id"], email=None, groups=[], claims={}
    )
    app.dependency_overrides[get_current_user_optional] = app.dependency_overrides[
        require_authentication
    ]
    yield client, actor
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_groups_http_lifecycle(group_client):
    client, actor = group_client
    response = await client.get("/groups/mine")
    assert response.status_code == 200
    a = response.json()
    assert response.headers["cache-control"] == "private, no-store"
    assert a["member_count"] == 1
    assert (await client.post("/groups", json={"name": "Other"})).status_code == 409
    assert (await client.put(f"/groups/{a['id']}", json={"name": "  Home  "})).json()[
        "name"
    ] == "Home"
    assert (
        await client.post("/user-ingredients", json={"ingredient_id": 8})
    ).status_code == 201
    actor["id"] = "bob"
    joined = await client.post("/groups/join", json={"invite_code": a["invite_code"]})
    assert joined.status_code == 200 and joined.json()["member_count"] == 2
    ingredients = await client.get(f"/groups/{a['id']}/ingredients")
    assert ingredients.json()["total_count"] == 2
    assert (await client.delete(f"/groups/{a['id']}/ingredients/1")).status_code == 400
    # Static bulk route must not be consumed as an integer ID.
    deleted = await client.request(
        "DELETE", f"/groups/{a['id']}/ingredients/bulk", json={"ingredient_ids": [1, 8]}
    )
    assert deleted.status_code == 200 and deleted.json()["removed_count"] == 2
    assert (
        await client.get(f"/groups/{a['id']}/ingredients/recommendations")
    ).status_code == 200
    assert (
        await client.post(
            f"/groups/{a['id']}/ingredients/bulk", json={"ingredient_ids": [2]}
        )
    ).status_code == 201
    assert (await client.post(f"/groups/{a['id']}/leave", json={})).status_code == 422
    left = await client.post(f"/groups/{a['id']}/leave", json={"copy_inventory": True})
    assert left.status_code == 200 and left.json()["id"] != a["id"]
    assert (await client.get("/user-ingredients")).json()["total_count"] == 1
    assert (await client.get(f"/groups/{a['id']}/ingredients")).status_code == 403
    assert (
        await client.get("/recipes/search", params={"inventory": True})
    ).status_code == 200


@pytest.mark.asyncio
async def test_group_mutation_errors(group_client):
    client, actor = group_client
    a = (await client.get("/groups/mine")).json()
    assert (
        await client.post("/groups/join", json={"invite_code": "z" * 12})
    ).status_code == 422
    assert (
        await client.post("/groups/join", json={"invite_code": "abcdef123456"})
    ).status_code == 404
    assert (
        await client.post(f"/groups/{a['id']}/leave", json={"copy_inventory": False})
    ).status_code == 409
    assert (await client.delete(f"/groups/{a['id']}/members/alice")).status_code == 400
    assert (await client.delete(f"/groups/{a['id']}/members/bob")).status_code == 404
    actor["id"] = "bob"
    assert (
        await client.post("/groups/join", json={"invite_code": a["invite_code"]})
    ).status_code == 200
    actor["id"] = "alice"
    assert (await client.delete(f"/groups/{a['id']}/members/bob")).status_code == 200
    rotated = (await client.post(f"/groups/{a['id']}/invite-code/regenerate")).json()
    assert rotated["invite_code"] != a["invite_code"]
    actor["id"] = "bob"
    assert (
        await client.post("/groups/join", json={"invite_code": a["invite_code"]})
    ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PUT", "/groups/999", {"name": "x"}),
        ("POST", "/groups/999/leave", {"copy_inventory": True}),
        ("DELETE", "/groups/999/members/other", None),
        ("POST", "/groups/999/invite-code/regenerate", None),
        ("GET", "/groups/999/ingredients", None),
        ("POST", "/groups/999/ingredients", {"ingredient_id": 1}),
        ("POST", "/groups/999/ingredients/bulk", {"ingredient_ids": [1]}),
        ("DELETE", "/groups/999/ingredients/bulk", {"ingredient_ids": [1]}),
        ("DELETE", "/groups/999/ingredients/1", None),
        ("GET", "/groups/999/ingredients/recommendations", None),
    ],
)
async def test_all_group_id_routes_require_membership(group_client, method, path, body):
    client, _ = group_client
    assert (await client.request(method, path, json=body)).status_code == 403


@pytest.mark.asyncio
async def test_groups_openapi_and_no_auth(test_client_memory_with_app):
    client, app = test_client_memory_with_app
    schema = app.openapi()
    assert "/groups/mine" in schema["paths"]
    for method, path, body in [
        ("PUT", "/groups/1", {"name": "Home"}),
        ("POST", "/groups/1/leave", {"copy_inventory": True}),
        ("DELETE", "/groups/1/members/other", None),
        ("POST", "/groups/1/invite-code/regenerate", None),
        ("GET", "/groups/1/ingredients", None),
        ("POST", "/groups/1/ingredients", {"ingredient_id": 1}),
        ("POST", "/groups/1/ingredients/bulk", {"ingredient_ids": [1]}),
        ("DELETE", "/groups/1/ingredients/bulk", {"ingredient_ids": [1]}),
        ("DELETE", "/groups/1/ingredients/1", None),
        ("GET", "/groups/1/ingredients/recommendations", None),
        ("GET", "/groups/mine", None),
        ("POST", "/groups", {"name": "Home"}),
        ("POST", "/groups/join", {"invite_code": "abcdef123456"}),
    ]:
        assert (await client.request(method, path, json=body)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_malformed_invite_not_logged(group_client, caplog):
    client, _ = group_client
    invite = "SECRET-invite-mistyped"
    response = await client.post("/groups/join", json={"invite_code": invite})
    assert response.status_code == 422
    assert invite.lower() not in caplog.text.lower()
