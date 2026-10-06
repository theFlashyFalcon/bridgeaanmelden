"""
Tests voor "Toevoegen voor onbepaalde tijd" bij het handmatig toevoegen van
een paar op /beheer/af-aanmeldingen/{event_id}: koppelt (indien mogelijk) de
ingevulde namen aan bestaande lid-accounts en meldt hen definitief aan voor
elke (toekomstige) avond van hetzelfde type bij deze club.
"""
from datetime import date, timedelta

from tests.conftest import make_member, make_season


def make_club(db_session, naam="BC Test"):
    from app.models import Club
    club = Club(naam=naam)
    db_session.add(club)
    db_session.commit()
    db_session.refresh(club)
    return club


def make_member_club(db_session, member_id, club_id, role="lid"):
    from app.models import MemberClub
    mc = MemberClub(member_id=member_id, club_id=club_id, role=role)
    db_session.add(mc)
    db_session.commit()
    return mc


def make_evening(db_session, season_id, club_id=None, ev_type="clubavond",
                  datum=None, deelnemers_type="paren"):
    from app.models import ClubEvening
    if datum is None:
        datum = date.today() + timedelta(days=7)
    ev = ClubEvening(datum=datum, type=ev_type, season_id=season_id,
                      club_id=club_id, deelnemers_type=deelnemers_type)
    db_session.add(ev)
    db_session.commit()
    db_session.refresh(ev)
    return ev


def _no_csrf(app):
    from app.csrf import require_csrf
    app.dependency_overrides[require_csrf] = lambda: None


def _set_auth(app, wl):
    from app.auth import get_current_user, require_auth, require_wedstrijdleider
    _no_csrf(app)
    app.dependency_overrides[require_wedstrijdleider] = lambda: wl
    app.dependency_overrides[require_auth] = lambda: wl
    app.dependency_overrides[get_current_user] = lambda: wl


def _wl_met_club(db_session, naam="BC Test"):
    club = make_club(db_session, naam=naam)
    wl = make_member(db_session, voornaam="Wies", achternaam="Leider",
                      lidnummer="PERMWL1", role="wedstrijdleider")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    return club, wl


async def test_beide_spelers_met_lidnummer_worden_gekoppeld(client, db_session):
    from app.main import app
    from app.models import RecurringRegistration, Registration

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    speler1 = make_member(db_session, voornaam="Jan", achternaam="Jansen", lidnummer="PERM001")
    speler2 = make_member(db_session, voornaam="Piet", achternaam="Pietersen", lidnummer="PERM002")
    make_member_club(db_session, speler1.id, club.id)
    make_member_club(db_session, speler2.id, club.id)
    ev = make_evening(db_session, season.id, club_id=club.id)
    # Een tweede, verder in de toekomst liggende avond van hetzelfde type moet ook meegenomen worden.
    ev2 = make_evening(db_session, season.id, club_id=club.id, datum=date.today() + timedelta(days=21))

    _set_auth(app, wl)
    response = await client.post(
        f"/beheer/af-aanmeldingen/{ev.id}/toevoegen-permanent",
        data={
            "naam_1": "Jan Jansen", "lidnummer_1": "PERM001",
            "naam_2": "Piet Pietersen", "lidnummer_2": "PERM002",
        },
    )
    assert response.status_code == 302
    assert "permanent_toegevoegd=2" in response.headers["location"]

    regs1 = db_session.query(Registration).filter(Registration.person1_id == speler1.id).all()
    regs2 = db_session.query(Registration).filter(Registration.person1_id == speler2.id).all()
    assert {r.evening_id for r in regs1} == {ev.id, ev2.id}
    assert {r.evening_id for r in regs2} == {ev.id, ev2.id}
    assert all(r.partner_naam == "Piet Pietersen" for r in regs1)
    assert all(r.partner_naam == "Jan Jansen" for r in regs2)

    rr_count = db_session.query(RecurringRegistration).filter(
        RecurringRegistration.actief == True  # noqa: E712
    ).count()
    assert rr_count == 2


async def test_eenzijdige_match_registreert_alleen_dat_lid(client, db_session):
    from app.main import app
    from app.models import RecurringRegistration, Registration

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    speler1 = make_member(db_session, voornaam="Jan", achternaam="Jansen", lidnummer="PERM003")
    make_member_club(db_session, speler1.id, club.id)
    ev = make_evening(db_session, season.id, club_id=club.id)

    _set_auth(app, wl)
    response = await client.post(
        f"/beheer/af-aanmeldingen/{ev.id}/toevoegen-permanent",
        data={"naam_1": "Jan Jansen", "lidnummer_1": "PERM003", "naam_2": "Onbekende Gast"},
    )
    assert response.status_code == 302
    assert "permanent_toegevoegd=1" in response.headers["location"]

    regs = db_session.query(Registration).filter(Registration.person1_id == speler1.id).all()
    assert len(regs) == 1
    assert regs[0].partner_naam == "Onbekende Gast"
    assert db_session.query(RecurringRegistration).filter(
        RecurringRegistration.member_id == speler1.id
    ).count() == 1


async def test_geen_match_registreert_toch_als_niet_lid_paar(client, db_session):
    from app.main import app
    from app.models import ManualPair, RecurringManualPair, RecurringRegistration, Registration

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id)
    # Tweede, verder in de toekomst liggende avond van hetzelfde type moet ook meegenomen worden.
    ev2 = make_evening(db_session, season.id, club_id=club.id, datum=date.today() + timedelta(days=21))

    _set_auth(app, wl)
    response = await client.post(
        f"/beheer/af-aanmeldingen/{ev.id}/toevoegen-permanent",
        data={"naam_1": "Onbekende Speler", "naam_2": "Nog Een Onbekende"},
    )
    assert response.status_code == 302
    assert "permanent_toegevoegd=0" in response.headers["location"]
    # Geen lid-accounts gekoppeld, dus geen Registration/RecurringRegistration...
    assert db_session.query(Registration).count() == 0
    assert db_session.query(RecurringRegistration).count() == 0
    # ...maar wel een handmatige aanmelding voor elke (toekomstige) avond, plus
    # een herhaalaanmelding zodat nieuwe avonden automatisch meekomen.
    pairs = db_session.query(ManualPair).all()
    assert {p.evening_id for p in pairs} == {ev.id, ev2.id}
    assert all(p.naam_1 == "Onbekende Speler" and p.naam_2 == "Nog Een Onbekende" for p in pairs)
    assert db_session.query(RecurringManualPair).filter(
        RecurringManualPair.actief == True  # noqa: E712
    ).count() == 1


async def test_niet_beschikbaar_voor_viertallen(client, db_session):
    from app.main import app

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="viertallen")

    _set_auth(app, wl)
    response = await client.post(
        f"/beheer/af-aanmeldingen/{ev.id}/toevoegen-permanent",
        data={"naam_1": "Jan Jansen"},
    )
    assert response.status_code == 400
