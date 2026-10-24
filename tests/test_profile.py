import pytest

from app import ALLOWED_THEME_COLORS, User, db


def get_user(app, user_id):
    with app.app_context():
        return db.session.get(User, user_id)


def post_profile(client, csrf_token, **data):
    data["csrf_token"] = csrf_token(client, "/profile")
    return client.post("/profile", data=data)


@pytest.mark.parametrize("color", sorted(ALLOWED_THEME_COLORS))
def test_each_allowed_theme_color_is_accepted(app, auth_client, user_id, csrf_token, color):
    response = post_profile(auth_client, csrf_token, action="update_theme", theme_color=color)

    assert response.status_code == 302
    assert get_user(app, user_id).theme_color == color


def test_theme_color_is_case_insensitive(app, auth_client, user_id, csrf_token):
    post_profile(auth_client, csrf_token, action="update_theme", theme_color="#1ce783")

    assert get_user(app, user_id).theme_color == "#1CE783"


def test_profile_template_offers_only_allowed_colors(auth_client):
    html = auth_client.get("/profile").get_data(as_text=True)

    for color in ALLOWED_THEME_COLORS:
        assert f'name="theme_color" value="{color}"' in html


@pytest.mark.parametrize(
    "color",
    [
        "purple",
        "#123456",
        "",
        "red; background:url(https://attacker.example/x)",
        "#00E5FF; } body { display:none",
    ],
)
def test_invalid_theme_color_is_rejected_and_previous_color_kept(
    app, auth_client, user_id, csrf_token, color
):
    post_profile(auth_client, csrf_token, action="update_theme", theme_color="#FF007F")

    response = post_profile(auth_client, csrf_token, action="update_theme", theme_color=color)

    assert response.status_code == 302
    assert get_user(app, user_id).theme_color == "#FF007F"
    assert "Invalid theme color." in auth_client.get("/profile").get_data(as_text=True)


def test_missing_theme_color_is_rejected(app, auth_client, user_id, csrf_token):
    before = get_user(app, user_id).theme_color

    post_profile(auth_client, csrf_token, action="update_theme")

    assert get_user(app, user_id).theme_color == before


def test_profile_name_update(app, auth_client, user_id, csrf_token):
    response = post_profile(auth_client, csrf_token, action="update_profile", name="Renamed")

    assert response.status_code == 302
    assert get_user(app, user_id).name == "Renamed"


def test_user_cannot_self_upgrade_subscription(app, auth_client, user_id, csrf_token):
    post_profile(
        auth_client,
        csrf_token,
        action="update_subscription",
        subscription_tier="Premium",
    )

    assert get_user(app, user_id).subscription_tier == "Free"


def test_profile_page_has_no_subscription_form(auth_client):
    html = auth_client.get("/profile").get_data(as_text=True)

    assert "update_subscription" not in html
    assert "Subscription management is not enabled" in html
