"""
Smoke tests — verify the app starts and core pages are reachable.
These tests do not correspond to a specific user story; they guard the scaffold.
"""
from tests.conftest import make_evening, make_season


async def test_homepage_returns_200(client):
    """The public homepage must be accessible without authentication."""
    response = await client.get("/")
    assert response.status_code == 200


async def test_homepage_shows_no_evening_when_none_planned(client):
    """When no evenings are scheduled the homepage renders without errors."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "Geen komende avonden" in response.text


async def test_homepage_shows_next_evening(client, db_session):
    """When an active season and evening exist, the date appears on the homepage."""
    season = make_season(db_session)
    make_evening(db_session, season_id=season.id)

    response = await client.get("/")
    assert response.status_code == 200
    assert "Volgende avond" in response.text


async def test_offline_page_returns_200(client):
    """The offline fallback page must render."""
    response = await client.get("/offline")
    assert response.status_code == 200


async def test_privacy_page_returns_200(client):
    """The privacy policy page must be accessible without authentication."""
    response = await client.get("/privacy")
    assert response.status_code == 200


async def test_app_build():
    """Verify the FastAPI app object can be imported (build check)."""
    from app.main import app as application

    assert application is not None
