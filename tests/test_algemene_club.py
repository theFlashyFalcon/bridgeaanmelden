"""
De algemene club ("Algemeen"): iedereen is er automatisch lid van.

Evenementen die een admin in deze club aanmaakt, zijn zichtbaar voor alle
gebruikers — ook voor leden zonder enige clubkoppeling.
"""
from tests.conftest import make_member
from tests.test_use_cases import (
    _set_auth,
    make_club,
    make_evening_for_club,
    make_member_club,
    make_season_for_club,
)


def make_algemene_club(db_session, naam="Algemeen"):
    from app.models import Club

    club = Club(naam=naam, is_algemeen=True)
    db_session.add(club)
    db_session.commit()
    db_session.refresh(club)
    return club


# ── Automatisch lidmaatschap ──────────────────────────────────────────────────

async def test_lid_zonder_koppeling_is_lid_van_algemene_club(db_session):
    from app.auth import get_member_club_ids, is_member_of_club

    algemeen = make_algemene_club(db_session)
    andere = make_club(db_session, naam="BC Besloten")
    member = make_member(db_session, lidnummer="ALG-1")

    assert is_member_of_club(member, algemeen.id, db_session)
    assert not is_member_of_club(member, andere.id, db_session)
    assert algemeen.id in get_member_club_ids(member, db_session)


async def test_expliciete_koppeling_algemene_club_geen_dubbel_id(db_session):
    from app.auth import get_member_club_ids

    algemeen = make_algemene_club(db_session)
    member = make_member(db_session, lidnummer="ALG-2")
    make_member_club(db_session, member.id, algemeen.id)

    ids = get_member_club_ids(member, db_session)
    assert ids.count(algemeen.id) == 1


# ── Zichtbaarheid van algemene evenementen ────────────────────────────────────

async def test_algemeen_event_zichtbaar_voor_iedereen_op_homepage(client, db_session):
    from app.auth import get_current_user
    from app.main import app

    algemeen = make_algemene_club(db_session)
    besloten = make_club(db_session, naam="BC Besloten")
    season_alg = make_season_for_club(db_session, algemeen.id)
    season_besloten = make_season_for_club(db_session, besloten.id, naam="2025-2026 B")
    make_evening_for_club(db_session, season_alg.id, algemeen.id)
    besloten_event = make_evening_for_club(db_session, season_besloten.id, besloten.id)
    besloten_event.naam = "Geheime Clubavond"
    algemeen_event = db_session.query(type(besloten_event)).filter_by(club_id=algemeen.id).first()
    algemeen_event.naam = "Zomerdrive Algemeen"
    db_session.commit()

    member = make_member(db_session, lidnummer="ALG-3")  # geen enkele clubkoppeling
    app.dependency_overrides[get_current_user] = lambda: member

    response = await client.get("/")
    assert response.status_code == 200
    assert "Zomerdrive Algemeen" in response.text
    assert "Geheime Clubavond" not in response.text


async def test_deelnemers_algemeen_event_toegankelijk_zonder_koppeling(client, db_session):
    from app.main import app

    algemeen = make_algemene_club(db_session)
    season = make_season_for_club(db_session, algemeen.id)
    evening = make_evening_for_club(db_session, season.id, algemeen.id)

    member = make_member(db_session, lidnummer="ALG-4")
    _set_auth(app, member=member)

    response = await client.get(f"/deelnemers/{evening.id}")
    assert response.status_code == 200


async def test_deelnemers_besloten_event_blijft_afgeschermd(client, db_session):
    from app.main import app

    make_algemene_club(db_session)
    besloten = make_club(db_session, naam="BC Besloten")
    season = make_season_for_club(db_session, besloten.id)
    evening = make_evening_for_club(db_session, season.id, besloten.id)

    member = make_member(db_session, lidnummer="ALG-5")
    _set_auth(app, member=member)

    response = await client.get(f"/deelnemers/{evening.id}")
    assert response.status_code == 403


# ── Beheer ────────────────────────────────────────────────────────────────────

async def test_algemene_club_niet_verwijderbaar(client, db_session):
    from app.main import app
    from app.models import Club

    algemeen = make_algemene_club(db_session)
    admin = make_member(db_session, role="admin", lidnummer="ADM-1")
    _set_auth(app, admin=admin)

    response = await client.post(f"/beheer/clubs/{algemeen.id}/verwijder", data={"_csrf_token": "x"})
    assert response.status_code == 302
    assert "fout=algemeen" in response.headers["location"]
    assert db_session.query(Club).filter(Club.id == algemeen.id).first() is not None


async def test_wedstrijdleider_rol_op_algemene_club_geeft_geen_beheerrechten(db_session):
    """
    Een MemberClub-rij met rol wedstrijdleider gekoppeld aan de algemene club
    mag daar geen beheerrechten aan ontlenen — alleen globale admins mogen de
    algemene club beheren.
    """
    from app.auth import can_manage_club

    algemeen = make_algemene_club(db_session)
    andere = make_club(db_session, naam="BC Andere")
    wl = make_member(db_session, lidnummer="ALG-WL")
    make_member_club(db_session, wl.id, algemeen.id, role="wedstrijdleider")
    make_member_club(db_session, wl.id, andere.id, role="wedstrijdleider")

    assert not can_manage_club(wl, algemeen.id, db_session)
    assert can_manage_club(wl, andere.id, db_session)
