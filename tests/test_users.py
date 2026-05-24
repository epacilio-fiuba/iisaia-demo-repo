def test_list_users_empty(client):
    r = client.get("/users")
    assert r.status_code == 200
    assert r.json() == []


def test_create_user_requires_auth(client):
    r = client.post("/users", json={"name": "Ana", "email": "ana@example.com"})
    assert r.status_code == 401


def test_create_user_ok(client, auth_headers):
    r = client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["name"] == "Ana"


def test_get_user_by_id(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    r = client.get("/users/1")
    assert r.status_code == 200
    assert r.json()["name"] == "Ana"


def test_get_user_not_found(client):
    r = client.get("/users/999")
    assert r.status_code == 404
