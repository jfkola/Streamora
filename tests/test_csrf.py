"""Every state-changing route must reject requests without a valid CSRF token."""

import pytest


def test_csrf_protection_is_enabled(app):
    assert app.config["WTF_CSRF_ENABLED"] is True


@pytest.mark.parametrize("path", ["/", "/login", "/register"])
def test_public_pages_render_csrf_token(client, csrf_token, path):
    assert csrf_token(client, path)


def test_watch_page_renders_csrf_meta_tag(auth_client, csrf_token, movie_id):
    assert csrf_token(auth_client, f"/watch/{movie_id}")


def test_register_without_token_is_rejected(client):
    response = client.post(
        "/register",
        data={"name": "A", "username": "a", "password": "p"},
    )
    assert response.status_code == 400


def test_login_without_token_is_rejected(client, user_id):
    response = client.post(
        "/login",
        data={"username": "alice", "password": "correct-horse"},
    )
    assert response.status_code == 400


def test_invalid_token_is_rejected(client, user_id):
    response = client.post(
        "/login",
        data={"username": "alice", "password": "correct-horse", "csrf_token": "forged"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "path, data",
    [
        ("/logout", {}),
        ("/profile", {"action": "update_profile", "name": "X"}),
        ("/profile", {"action": "update_theme", "theme_color": "#00E5FF"}),
    ],
)
def test_authenticated_forms_without_token_are_rejected(auth_client, path, data):
    assert auth_client.post(path, data=data).status_code == 400


@pytest.mark.parametrize("path", ["/api/progress", "/api/mylist/toggle"])
def test_json_api_without_token_header_is_rejected(auth_client, movie_id, path):
    response = auth_client.post(path, json={"movie_id": movie_id, "timestamp": 5})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "path_template",
    ["/admin/upload", "/admin/edit/{id}", "/admin/delete/{id}"],
)
def test_admin_routes_without_token_are_rejected(admin_client, movie_id, path_template):
    response = admin_client.post(path_template.format(id=movie_id), data={"title": "Z"})
    assert response.status_code == 400
