import pytest

from app import MyList, WatchHistory, db


def post_json(client, api_headers, path, payload):
    return client.post(path, json=payload, headers=api_headers(client))


# ---------- /api/progress ----------

def test_progress_is_saved(app, auth_client, api_headers, movie_id, user_id):
    response = post_json(auth_client, api_headers, "/api/progress",
                         {"movie_id": movie_id, "timestamp": 42.5})

    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    with app.app_context():
        history = WatchHistory.query.filter_by(user_id=user_id, movie_id=movie_id).one()
        assert history.timestamp == 42.5


def test_progress_updates_existing_row(app, auth_client, api_headers, movie_id):
    post_json(auth_client, api_headers, "/api/progress", {"movie_id": movie_id, "timestamp": 10})
    post_json(auth_client, api_headers, "/api/progress", {"movie_id": movie_id, "timestamp": 50})

    with app.app_context():
        rows = WatchHistory.query.all()
        assert len(rows) == 1
        assert rows[0].timestamp == 50


def test_saved_progress_resumes_on_watch_page(auth_client, api_headers, movie_id):
    post_json(auth_client, api_headers, "/api/progress", {"movie_id": movie_id, "timestamp": 75})

    html = auth_client.get(f"/watch/{movie_id}").get_data(as_text=True)
    assert "const START_TIME = 75.0;" in html


@pytest.mark.parametrize(
    "payload",
    [
        {"movie_id": 1, "timestamp": -1},
        {"movie_id": 1, "timestamp": "nan"},
        {"movie_id": 1, "timestamp": "inf"},
        {"movie_id": 1, "timestamp": "abc"},
        {"movie_id": "abc", "timestamp": 3},
        {"movie_id": None, "timestamp": 3},
        {"movie_id": 1},
        {"timestamp": 3},
    ],
)
def test_progress_rejects_invalid_payloads(app, auth_client, api_headers, movie_id, payload):
    response = post_json(auth_client, api_headers, "/api/progress", payload)

    assert response.status_code == 400
    with app.app_context():
        assert WatchHistory.query.count() == 0


def test_progress_rejects_non_object_json(auth_client, api_headers):
    response = post_json(auth_client, api_headers, "/api/progress", [1, 2])
    assert response.status_code == 400


def test_progress_rejects_non_json_body(auth_client, api_headers):
    response = auth_client.post("/api/progress", data="not json", headers=api_headers(auth_client))
    assert response.status_code == 400


def test_progress_for_unknown_movie_returns_404(auth_client, api_headers):
    response = post_json(auth_client, api_headers, "/api/progress", {"movie_id": 999, "timestamp": 1})
    assert response.status_code == 404


def test_progress_requires_login(client, csrf_token, movie_id):
    response = client.post(
        "/api/progress",
        json={"movie_id": movie_id, "timestamp": 1},
        headers={"X-CSRFToken": csrf_token(client, "/")},
    )
    assert response.status_code == 302
    assert "/login" in response.location


# ---------- /api/mylist/toggle ----------

def test_mylist_toggle_adds_then_removes(app, auth_client, api_headers, movie_id):
    added = post_json(auth_client, api_headers, "/api/mylist/toggle", {"movie_id": movie_id})
    assert added.json == {"status": "added"}
    with app.app_context():
        assert MyList.query.count() == 1

    removed = post_json(auth_client, api_headers, "/api/mylist/toggle", {"movie_id": movie_id})
    assert removed.json == {"status": "removed"}
    with app.app_context():
        assert MyList.query.count() == 0


def test_mylist_appears_on_home_page(auth_client, api_headers, movie_id):
    post_json(auth_client, api_headers, "/api/mylist/toggle", {"movie_id": movie_id})

    html = auth_client.get("/").get_data(as_text=True)
    assert f"mylist-card-{movie_id}" in html


@pytest.mark.parametrize("payload", [{"movie_id": "abc"}, {"movie_id": None}, {}])
def test_mylist_rejects_invalid_payloads(auth_client, api_headers, payload):
    response = post_json(auth_client, api_headers, "/api/mylist/toggle", payload)
    assert response.status_code == 400


def test_mylist_rejects_non_object_json(auth_client, api_headers):
    response = post_json(auth_client, api_headers, "/api/mylist/toggle", [1])
    assert response.status_code == 400


def test_mylist_for_unknown_movie_returns_404(auth_client, api_headers):
    response = post_json(auth_client, api_headers, "/api/mylist/toggle", {"movie_id": 999})
    assert response.status_code == 404


def test_activity_is_isolated_per_user(app, client, create_user, login, api_headers, csrf_token, movie_id):
    create_user(username="alice")
    create_user(username="bob")

    login(client, username="alice")
    post_json(client, api_headers, "/api/mylist/toggle", {"movie_id": movie_id})
    client.post("/logout", data={"csrf_token": csrf_token(client, "/")})

    login(client, username="bob")
    response = post_json(client, api_headers, "/api/mylist/toggle", {"movie_id": movie_id})

    assert response.json == {"status": "added"}
    with app.app_context():
        assert MyList.query.count() == 2


# ---------- database constraints ----------

def test_duplicate_watch_history_is_blocked_by_database(app, user_id, movie_id):
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        db.session.add(WatchHistory(user_id=user_id, movie_id=movie_id))
        db.session.commit()
        db.session.add(WatchHistory(user_id=user_id, movie_id=movie_id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_duplicate_mylist_entry_is_blocked_by_database(app, user_id, movie_id):
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        db.session.add(MyList(user_id=user_id, movie_id=movie_id))
        db.session.commit()
        db.session.add(MyList(user_id=user_id, movie_id=movie_id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
