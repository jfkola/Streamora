import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

# app.py reads its configuration at import time, so the environment must be
# prepared before it is imported.
_TEST_DIR = tempfile.mkdtemp(prefix="streamora-tests-")
_DB_PATH = Path(_TEST_DIR, "test.db").as_posix()
os.environ["SECRET_KEY"] = "test-only-secret"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"

from flask_migrate import downgrade, upgrade  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from app import Movie, User, db  # noqa: E402
from app import app as flask_app  # noqa: E402

MIGRATIONS_DIR = str(Path(__file__).resolve().parent.parent / "migrations")
TOKEN_PATTERN = re.compile(
    r'name="csrf[-_]token" (?:value|content)="([^"]+)"'
)


def pytest_sessionfinish(session, exitstatus):
    with flask_app.app_context():
        db.engine.dispose()
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def _schema():
    """Build the schema once through the real migrations."""
    with flask_app.app_context():
        upgrade(directory=MIGRATIONS_DIR)
    yield
    with flask_app.app_context():
        downgrade(directory=MIGRATIONS_DIR, revision="base")


@pytest.fixture
def app(_schema):
    # CSRF stays enabled: the tests exist to prove it is enforced.
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf_token():
    """Return a function that fetches a page and extracts its CSRF token."""

    def fetch(client, path="/"):
        response = client.get(path)
        assert response.status_code == 200, path
        match = TOKEN_PATTERN.search(response.get_data(as_text=True))
        assert match, f"No CSRF token rendered on {path}"
        return match.group(1)

    return fetch


@pytest.fixture
def create_user(app):
    def create(username="alice", password="correct-horse", name="Alice Example",
               is_admin=False):
        with app.app_context():
            user = User(
                name=name,
                username=username,
                password=generate_password_hash(password),
                is_admin=is_admin,
            )
            db.session.add(user)
            db.session.commit()
            return user.id

    return create


@pytest.fixture
def login(csrf_token):
    def log_in(client, username="alice", password="correct-horse"):
        token = csrf_token(client, "/login")
        return client.post(
            "/login",
            data={"username": username, "password": password, "csrf_token": token},
        )

    return log_in


@pytest.fixture
def user_id(create_user):
    return create_user()


@pytest.fixture
def auth_client(client, user_id, login):
    response = login(client)
    assert response.status_code == 302
    return client


@pytest.fixture
def admin_client(client, create_user, login):
    create_user(username="admin", name="Admin User", is_admin=True)
    response = login(client, username="admin")
    assert response.status_code == 302
    return client


@pytest.fixture
def api_headers(csrf_token):
    """Return a function building the headers the frontend sends to the JSON API."""

    def build(client):
        return {"X-CSRFToken": csrf_token(client, "/")}

    return build


@pytest.fixture
def movie_id(app):
    with app.app_context():
        movie = Movie(
            title="Test Movie",
            category="Drama",
            video_url="https://res.cloudinary.com/demo/video/upload/test.mp4",
            thumbnail="https://res.cloudinary.com/demo/image/upload/test.jpg",
        )
        db.session.add(movie)
        db.session.commit()
        return movie.id
