import pytest
from fakeredis import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.redis import get_redis
from app.sql import Base, get_db

TEST_DATABASE_URL = "sqlite:///test_db.sqlite"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def client(db_session, fake_redis):
    # Dependency override for DB
    def override_get_db():
        yield db_session

    # Dependency override for Redis
    def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


#
# /auth/register
#

def test_auth_register_success(client):
    response = client.post("/auth/register", json={
        "username": "alice",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["id"] is not None


def test_auth_register_conflict(client):
    response = client.post("/auth/register", json={
        "username": "alice",
        "password": "password123"
    })
    assert response.status_code == 409
    assert response.json()["detail"] == "User with this username already exists"


#
# /auth/token
#

def test_auth_token_success(client):
    response = client.post("/auth/token", json={
        "username": "alice",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["access_token"] is not None


def test_auth_token_incorrect_credentials(client):
    response = client.post("/auth/token", json={
        "username": "alice",
        "password": "wrongpassword"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


@pytest.fixture
def token_for_alice(client):
    resp = client.post("/auth/token", json={
        "username": "alice",
        "password": "password123"
    })
    return resp.json()["access_token"]


#
# /links/shorten
#

def test_links_create_without_auth(client):
    response = client.post("/links/shorten", json={
        "url": "https://www.example.com",
        "expire_at": "2999-01-01T00:00:00"
    })

    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert data["id"] is not None


def test_links_create_without_auth_in_past(client):
    response = client.post("/links/shorten", json={
        "url": "https://www.example.com",
        "expire_at": "2023-01-01T00:00:00"
    })

    assert response.status_code == 400
    assert response.json()["detail"] == "expire_at must be in the future"


def test_links_create_alias(client, token_for_alice):
    response = client.post(
        "/links/shorten",
        json={
            "url": "https://www.example.com",
            "expire_at": "2999-01-01T00:00:00",
            "alias": "myalias"
        },
        headers={"Authorization": f"Bearer {token_for_alice}"}
    )

    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert data["id"] == "myalias"


def test_links_create_alias_conflict(client, token_for_alice):
    response = client.post(
        "/links/shorten",
        json={
            "url": "https://www.example2.com",
            "expire_at": "2999-01-01T00:00:00",
            "alias": "myalias"
        },
        headers={"Authorization": f"Bearer {token_for_alice}"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Alias already exists"


#
# /links
#


def test_links_list(client, token_for_alice):
    response = client.get("/links", headers={"Authorization": f"Bearer {token_for_alice}"})

    assert response.status_code == 200
    data = response.json()
    assert "links" in data

    assert len(data["links"]) == 1
    assert data["links"][0]["id"] == "myalias"
    assert data["links"][0]["url"] == "https://www.example.com"
    assert data["links"][0]["access_count"] == 0


#
# /links/short
#


def test_links_search(client, token_for_alice):
    response = client.get(
        "/links/search",
        params={"original_url": "example"},
        headers={"Authorization": f"Bearer {token_for_alice}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "links" in data

    assert len(data["links"]) == 1
    assert data["links"][0]["id"] == "myalias"
    assert data["links"][0]["url"] == "https://www.example.com"
    assert data["links"][0]["access_count"] == 0


#
# /links/{alias}
#

def test_links_redirect_by_alias(client):
    response = client.get("/links/myalias", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "https://www.example.com"


#
# /links/{alias}/stats
#


def test_links_stats_by_alias(client, token_for_alice):
    response = client.get("/links/myalias/stats", headers={"Authorization": f"Bearer {token_for_alice}"})

    assert response.status_code == 200

    data = response.json()
    assert data["id"] == "myalias"
    assert data["url"] == "https://www.example.com"
    assert data["access_count"] == 1


#
# /links/{alias} [PUT]
#

def test_update_link(client, token_for_alice):
    response = client.put(
        "/links/myalias",
        json={"url": "https://updated.example.com"},
        headers={"Authorization": f"Bearer {token_for_alice}"}
    )

    assert response.status_code == 204

    stats_resp = client.get("/links/myalias/stats", headers={"Authorization": f"Bearer {token_for_alice}"})

    assert stats_resp.status_code == 200

    data = stats_resp.json()
    assert data["id"] == "myalias"
    assert data["url"] == "https://updated.example.com"
    assert data["access_count"] == 1


#
# /links/{alias} [DELETE]
#


def test_delete_link(client, token_for_alice):
    response = client.delete(
        "/links/myalias",
        headers={"Authorization": f"Bearer {token_for_alice}"}
    )

    assert response.status_code == 204

    stats_resp = client.get("/links/myalias/stats", headers={"Authorization": f"Bearer {token_for_alice}"})
    assert stats_resp.status_code == 404
    assert stats_resp.json()["detail"] == "Link not found"
