import importlib
import sys

import pytest
from werkzeug.security import check_password_hash

from app import User


def register(client, csrf_token, username="newuser", password="s3cret-pass", name="New User"):
    return client.post(
        "/register",
        data={
            "name": name,
            "username": username,
            "password": password,
            "csrf_token": csrf_token(client, "/register"),
        },
    )


def test_home_page_is_public(client):
    assert client.get("/").status_code == 200


def test_registration_creates_user_with_hashed_password(app, client, csrf_token):
    response = register(client, csrf_token)

    assert response.status_code == 302
    assert response.location.endswith("/login")
    with app.app_context():
        user = User.query.filter_by(username="newuser").one()
        assert user.password != "s3cret-pass"
        assert check_password_hash(user.password, "s3cret-pass")
        assert user.subscription_tier == "Free"
        assert user.is_admin is False


def test_duplicate_username_is_rejected(app, client, csrf_token, user_id):
    response = register(client, csrf_token, username="alice")

    assert response.status_code == 302
    assert response.location.endswith("/register")
    with app.app_context():
        assert User.query.filter_by(username="alice").count() == 1


def test_login_with_valid_credentials(client, user_id, login):
    response = login(client)

    assert response.status_code == 302
    assert client.get("/profile").status_code == 200


def test_login_with_wrong_password_fails(client, user_id, login):
    response = login(client, password="wrong-password")

    assert response.status_code == 200
    assert "Invalid username or password." in response.get_data(as_text=True)
    assert client.get("/profile").status_code == 302


def test_login_with_unknown_user_fails(client, login):
    response = login(client, username="nobody")

    assert "Invalid username or password." in response.get_data(as_text=True)


def test_logout_requires_post(auth_client):
    assert auth_client.get("/logout").status_code == 405


def test_logout_with_token_ends_session(auth_client, csrf_token):
    response = auth_client.post("/logout", data={"csrf_token": csrf_token(auth_client, "/")})

    assert response.status_code == 302
    assert auth_client.get("/profile").status_code == 302


def test_protected_pages_redirect_anonymous_users_to_login(client, movie_id):
    for path in ("/profile", f"/watch/{movie_id}", "/admin"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.location, path


def test_app_refuses_to_start_without_secret_key(monkeypatch):
    # Re-import app.py with no SECRET_KEY and no .env file to fall back on.
    # monkeypatch restores the original module and environment afterwards.
    monkeypatch.delenv("SECRET_KEY")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delitem(sys.modules, "app")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        importlib.import_module("app")
