"""
Tests voor het handmatig verwijderen (afmelden) van een reguliere aanmelding
door de wedstrijdleider vanaf /beheer/af-aanmeldingen/{event_id}: de aanmelding
wordt op afgemeld gezet en de betrokken lid-account(s) krijgen een bericht.
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


def make_registration(db_session, evening_id, person1_id, partner_naam=None,
                       person2_id=None, status="aangemeld"):
    from app.models import Registration, RegistrationType
    reg = Registration(
        evening_id=evening_id, person1_id=person1_id, person2_id=person2_id,
        partner_naam=partner_naam, type=RegistrationType.vast, status=status,
    )
    db_session.add(reg)
    db_session.commit()
    db_session.refresh(reg)
    return reg


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
                      lidnummer="VERWWL1", role="wedstrijdleider")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    return club, wl


async def test_wl_meldt_paar_af_en_speler_krijgt_bericht(client, db_session):
    from app.main import app
    from app.models import Bericht, Registration, RegistrationStatus

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    speler = make_member(db_session, voornaam="Jan", achternaam="Jansen", lidnummer="VERW001")
    make_member_club(db_session, speler.id, club.id)
    ev = make_evening(db_session, season.id, club_id=club.id)
    reg = make_registration(db_session, ev.id, speler.id, partner_naam="Piet Pietersen")

    _set_auth(app, wl)
    response = await client.post(f"/beheer/af-aanmeldingen/{ev.id}/reg/{reg.id}/verwijder")
    assert response.status_code == 302
    assert "paar_verwijderd=1" in response.headers["location"]

    db_session.refresh(reg)
    assert reg.status == RegistrationStatus.afgemeld
    assert reg.partner_naam is None

    bericht = db_session.query(Bericht).filter(
        Bericht.ontvanger_id == speler.id, Bericht.afzender_id == wl.id
    ).first()
    assert bericht is not None
    assert "afgemeld" in bericht.tekst.lower()


async def test_wl_meldt_paar_af_beide_accounts_krijgen_bericht(client, db_session):
    from app.main import app
    from app.models import Bericht

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    speler1 = make_member(db_session, voornaam="Jan", achternaam="Jansen", lidnummer="VERW002")
    speler2 = make_member(db_session, voornaam="Piet", achternaam="Pietersen", lidnummer="VERW003")
    make_member_club(db_session, speler1.id, club.id)
    make_member_club(db_session, speler2.id, club.id)
    ev = make_evening(db_session, season.id, club_id=club.id)
    reg = make_registration(db_session, ev.id, speler1.id, person2_id=speler2.id)

    _set_auth(app, wl)
    await client.post(f"/beheer/af-aanmeldingen/{ev.id}/reg/{reg.id}/verwijder")

    assert db_session.query(Bericht).filter(Bericht.ontvanger_id == speler1.id).count() == 1
    assert db_session.query(Bericht).filter(Bericht.ontvanger_id == speler2.id).count() == 1


async def test_wl_zonder_toegang_krijgt_403(client, db_session):
    from app.main import app

    club_a, wl_a = _wl_met_club(db_session, naam="Club A")
    club_b = make_club(db_session, naam="Club B")
    season = make_season(db_session)
    speler = make_member(db_session, voornaam="Jan", achternaam="Jansen", lidnummer="VERW004")
    make_member_club(db_session, speler.id, club_b.id)
    ev = make_evening(db_session, season.id, club_id=club_b.id)
    reg = make_registration(db_session, ev.id, speler.id)

    _set_auth(app, wl_a)
    response = await client.post(f"/beheer/af-aanmeldingen/{ev.id}/reg/{reg.id}/verwijder")
    assert response.status_code == 403


async def test_speler_kan_zichzelf_na_afmelden_door_wl_opnieuw_aanmelden(client, db_session):
    """Acceptatiecriterium: nadat de WL een paar via het kruisje afmeldt, kan
    de speler zichzelf gewoon weer aanmelden voor diezelfde avond."""
    from app.auth import get_current_user, require_auth
    from app.main import app
    from app.models import Registration, RegistrationStatus

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    speler = make_member(db_session, voornaam="Jan", achternaam="Jansen", lidnummer="VERW005")
    make_member_club(db_session, speler.id, club.id)
    ev = make_evening(db_session, season.id, club_id=club.id)
    reg = make_registration(db_session, ev.id, speler.id, partner_naam="Piet Pietersen")

    _set_auth(app, wl)
    response = await client.post(f"/beheer/af-aanmeldingen/{ev.id}/reg/{reg.id}/verwijder")
    assert response.status_code == 302

    # Wissel naar de speler zelf en meld opnieuw aan.
    _no_csrf(app)
    app.dependency_overrides[require_auth] = lambda: speler
    app.dependency_overrides[get_current_user] = lambda: speler
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "partner_voornaam": "Piet", "partner_achternaam": "Pietersen",
    })
    assert response.status_code == 302
    assert "bevestigd=1" in response.headers["location"]

    regs = db_session.query(Registration).filter(Registration.person1_id == speler.id).all()
    assert len(regs) == 2  # de afgemelde rij blijft bewaard, plus de nieuwe aanmelding
    nieuwe = [r for r in regs if r.status == RegistrationStatus.aangemeld]
    assert len(nieuwe) == 1
    assert nieuwe[0].partner_naam == "Piet Pietersen"


async def test_onbekende_registratie_geeft_geen_fout(client, db_session):
    from app.main import app

    club, wl = _wl_met_club(db_session)
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id)

    _set_auth(app, wl)
    response = await client.post(f"/beheer/af-aanmeldingen/{ev.id}/reg/99999/verwijder")
    assert response.status_code == 302
    assert "paar_verwijderd" not in response.headers["location"]
