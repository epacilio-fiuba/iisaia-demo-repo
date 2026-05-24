def test_create_post_requires_existing_author(client, auth_headers):
    r = client.post(
        "/posts",
        json={"title": "Hola", "body": "Mundo", "author_id": 1},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_create_post_ok(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    r = client.post(
        "/posts",
        json={"title": "Hola", "body": "Mundo", "author_id": 1},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["id"] == 1


def test_list_posts(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    client.post(
        "/posts",
        json={"title": "Hola", "body": "Mundo", "author_id": 1},
        headers=auth_headers,
    )
    r = client.get("/posts")
    assert r.status_code == 200
    assert len(r.json()) == 1
