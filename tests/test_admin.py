import pytest

from app import Movie, db


def get_movie(app, movie_id):
    with app.app_context():
        return db.session.get(Movie, movie_id)


@pytest.mark.parametrize(
    "method, path_template",
    [
        ("get", "/admin"),
        ("post", "/admin/upload"),
        ("post", "/admin/edit/{id}"),
        ("post", "/admin/delete/{id}"),
    ],
)
def test_non_admin_is_redirected_away(app, auth_client, csrf_token, movie_id, method, path_template):
    path = path_template.format(id=movie_id)
    kwargs = {}
    if method == "post":
        kwargs["data"] = {"title": "Hijacked", "csrf_token": csrf_token(auth_client, "/")}

    response = getattr(auth_client, method)(path, **kwargs)

    assert response.status_code == 302
    assert response.location.endswith("/")
    movie = get_movie(app, movie_id)
    assert movie is not None
    assert movie.title == "Test Movie"


def test_admin_dashboard_renders_tokens_for_every_form(admin_client, movie_id):
    html = admin_client.get("/admin").get_data(as_text=True)

    # upload, edit, delete and logout forms
    assert html.count('name="csrf_token"') >= 4


def test_admin_can_edit_movie_metadata(app, admin_client, csrf_token, movie_id):
    response = admin_client.post(
        f"/admin/edit/{movie_id}",
        data={"title": "Edited", "category": "Thriller", "csrf_token": csrf_token(admin_client, "/admin")},
    )

    assert response.status_code == 302
    movie = get_movie(app, movie_id)
    assert (movie.title, movie.category) == ("Edited", "Thriller")


def test_admin_can_delete_movie(app, admin_client, csrf_token, movie_id):
    response = admin_client.post(
        f"/admin/delete/{movie_id}",
        data={"csrf_token": csrf_token(admin_client, "/admin")},
    )

    assert response.status_code == 302
    assert get_movie(app, movie_id) is None


def test_editing_unknown_movie_returns_404(admin_client, csrf_token):
    response = admin_client.post(
        "/admin/edit/999",
        data={"title": "X", "csrf_token": csrf_token(admin_client, "/admin")},
    )
    assert response.status_code == 404
