"""Every API route requires a verified Firebase token, except an explicit public allowlist.

The routes are read from the app's own OpenAPI description, so a new endpoint that forgets the
auth dependency fails here instead of shipping unauthenticated.
"""

import re

import pytest

from receipt_api.main import API_PREFIX

from .conftest import Env

PUBLIC = {("GET", f"{API_PREFIX}/health")}


def _routes() -> list[tuple[str, str]]:
    paths = Env().app.openapi()["paths"]
    return sorted(
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith(API_PREFIX)
        for method in operations
    )


ROUTES = _routes()


def _concrete(path: str, doc_id: str) -> str:
    return re.sub(r"\{[^}]+\}", doc_id, path)


def test_route_inventory_is_complete() -> None:
    # Guards the parametrised test below against silently testing nothing.
    assert len(ROUTES) >= 16
    assert ("DELETE", f"{API_PREFIX}/documents/{{document_id}}") in ROUTES


@pytest.mark.parametrize(("method", "path"), [r for r in ROUTES if r not in PUBLIC])
def test_route_rejects_missing_and_forged_tokens(env: Env, method: str, path: str) -> None:
    doc_id = env.add()  # a real document, so only the missing auth can cause the 401
    url = _concrete(path, doc_id)
    for headers in ({}, {"Authorization": "Bearer forged"}, {"Authorization": "Basic abc"}):
        resp = env.client.request(method, url, headers=headers, json={})
        assert resp.status_code == 401, (method, url, headers, resp.status_code)
        assert resp.headers.get("WWW-Authenticate") == "Bearer"
    assert env.repo.get(doc_id) is not None  # nothing was changed or deleted


@pytest.mark.parametrize(("method", "path"), [r for r in ROUTES if r not in PUBLIC and "{" in r[1]])
def test_route_hides_other_users_documents(env: Env, method: str, path: str) -> None:
    doc_id = env.add(user="user_B")
    resp = env.send(method, _concrete(path, doc_id), body={}, token="token-a")
    assert resp.status_code == 404, (method, path, resp.status_code)
    assert env.repo.get(doc_id) is not None


def test_public_routes_work_without_a_token(env: Env) -> None:
    for method, path in PUBLIC:
        assert env.client.request(method, path).status_code == 200
