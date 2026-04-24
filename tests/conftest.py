"""
Shared fixtures for all tests.

Usage in test files:
    from tests.conftest import *  # noqa — fixtures are auto-discovered by pytest
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    """Provide an isolated in-memory SQLite session for each test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest_asyncio.fixture
async def client(db_session):
    """Async HTTP client wired to the test database."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Helper factories ──────────────────────────────────────────────────────────

def make_member(
    db_session,
    voornaam="Test",
    achternaam="Lid",
    lidnummer="LID001",
    role="lid",
    training_eligible=False,
    oauth_sub=None,
):
    from app.models import Member

    member = Member(
        voornaam=voornaam,
        achternaam=achternaam,
        lidnummer=lidnummer,
        role=role,
        training_eligible=training_eligible,
        oauth_sub=oauth_sub,
    )
    db_session.add(member)
    db_session.commit()
    db_session.refresh(member)
    return member


def make_season(db_session, naam="2025-2026", actief=True):
    from datetime import date

    from app.models import Season

    season = Season(
        naam=naam,
        start_datum=date(2025, 9, 1),
        eind_datum=date(2026, 6, 30),
        actief=actief,
    )
    db_session.add(season)
    db_session.commit()
    db_session.refresh(season)
    return season


def make_evening(db_session, season_id, datum=None, type="regulier"):
    from datetime import date, timedelta

    from app.models import ClubEvening

    if datum is None:
        datum = date.today() + timedelta(days=7)

    evening = ClubEvening(datum=datum, type=type, season_id=season_id)
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)
    return evening
