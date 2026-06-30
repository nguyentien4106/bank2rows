from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlmodel import Session, SQLModel, create_engine, delete

from app.auth.dependencies import get_db
from app.core.config import settings
from app.core.db import init_db
from app.main import app
from app.models import Item, User
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers

# Run the whole suite against a dedicated, isolated database so it never
# touches the real application data. The destructive cleanup in the `db`
# fixture below only ever runs against this throwaway database.
TEST_DB_NAME = f"{settings.POSTGRES_DB}_test"


def _db_url(db_name: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        database=db_name,
    )


def _ensure_test_database() -> None:
    # Connect to the default maintenance database to create the test database
    # if it does not exist yet. CREATE DATABASE cannot run in a transaction,
    # so use an AUTOCOMMIT connection.
    admin_engine = create_engine(
        _db_url("postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_NAME},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()


_ensure_test_database()
test_engine = create_engine(_db_url(TEST_DB_NAME))
# `app.main` was imported above, so every model is registered on the shared
# SQLModel metadata; create the full schema on the test database.
SQLModel.metadata.create_all(test_engine)


def _get_test_db() -> Generator[Session, None, None]:
    with Session(test_engine) as session:
        yield session


# Make every request the app handles use the test database too.
app.dependency_overrides[get_db] = _get_test_db


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    with Session(test_engine) as session:
        init_db(session)
        yield session
        statement = delete(Item)
        session.execute(statement)
        statement = delete(User)
        session.execute(statement)
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
