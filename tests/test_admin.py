import os
import tempfile
from io import BytesIO

import cloudinary.uploader
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


# ---------- media uploads ----------

@pytest.fixture
def cloudinary_mock(monkeypatch):
    """Replace Cloudinary with fakes and record what the upload route sends."""
    calls = {"upload_large": [], "upload": [], "temp_paths": []}

    def fake_upload_large(path, **kwargs):
        assert os.path.exists(path), "video must be on disk while uploading"
        calls["upload_large"].append((path, kwargs))
        return {"secure_url": "https://res.cloudinary.com/demo/video/upload/new.mp4"}

    def fake_upload(file, **kwargs):
        calls["upload"].append(kwargs)
        kind = kwargs["resource_type"]
        return {"secure_url": f"https://res.cloudinary.com/demo/{kind}/upload/new"}

    real_mkstemp = tempfile.mkstemp

    def tracking_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        calls["temp_paths"].append(path)
        return fd, path

    monkeypatch.setattr(cloudinary.uploader, "upload_large", fake_upload_large)
    monkeypatch.setattr(cloudinary.uploader, "upload", fake_upload)
    monkeypatch.setattr(tempfile, "mkstemp", tracking_mkstemp)
    return calls


def upload(client, csrf_token, video="movie.mp4", thumbnail="poster.jpg",
           subtitle=None, title="New Movie", category="Action"):
    data = {"title": title, "category": category}
    if video:
        data["video"] = (BytesIO(b"fake video bytes"), video)
    if thumbnail:
        data["thumbnail"] = (BytesIO(b"fake image bytes"), thumbnail)
    if subtitle:
        data["subtitle"] = (BytesIO(b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"), subtitle)
    return client.post(
        "/admin/upload",
        data=data,
        content_type="multipart/form-data",
        headers={"X-CSRFToken": csrf_token(client, "/admin")},
    )


def movie_count(app):
    with app.app_context():
        return Movie.query.count()


def test_valid_upload_creates_one_movie(app, admin_client, csrf_token, cloudinary_mock):
    response = upload(admin_client, csrf_token, subtitle="captions.vtt")

    assert response.status_code == 200
    assert response.json == {"message": "Movie uploaded successfully!"}
    with app.app_context():
        movie = Movie.query.one()
        assert (movie.title, movie.category) == ("New Movie", "Action")
        assert movie.video_url.endswith("/video/upload/new.mp4")
        assert movie.thumbnail.endswith("/image/upload/new")
        assert movie.subtitle.endswith("/raw/upload/new")
    assert [c["resource_type"] for c in cloudinary_mock["upload"]] == ["image", "raw"]


def test_upload_strips_title_and_category(app, admin_client, csrf_token, cloudinary_mock):
    upload(admin_client, csrf_token, title="  Padded  ", category="  Drama ")

    with app.app_context():
        movie = Movie.query.one()
        assert (movie.title, movie.category) == ("Padded", "Drama")


def test_temp_file_is_removed_after_success(admin_client, csrf_token, cloudinary_mock):
    upload(admin_client, csrf_token)

    assert len(cloudinary_mock["temp_paths"]) == 1
    assert not os.path.exists(cloudinary_mock["temp_paths"][0])


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"video": None}, "Video and thumbnail files are required."),
        ({"thumbnail": None}, "Video and thumbnail files are required."),
        ({"video": "movie.exe"}, "Unsupported video format."),
        ({"video": "movie"}, "Unsupported video format."),
        ({"video": "movie.mp4.php"}, "Unsupported video format."),
        ({"thumbnail": "poster.svg"}, "Unsupported thumbnail format."),
        ({"subtitle": "captions.html"}, "Unsupported subtitle format."),
        ({"title": ""}, "Title and category are required."),
        ({"title": "   "}, "Title and category are required."),
        ({"category": ""}, "Title and category are required."),
    ],
)
def test_invalid_upload_is_rejected_before_cloudinary(
    app, admin_client, csrf_token, cloudinary_mock, overrides, message
):
    response = upload(admin_client, csrf_token, **overrides)

    assert response.status_code == 400
    assert response.json == {"error": message}
    assert movie_count(app) == 0
    assert cloudinary_mock["upload_large"] == []
    assert cloudinary_mock["upload"] == []
    assert cloudinary_mock["temp_paths"] == []


def test_extensions_are_case_insensitive(app, admin_client, csrf_token, cloudinary_mock):
    response = upload(admin_client, csrf_token, video="MOVIE.MP4", thumbnail="Poster.PNG")

    assert response.status_code == 200
    assert movie_count(app) == 1


def test_cloudinary_failure_returns_generic_error(
    app, admin_client, csrf_token, cloudinary_mock, monkeypatch
):
    def failing_upload_large(path, **kwargs):
        raise RuntimeError("api_secret=SUPER-SECRET connection refused")

    monkeypatch.setattr(cloudinary.uploader, "upload_large", failing_upload_large)

    response = upload(admin_client, csrf_token)

    assert response.status_code == 500
    assert response.json == {"error": "Media upload failed."}
    assert "SUPER-SECRET" not in response.get_data(as_text=True)
    assert movie_count(app) == 0
    assert len(cloudinary_mock["temp_paths"]) == 1
    assert not os.path.exists(cloudinary_mock["temp_paths"][0])


def test_thumbnail_failure_returns_generic_error(
    app, admin_client, csrf_token, cloudinary_mock, monkeypatch
):
    def failing_upload(file, **kwargs):
        raise RuntimeError("thumbnail rejected")

    monkeypatch.setattr(cloudinary.uploader, "upload", failing_upload)

    response = upload(admin_client, csrf_token)

    assert response.status_code == 500
    assert response.json == {"error": "Media upload failed."}
    assert movie_count(app) == 0
    assert not os.path.exists(cloudinary_mock["temp_paths"][0])
