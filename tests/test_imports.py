import io


def _csv(content: str) -> dict:
    return {"file": ("test.csv", io.BytesIO(content.encode("utf-8")), "text/csv")}


def test_import_requires_auth(client):
    r = client.post(
        "/import/users",
        files=_csv("name,email\nAna,a@x.com\n"),
        data={"mode": "atomic"},
    )
    assert r.status_code == 401


def test_import_invalid_resource(client, auth_headers):
    r = client.post(
        "/import/widgets",
        files=_csv("a,b\n1,2\n"),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_import_missing_column(client, auth_headers):
    r = client.post(
        "/import/users",
        files=_csv("name\nAna\n"),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "email" in r.json()["detail"]


def test_import_empty_csv(client, auth_headers):
    r = client.post(
        "/import/users",
        files=_csv("name,email\n"),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "empty csv"


def test_import_missing_file(client, auth_headers):
    r = client.post(
        "/import/users",
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 422  # FastAPI validation: file field required


def test_import_unknown_mode(client, auth_headers):
    r = client.post(
        "/import/users",
        files=_csv("name,email\nAna,a@x.com\n"),
        data={"mode": "weird"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_import_too_many_rows(client, auth_headers):
    body = "name,email\n" + "\n".join(
        f"User{i},user{i}@x.com" for i in range(1001)
    ) + "\n"
    r = client.post(
        "/import/users",
        files=_csv(body),
        data={"mode": "partial"},
        headers=auth_headers,
    )
    assert r.status_code == 413


def test_import_file_too_large(client, auth_headers):
    big = "name,email\n" + ("padding,padding@x.com\n" * 60000)  # > 1 MB
    r = client.post(
        "/import/users",
        files=_csv(big),
        data={"mode": "partial"},
        headers=auth_headers,
    )
    assert r.status_code == 413


def test_import_users_atomic_ok(client, auth_headers):
    csv = "name,email\nAna,a@x.com\nBob,b@x.com\nCar,c@x.com\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 3
    assert len(body["inserted"]) == 3
    assert body["skipped"] == []
    assert body["rolled_back"] is False
    assert len(client.get("/users").json()) == 3


def test_import_posts_atomic_ok(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "a@x.com"},
        headers=auth_headers,
    )
    csv = "title,body,author_id\nt1,b1,1\nt2,b2,1\n"
    r = client.post(
        "/import/posts",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["inserted"]) == 2


def test_import_users_partial_with_invalid(client, auth_headers):
    csv = "name,email\nAna,a@x.com\nBad,\nBob,b@x.com\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "partial"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["inserted"]) == 2
    assert body["skipped"][0]["reason"] == "missing_field"
    assert body["rolled_back"] is False
    assert len(client.get("/users").json()) == 2


def test_import_users_atomic_rolls_back_returns_422(client, auth_headers):
    csv = "name,email\nAna,a@x.com\nBad,\nBob,b@x.com\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["inserted"] == []
    assert body["rolled_back"] is True
    assert len(body["skipped"]) == 1
    assert client.get("/users").json() == []


def test_import_atomic_preserves_preexisting(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Pre", "email": "pre@x.com"},
        headers=auth_headers,
    )
    csv = "name,email\nAna,a@x.com\nBad,\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    users = client.get("/users").json()
    assert len(users) == 1
    assert users[0]["email"] == "pre@x.com"
    assert users[0]["id"] == 1
