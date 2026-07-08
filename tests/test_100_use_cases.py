"""
100 gegenereerde use cases (UC101–UC200) — brede dekking van de hele app,
inclusief regressietests voor de gerepareerde bugs (club-scoping, rate
limiting, datumvalidatie, oneindige-lus-guard, GDPR-opruiming, enz.).
"""
import hashlib
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from tests.conftest import make_member, make_season

WACHTWOORD = "geheim123!"


# ── Gedeelde helpers ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_ratelimit():
    """Rate-limiter is module-globale staat; schoon vóór en na elke test."""
    from app import ratelimit
    ratelimit._failed.clear()
    yield
    ratelimit._failed.clear()


def _no_csrf(app):
    from app.csrf import require_csrf
    app.dependency_overrides[require_csrf] = lambda: None


def _set_auth(app, member=None, admin=None, wl=None):
    from app.auth import require_admin, require_auth, require_wedstrijdleider
    _no_csrf(app)
    if admin is not None:
        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[require_wedstrijdleider] = lambda: admin
        app.dependency_overrides[require_auth] = lambda: admin
    if wl is not None:
        app.dependency_overrides[require_wedstrijdleider] = lambda: wl
        app.dependency_overrides[require_auth] = lambda: wl
    if member is not None:
        app.dependency_overrides[require_auth] = lambda: member


def make_club(db_session, naam="BC Gen"):
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
                 datum=None, deelnemers_type="paren", inschrijftermijn_uren=None):
    from app.models import ClubEvening
    if datum is None:
        datum = date.today() + timedelta(days=7)
    ev = ClubEvening(datum=datum, type=ev_type, season_id=season_id,
                     club_id=club_id, deelnemers_type=deelnemers_type,
                     inschrijftermijn_uren=inschrijftermijn_uren)
    db_session.add(ev)
    db_session.commit()
    db_session.refresh(ev)
    return ev


def make_season_nu(db_session, club_id=None, actief=True):
    """Seizoen dat vandaag omvat (conftest-seizoen loopt tot medio 2026)."""
    from app.models import Season
    s = Season(naam="Seizoen-nu", start_datum=date.today() - timedelta(days=30),
               eind_datum=date.today() + timedelta(days=2500), actief=actief,
               club_id=club_id)
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def make_registration(db_session, member_id, evening_id, status="aangemeld", **kw):
    from app.models import Registration, RegistrationStatus, RegistrationType
    reg = Registration(evening_id=evening_id, person1_id=member_id,
                       type=RegistrationType.los,
                       status=getattr(RegistrationStatus, status), **kw)
    db_session.add(reg)
    db_session.commit()
    db_session.refresh(reg)
    return reg


def make_lid_entry(db_session, voornaam, achternaam, nbb_nummer=None, club_id=None):
    from app.models import Lid
    lid = Lid(voornaam=voornaam, achternaam=achternaam,
              nbb_nummer=nbb_nummer, club_id=club_id)
    db_session.add(lid)
    db_session.commit()
    return lid


def met_wachtwoord(db_session, member, wachtwoord=WACHTWOORD, email=None):
    from app.auth import hash_password
    member.wachtwoord_hash = hash_password(wachtwoord)
    if email:
        member.email = email
    db_session.commit()
    return member


# ══════════════════════════════════════════════════════════════════════════════
# A. AUTH & LOGIN (UC101–UC118)
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc101_login_pagina(client):
    response = await client.get("/login")
    assert response.status_code == 200


async def test_uc102_login_fout_wachtwoord(client, db_session):
    from app.main import app
    _no_csrf(app)
    lid = met_wachtwoord(db_session, make_member(db_session, lidnummer="UC102"))
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC102", "password": "verkeerd!",
    })
    assert response.status_code == 401


async def test_uc103_login_succes(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC103"))
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC103", "password": WACHTWOORD,
    })
    assert response.status_code == 302
    assert response.headers["location"] == "/"


async def test_uc104_login_volgt_next_parameter(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC104"))
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC104", "password": WACHTWOORD,
        "next": "/profiel",
    })
    assert response.status_code == 302
    assert response.headers["location"] == "/profiel"


async def test_uc105_login_next_absolute_url_geweigerd(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC105"))
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC105", "password": WACHTWOORD,
        "next": "https://evil.example.com/phish",
    })
    assert response.headers["location"] == "/"


async def test_uc106_login_next_dubbele_slash_geweigerd(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC106"))
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC106", "password": WACHTWOORD,
        "next": "//evil.example.com",
    })
    assert response.headers["location"] == "/"


async def test_uc107_login_met_naam(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(
        db_session, voornaam="Uniekjan", achternaam="Naamtest", lidnummer="UC107"))
    response = await client.post("/login", data={
        "login_method": "naam", "voornaam": "Uniekjan", "achternaam": "Naamtest",
        "password": WACHTWOORD,
    })
    assert response.status_code == 302


async def test_uc108_login_naam_wildcards_matchen_niet(client, db_session):
    """ILIKE-wildcards (%/_) in de naam-login worden ge-escaped."""
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(
        db_session, voornaam="Doelwit", achternaam="Speler", lidnummer="UC108"))
    response = await client.post("/login", data={
        "login_method": "naam", "voornaam": "%", "achternaam": "%",
        "password": WACHTWOORD,
    })
    assert response.status_code == 401


async def test_uc109_login_naam_meerdere_matches(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(
        db_session, voornaam="Jan", achternaam="Dubbel", lidnummer="UC109A"))
    met_wachtwoord(db_session, make_member(
        db_session, voornaam="Jan", achternaam="Dubbel", lidnummer="UC109B"))
    response = await client.post("/login", data={
        "login_method": "naam", "voornaam": "Jan", "achternaam": "Dubbel",
        "password": WACHTWOORD,
    })
    assert response.status_code == 401
    assert "Meerdere accounts" in response.text


async def test_uc110_login_verwijderd_lid(client, db_session):
    from datetime import datetime, timezone
    from app.main import app
    _no_csrf(app)
    lid = met_wachtwoord(db_session, make_member(db_session, lidnummer="UC110"))
    lid.verwijderd_op = datetime.now(timezone.utc)
    db_session.commit()
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC110", "password": WACHTWOORD,
    })
    assert response.status_code == 401


async def test_uc111_login_rate_limit_na_5_pogingen(client, db_session):
    from app.main import app
    _no_csrf(app)
    for _ in range(5):
        response = await client.post("/login", data={
            "login_method": "nbb", "nbb_nummer": "BESTAATNIET", "password": "x" * 8,
        })
        assert response.status_code == 401
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "BESTAATNIET", "password": "x" * 8,
    })
    assert response.status_code == 429


async def test_uc112_login_succes_reset_rate_limit(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC112"))
    for _ in range(4):
        await client.post("/login", data={
            "login_method": "nbb", "nbb_nummer": "UC112", "password": "verkeerd!",
        })
    ok = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC112", "password": WACHTWOORD,
    })
    assert ok.status_code == 302
    # Teller is gereset: een nieuwe foute poging geeft 401, geen 429
    fout = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC112", "password": "verkeerd!",
    })
    assert fout.status_code == 401


async def test_uc113_legacy_hash_wordt_geupgraded(client, db_session):
    """Oude 'salt$hash'-hashes worden bij succesvolle login vervangen."""
    from app.main import app
    _no_csrf(app)
    lid = make_member(db_session, lidnummer="UC113")
    salt = "ab" * 16
    dk = hashlib.pbkdf2_hmac("sha256", WACHTWOORD.encode(), salt.encode(), 260_000)
    lid.wachtwoord_hash = f"{salt}${dk.hex()}"
    db_session.commit()
    response = await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC113", "password": WACHTWOORD,
    })
    assert response.status_code == 302
    db_session.expire_all()
    assert lid.wachtwoord_hash.startswith("pbkdf2_sha256$")


async def test_uc114_login_pagina_redirect_indien_ingelogd(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC114"))
    await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC114", "password": WACHTWOORD,
    })
    response = await client.get("/login")
    assert response.status_code == 302
    assert response.headers["location"] == "/"


async def test_uc115_logout_wist_sessie(client, db_session):
    from app.main import app
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC115"))
    await client.post("/login", data={
        "login_method": "nbb", "nbb_nummer": "UC115", "password": WACHTWOORD,
    })
    assert (await client.get("/gdpr/download")).status_code == 200
    await client.get("/logout")
    response = await client.get("/gdpr/download")
    assert response.status_code == 302
    assert "/login" in response.headers["location"]


async def test_uc116_wachtwoord_vergeten_onbekend_adres_stil(client, db_session):
    """Onbekend e-mailadres → zelfde antwoord (geen accountenumeratie)."""
    from app.main import app
    from app.models import PasswordResetToken
    _no_csrf(app)
    response = await client.post("/wachtwoord-vergeten",
                                 data={"email": "bestaatniet@voorbeeld.nl"})
    assert response.status_code == 200
    assert db_session.query(PasswordResetToken).count() == 0


async def test_uc117_wachtwoord_vergeten_rate_limit(client, db_session):
    """Na 5 pogingen worden geen reset-tokens meer aangemaakt."""
    from app.main import app
    from app.models import PasswordResetToken
    _no_csrf(app)
    met_wachtwoord(db_session, make_member(db_session, lidnummer="UC117"),
                   email="uc117@voorbeeld.nl")
    for _ in range(5):
        await client.post("/wachtwoord-vergeten",
                          data={"email": "onbekend@voorbeeld.nl"})
    response = await client.post("/wachtwoord-vergeten",
                                 data={"email": "uc117@voorbeeld.nl"})
    assert response.status_code == 200
    assert db_session.query(PasswordResetToken).count() == 0


async def test_uc118_wachtwoord_reset_ongeldig_token(client):
    response = await client.get("/wachtwoord-reset/ongeldigtoken123")
    assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# B. REGISTRATIE & AANMELDEN (UC119–UC140)
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc119_registreren_pagina(client):
    response = await client.get("/registreren")
    assert response.status_code == 200


async def test_uc120_registreren_lege_velden(client, db_session):
    from app.main import app
    _no_csrf(app)
    response = await client.post("/registreren", data={})
    assert response.status_code == 422


async def test_uc121_registreren_kort_wachtwoord(client, db_session):
    from app.main import app
    _no_csrf(app)
    response = await client.post("/registreren", data={
        "voornaam": "A", "achternaam": "B", "email": "a@b.nl",
        "lidnummer": "1", "password": "kort", "password2": "kort",
        "toestemming": "on",
    })
    assert response.status_code == 422
    assert "minimaal 8 tekens" in response.text


async def test_uc122_registreren_zonder_toestemming(client, db_session):
    from app.main import app
    _no_csrf(app)
    response = await client.post("/registreren", data={
        "voornaam": "A", "achternaam": "B", "email": "a@b.nl",
        "lidnummer": "1", "password": WACHTWOORD, "password2": WACHTWOORD,
    })
    assert response.status_code == 422
    assert "privacybeleid" in response.text


async def test_uc123_registreren_lid_in_ledenlijst(client, db_session):
    from app.main import app
    from app.models import Member, MemberClub
    _no_csrf(app)
    club = make_club(db_session)
    make_lid_entry(db_session, "Nieuw", "Clublid", nbb_nummer="NB123",
                   club_id=club.id)
    response = await client.post("/registreren", data={
        "voornaam": "Nieuw", "achternaam": "Clublid", "email": "nieuw@voorbeeld.nl",
        "lidnummer": "NB123", "password": WACHTWOORD, "password2": WACHTWOORD,
        "toestemming": "on",
    })
    assert response.status_code == 302
    member = db_session.query(Member).filter(Member.lidnummer == "NB123").first()
    assert member is not None
    assert db_session.query(MemberClub).filter(
        MemberClub.member_id == member.id, MemberClub.club_id == club.id
    ).first() is not None


async def test_uc124_registreren_naam_mismatch_wordt_geweigerd(client, db_session):
    """Andermans NBB-nummer met een andere naam: account wordt niet aangemaakt."""
    from app.main import app
    from app.models import Member
    _no_csrf(app)
    club = make_club(db_session)
    make_lid_entry(db_session, "Echte", "Naam", nbb_nummer="NB124", club_id=club.id)
    response = await client.post("/registreren", data={
        "voornaam": "Valse", "achternaam": "Naam", "email": "vals@voorbeeld.nl",
        "lidnummer": "NB124", "password": WACHTWOORD, "password2": WACHTWOORD,
        "toestemming": "on",
    })
    assert response.status_code == 422
    assert db_session.query(Member).filter(Member.lidnummer == "NB124").count() == 0


async def test_uc125_registreren_onbekend_clubloos_account(client, db_session):
    """Niet in een ledenlijst: account wordt aangemaakt zonder clubkoppeling."""
    from app.main import app
    from app.models import Member, MemberClub
    _no_csrf(app)
    response = await client.post("/registreren", data={
        "voornaam": "On", "achternaam": "Bekend", "email": "onbekend125@voorbeeld.nl",
        "lidnummer": "NB125", "password": WACHTWOORD, "password2": WACHTWOORD,
        "toestemming": "on",
    })
    assert response.status_code == 302
    member = db_session.query(Member).filter(Member.lidnummer == "NB125").first()
    assert member is not None
    assert member.toestemming_op is not None
    assert db_session.query(MemberClub).filter(
        MemberClub.member_id == member.id).count() == 0


async def test_uc126_registreren_zelfde_email_geweigerd(client, db_session):
    """Tweede registratie met hetzelfde e-mailadres wordt geweigerd."""
    from app.main import app
    from app.models import Member
    _no_csrf(app)
    data = {
        "voornaam": "Dub", "achternaam": "Bel", "email": "dubbel@voorbeeld.nl",
        "lidnummer": "NB126", "password": WACHTWOORD, "password2": WACHTWOORD,
        "toestemming": "on",
    }
    assert (await client.post("/registreren", data=data)).status_code == 302
    data["lidnummer"] = "NB126B"
    response = await client.post("/registreren", data=data)
    assert response.status_code == 422
    assert db_session.query(Member).filter(
        Member.email == "dubbel@voorbeeld.nl").count() == 1


async def test_uc127_registreren_bestaand_account(client, db_session):
    from app.main import app
    _no_csrf(app)
    lid = make_member(db_session, lidnummer="NB127")
    lid.email = "bestaand@voorbeeld.nl"
    db_session.commit()
    response = await client.post("/registreren", data={
        "voornaam": "X", "achternaam": "Y", "email": "bestaand@voorbeeld.nl",
        "lidnummer": "ANDERS", "password": WACHTWOORD, "password2": WACHTWOORD,
        "toestemming": "on",
    })
    assert response.status_code == 422


async def test_uc128_aanmelden_met_partner_uit_ledenlijst(client, db_session):
    from app.main import app
    from app.models import Registration, RegistrationStatus
    lid = make_member(db_session, lidnummer="UC128")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    make_lid_entry(db_session, "Piet", "Klaassen")
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}", data={
        "partner_voornaam": "Piet", "partner_achternaam": "Klaassen",
    })
    assert response.status_code == 302
    assert "bevestigd=1" in response.headers["location"]
    reg = db_session.query(Registration).filter(
        Registration.person1_id == lid.id).first()
    assert reg.status == RegistrationStatus.aangemeld
    assert reg.partner_naam == "Piet Klaassen"


async def test_uc129_aanmelden_onbekende_partner_wordt_verzoek(client, db_session):
    from app.main import app
    from app.models import PartnerRequest
    lid = make_member(db_session, lidnummer="UC129")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}", data={
        "partner_voornaam": "Gast", "partner_achternaam": "Speler",
    })
    assert response.status_code == 302
    assert db_session.query(PartnerRequest).filter(
        PartnerRequest.requester_id == lid.id,
        PartnerRequest.status == "wachtend",
    ).count() == 1


async def test_uc130_aanmelden_zonder_partner_solo(client, db_session):
    from app.main import app
    from app.models import Registration, RegistrationStatus
    lid = make_member(db_session, lidnummer="UC130")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    _set_auth(app, member=lid)
    await client.post(f"/aanmelden/{evening.id}",
                      data={"partner_voornaam": "", "partner_achternaam": ""})
    reg = db_session.query(Registration).filter(
        Registration.person1_id == lid.id).first()
    assert reg.status == RegistrationStatus.beschikbaar_solo


async def test_uc131_afmelden(client, db_session):
    from app.main import app
    from app.models import Registration, RegistrationStatus
    lid = make_member(db_session, lidnummer="UC131")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    make_registration(db_session, lid.id, evening.id)
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}",
                                 data={"action": "afmelden"})
    assert "afgemeld=1" in response.headers["location"]
    db_session.expire_all()
    reg = db_session.query(Registration).filter(
        Registration.person1_id == lid.id).first()
    assert reg.status == RegistrationStatus.afgemeld


async def test_uc132_afmelden_zonder_aanmelding_geen_crash(client, db_session):
    from app.main import app
    from app.models import Registration
    lid = make_member(db_session, lidnummer="UC132")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}",
                                 data={"action": "afmelden"})
    assert response.status_code == 302
    assert db_session.query(Registration).count() == 0


async def test_uc133_individueel_aanmelden(client, db_session):
    from app.main import app
    from app.models import Registration, RegistrationStatus
    lid = make_member(db_session, lidnummer="UC133")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="individueel")
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}", data={})
    assert "bevestigd=1" in response.headers["location"]
    reg = db_session.query(Registration).first()
    assert reg.status == RegistrationStatus.aangemeld
    assert reg.partner_naam is None


async def test_uc134_viertallen_volledig_team(client, db_session):
    from app.main import app
    from app.models import Registration
    lid = make_member(db_session, lidnummer="UC134")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="viertallen")
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}", data={
        "team_naam": "De Azen",
        "partner_voornaam": "B", "partner_achternaam": "Bee",
        "partner2_voornaam": "C", "partner2_achternaam": "Cee",
        "partner3_voornaam": "D", "partner3_achternaam": "Dee",
    })
    assert "bevestigd=1" in response.headers["location"]
    reg = db_session.query(Registration).first()
    assert reg.team_naam == "De Azen"
    assert reg.partner3_naam == "D Dee"


async def test_uc135_viertallen_onvolledig_team(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC135")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="viertallen")
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}", data={
        "partner_voornaam": "B", "partner_achternaam": "Bee",
    })
    assert "aangemeld_onvolledig_team=1" in response.headers["location"]


async def test_uc136_te_laat_vlag_na_inschrijftermijn(client, db_session):
    from app.main import app
    from app.models import Registration
    lid = make_member(db_session, lidnummer="UC136")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id,
                           datum=date.today() + timedelta(days=1),
                           inschrijftermijn_uren=100)
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}",
                                 data={"partner_voornaam": "", "partner_achternaam": ""})
    assert "te_laat=1" in response.headers["location"]
    reg = db_session.query(Registration).first()
    assert reg.te_laat is True


async def test_uc137_te_laat_goedkeuring_vervalt_bij_wijziging(client, db_session):
    """Regressie: nieuwe te-late wijziging reset een eerdere goedkeuring."""
    from app.main import app
    from app.models import Registration
    lid = make_member(db_session, lidnummer="UC137")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id,
                           datum=date.today() + timedelta(days=1),
                           inschrijftermijn_uren=100)
    reg = make_registration(db_session, lid.id, evening.id,
                            status="beschikbaar_solo", te_laat=True,
                            te_laat_goedgekeurd=True)
    make_lid_entry(db_session, "Piet", "Klaassen")
    _set_auth(app, member=lid)
    await client.post(f"/aanmelden/{evening.id}", data={
        "partner_voornaam": "Piet", "partner_achternaam": "Klaassen",
    })
    db_session.expire_all()
    assert reg.te_laat is True
    assert reg.te_laat_goedgekeurd is None


async def test_uc138_verleden_avond_aanmelden_geweigerd(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC138")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id,
                           datum=date.today() - timedelta(days=1))
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}", data={})
    assert response.status_code == 302
    assert response.headers["location"] == "/"


async def test_uc139_training_niet_toegestaan(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC139", training_eligible=False)
    season = make_season(db_session)
    evening = make_evening(db_session, season.id, ev_type="jeugdtraining")
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{evening.id}", data={})
    assert "training_niet_toegestaan=1" in response.headers["location"]


async def test_uc140_aanmelden_wijzigen_route_bereikbaar(client, db_session):
    """Regressie: /aanmelden/wijzigen matchte eerst /aanmelden/{event_id} (422)."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC140")
    _set_auth(app, member=lid)
    response = await client.get("/aanmelden/wijzigen")
    assert response.status_code == 302
    assert response.headers["location"] == "/"


# ══════════════════════════════════════════════════════════════════════════════
# C. BULK & HERHAAL (UC141–UC150)
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc141_instellingen_pagina(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC141")
    _set_auth(app, member=lid)
    response = await client.get("/instellingen")
    assert response.status_code == 200


async def test_uc142_bulk_aanmelden_alle_clubavonden(client, db_session):
    from app.main import app
    from app.models import Registration
    lid = make_member(db_session, lidnummer="UC142")
    season = make_season(db_session)
    for d in (7, 14, 21):
        make_evening(db_session, season.id, datum=date.today() + timedelta(days=d))
    make_evening(db_session, season.id, ev_type="speciaal")
    _set_auth(app, member=lid)
    response = await client.post("/instellingen", data={})
    assert "bulk_ok=3" in response.headers["location"]
    assert db_session.query(Registration).count() == 3


async def test_uc143_bulk_aanmelden_andere_club_geweigerd(client, db_session):
    """Regressie: club_id uit het formulier wordt tegen lidmaatschap gevalideerd."""
    from app.main import app
    club_a = make_club(db_session, "Club A")
    club_b = make_club(db_session, "Club B")
    lid = make_member(db_session, lidnummer="UC143")
    make_member_club(db_session, lid.id, club_a.id)
    _set_auth(app, member=lid)
    response = await client.post("/instellingen", data={"club_id": str(club_b.id)})
    assert response.status_code == 403


async def test_uc144_herhaal_alles_plus_recurring(client, db_session):
    from app.main import app
    from app.models import RecurringRegistration, Registration
    lid = make_member(db_session, lidnummer="UC144")
    season = make_season(db_session)
    bron = make_evening(db_session, season.id, datum=date.today() + timedelta(days=7))
    make_evening(db_session, season.id, datum=date.today() + timedelta(days=14))
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{bron.id}/herhaal", data={"alles": "on"})
    assert "bulk_ok=2" in response.headers["location"]
    assert db_session.query(Registration).count() == 2
    assert db_session.query(RecurringRegistration).filter(
        RecurringRegistration.actief == True  # noqa: E712
    ).count() == 1


async def test_uc145_herhaal_neemt_legacy_synoniem_mee(client, db_session):
    """Regressie: 'regulier' en 'clubavond' zijn hetzelfde type."""
    from app.main import app
    from app.models import Registration
    lid = make_member(db_session, lidnummer="UC145")
    season = make_season(db_session)
    bron = make_evening(db_session, season.id, ev_type="regulier",
                        datum=date.today() + timedelta(days=7))
    make_evening(db_session, season.id, ev_type="clubavond",
                 datum=date.today() + timedelta(days=14))
    _set_auth(app, member=lid)
    await client.post(f"/aanmelden/{bron.id}/herhaal", data={"alles": "on"})
    assert db_session.query(Registration).count() == 2


async def test_uc146_herhaal_foute_datum_geen_500(client, db_session):
    """Regressie: ongeldige datum gaf een 500."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC146")
    season = make_season(db_session)
    bron = make_evening(db_session, season.id)
    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{bron.id}/herhaal", data={
        "alles": "on", "alles_tot": "geen-geldige-datum",
    })
    assert response.status_code == 302
    assert "fout=datum" in response.headers["location"]


async def test_uc147_herhaal_om_de_week(client, db_session):
    from app.main import app
    from app.models import Registration
    lid = make_member(db_session, lidnummer="UC147")
    season = make_season(db_session)
    avonden = [make_evening(db_session, season.id,
                            datum=date.today() + timedelta(days=d))
               for d in (7, 14, 21, 28)]
    _set_auth(app, member=lid)
    await client.post(f"/aanmelden/{avonden[0].id}/herhaal", data={"elke": "2"})
    assert db_session.query(Registration).count() == 2


async def test_uc148_definitief_aanmelden_onbekend_type(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC148")
    _set_auth(app, member=lid)
    response = await client.post("/definitief-aanmelden/onzin", data={})
    assert response.status_code == 400


async def test_uc149_voor_alles_aanmelden_respecteert_training(client, db_session):
    from app.main import app
    from app.models import Bericht, Registration
    lid = make_member(db_session, lidnummer="UC149", training_eligible=False)
    season = make_season(db_session)
    make_evening(db_session, season.id)
    make_evening(db_session, season.id, ev_type="jeugdtraining",
                 datum=date.today() + timedelta(days=8))
    _set_auth(app, member=lid)
    response = await client.post("/voor-alles-aanmelden", data={})
    assert "bulk_ok=1" in response.headers["location"]
    assert db_session.query(Registration).count() == 1
    assert db_session.query(Bericht).filter(
        Bericht.is_systeem == True  # noqa: E712
    ).count() == 1


async def test_uc150_voor_alles_afmelden_annuleert_verzoeken(client, db_session):
    """Regressie: bulk afmelden liet openstaande partnerverzoeken staan."""
    from app.main import app
    from app.models import PartnerRequest, Registration, RegistrationStatus
    lid = make_member(db_session, lidnummer="UC150")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    make_registration(db_session, lid.id, evening.id)
    db_session.add(PartnerRequest(evening_id=evening.id, requester_id=lid.id,
                                  partner_voornaam="Gast", partner_achternaam="X"))
    db_session.commit()
    _set_auth(app, member=lid)
    response = await client.post("/voor-alles-afmelden", data={})
    assert "afgemeld_alles=1" in response.headers["location"]
    db_session.expire_all()
    assert db_session.query(Registration).first().status == RegistrationStatus.afgemeld
    assert db_session.query(PartnerRequest).count() == 0


# ══════════════════════════════════════════════════════════════════════════════
# D. AUTORISATIE & CLUB-SCOPING (UC151–UC162)
# ══════════════════════════════════════════════════════════════════════════════

def _twee_clubs_setup(db_session):
    """Club A met avond, plus een lid en een WL die alleen bij club B horen."""
    club_a = make_club(db_session, "Club A")
    club_b = make_club(db_session, "Club B")
    season_a = make_season_nu(db_session, club_id=club_a.id)
    avond_a = make_evening(db_session, season_a.id, club_id=club_a.id)
    lid_b = make_member(db_session, lidnummer="LID-B")
    make_member_club(db_session, lid_b.id, club_b.id, role="lid")
    wl_b = make_member(db_session, voornaam="Wil", lidnummer="WL-B")
    make_member_club(db_session, wl_b.id, club_b.id, role="wedstrijdleider")
    return club_a, club_b, avond_a, lid_b, wl_b


async def test_uc151_aanmelden_andere_club_403(client, db_session):
    from app.main import app
    _, _, avond_a, lid_b, _ = _twee_clubs_setup(db_session)
    _set_auth(app, member=lid_b)
    response = await client.post(f"/aanmelden/{avond_a.id}", data={})
    assert response.status_code == 403


async def test_uc152_deelnemers_andere_club_403(client, db_session):
    from app.main import app
    _, _, avond_a, lid_b, _ = _twee_clubs_setup(db_session)
    _set_auth(app, member=lid_b)
    response = await client.get(f"/deelnemers/{avond_a.id}")
    assert response.status_code == 403


async def test_uc153_aanmeldingen_detail_andere_club_403(client, db_session):
    from app.main import app
    _, club_b, avond_a, lid_b, _ = _twee_clubs_setup(db_session)
    _set_auth(app, member=lid_b)
    assert (await client.get(f"/beheer/aanmeldingen/{avond_a.id}")).status_code == 403
    season_b = make_season_nu(db_session, club_id=club_b.id)
    avond_b = make_evening(db_session, season_b.id, club_id=club_b.id)
    assert (await client.get(f"/beheer/aanmeldingen/{avond_b.id}")).status_code == 200


async def test_uc154_wl_af_aanmeldingen_andere_club_403(client, db_session):
    from app.main import app
    _, _, avond_a, _, wl_b = _twee_clubs_setup(db_session)
    _set_auth(app, wl=wl_b)
    response = await client.get(f"/beheer/af-aanmeldingen/{avond_a.id}")
    assert response.status_code == 403


async def test_uc155_wl_af_aanmeldingen_eigen_club_200(client, db_session):
    from app.main import app
    _, club_b, _, _, wl_b = _twee_clubs_setup(db_session)
    season_b = make_season_nu(db_session, club_id=club_b.id)
    avond_b = make_evening(db_session, season_b.id, club_id=club_b.id)
    _set_auth(app, wl=wl_b)
    response = await client.get(f"/beheer/af-aanmeldingen/{avond_b.id}")
    assert response.status_code == 200


async def test_uc156_uitslag_upload_andere_club_403(client, db_session):
    from app.main import app
    _, _, avond_a, _, wl_b = _twee_clubs_setup(db_session)
    _set_auth(app, wl=wl_b)
    response = await client.post(
        f"/uitslagen/{avond_a.id}/uploaden",
        files={"bestand": ("u.xml", b"<x/>", "text/xml")},
    )
    assert response.status_code == 403


async def test_uc157_uitslag_verwijderen_andere_club_403(client, db_session):
    from app.main import app
    from app.models import Uitslag
    _, _, avond_a, _, wl_b = _twee_clubs_setup(db_session)
    db_session.add(Uitslag(evening_id=avond_a.id, inhoud=b"<x/>"))
    db_session.commit()
    _set_auth(app, wl=wl_b)
    response = await client.post(f"/uitslagen/{avond_a.id}/verwijderen", data={})
    assert response.status_code == 403
    assert db_session.query(Uitslag).count() == 1


async def test_uc158_lid_detail_andere_club_403(client, db_session):
    from app.main import app
    club_a, _, _, _, wl_b = _twee_clubs_setup(db_session)
    lid_a = make_member(db_session, lidnummer="UC158A")
    make_member_club(db_session, lid_a.id, club_a.id)
    _set_auth(app, wl=wl_b)
    response = await client.get(f"/leden/{lid_a.id}")
    assert response.status_code == 403


async def test_uc159_training_toggle_andere_club_403(client, db_session):
    from app.main import app
    club_a, _, _, _, wl_b = _twee_clubs_setup(db_session)
    lid_a = make_member(db_session, lidnummer="UC159A")
    make_member_club(db_session, lid_a.id, club_a.id)
    _set_auth(app, wl=wl_b)
    response = await client.post(f"/leden/{lid_a.id}/training-toggle", data={})
    assert response.status_code == 403
    db_session.expire_all()
    assert lid_a.training_eligible is False  # onveranderd


async def test_uc160_actieve_club_zonder_rol_403(client, db_session):
    from app.main import app
    club = make_club(db_session)
    lid = make_member(db_session, lidnummer="UC160", role="lid")
    _set_auth(app, wl=lid)  # dependency-override; de route checkt zelf de clubrol
    response = await client.get(f"/beheer/actieve-club/{club.id}")
    assert response.status_code == 403


async def test_uc161_beheer_avonden_als_lid_403(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC161", role="lid")
    _set_auth(app, member=lid)
    response = await client.get("/beheer/avonden")
    assert response.status_code == 403


async def test_uc162_weergave_wissel_admin(client, db_session):
    from app.main import app
    admin = make_member(db_session, lidnummer="UC162", role="admin")
    _set_auth(app, admin=admin)
    assert (await client.get("/beheer/weergave/lid")).status_code == 302
    assert (await client.get("/beheer/weergave/reset")).status_code == 302
    assert (await client.get("/beheer/weergave/onzin")).status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# E. ADMIN: AVONDEN, SEIZOENEN, LEDEN, AANVRAGEN, ROLLEN (UC163–UC180)
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc163_avonden_lijst(client, db_session):
    from app.main import app
    wl = make_member(db_session, lidnummer="UC163", role="wedstrijdleider")
    _set_auth(app, wl=wl)
    response = await client.get("/beheer/avonden")
    assert response.status_code == 200


async def test_uc164_avond_aanmaken(client, db_session):
    from app.main import app
    from app.models import ClubEvening
    wl = make_member(db_session, lidnummer="UC164", role="wedstrijdleider")
    make_season_nu(db_session)
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/avonden", data={
        "naam": "Zomeravond", "datum": (date.today() + timedelta(days=7)).isoformat(),
        "type": "clubavond",
    })
    assert response.status_code == 302
    assert "aangemaakt=1" in response.headers["location"]
    assert db_session.query(ClubEvening).filter(
        ClubEvening.naam == "Zomeravond").count() == 1


async def test_uc165_avond_aanmaken_foute_datum(client, db_session):
    from app.main import app
    wl = make_member(db_session, lidnummer="UC165", role="wedstrijdleider")
    make_season_nu(db_session)
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/avonden", data={
        "naam": "X", "datum": "31-12-2026", "type": "clubavond",
    })
    assert response.status_code == 422


async def test_uc166_avond_aanmaken_zonder_seizoen(client, db_session):
    from app.main import app
    wl = make_member(db_session, lidnummer="UC166", role="wedstrijdleider")
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/avonden", data={
        "naam": "X", "datum": (date.today() + timedelta(days=7)).isoformat(),
        "type": "clubavond",
    })
    assert response.status_code == 422
    assert "Geen seizoen" in response.text


async def test_uc167_herhaal_avonden_wekelijks(client, db_session):
    from app.main import app
    from app.models import ClubEvening
    wl = make_member(db_session, lidnummer="UC167", role="wedstrijdleider")
    make_season_nu(db_session)
    _set_auth(app, wl=wl)
    start = date.today() + timedelta(days=7)
    response = await client.post("/beheer/avonden", data={
        "naam": "Reeks", "datum": start.isoformat(), "type": "clubavond",
        "herhaal_elke": "1", "herhaal_eenheid": "weken",
        "herhaal_tot": (start + timedelta(days=21)).isoformat(),
    })
    assert "aangemaakt=4" in response.headers["location"]
    assert db_session.query(ClubEvening).count() == 4


async def test_uc168_herhaal_avonden_interval_nul_geen_hang(client, db_session):
    """Regressie: herhaal_elke=0 veroorzaakte een oneindige lus."""
    from app.main import app
    from app.models import ClubEvening
    wl = make_member(db_session, lidnummer="UC168", role="wedstrijdleider")
    make_season_nu(db_session)
    _set_auth(app, wl=wl)
    start = date.today() + timedelta(days=7)
    response = await client.post("/beheer/avonden", data={
        "naam": "Nulreeks", "datum": start.isoformat(), "type": "clubavond",
        "herhaal_elke": "0", "herhaal_eenheid": "weken",
        "herhaal_tot": (start + timedelta(days=21)).isoformat(),
    })
    assert response.status_code == 302
    # 0 wordt geklemd naar 1 → wekelijks, dus 4 avonden
    assert db_session.query(ClubEvening).count() == 4


async def test_uc169_herhaal_avonden_maximaal_200(client, db_session):
    from app.main import app
    from app.models import ClubEvening
    wl = make_member(db_session, lidnummer="UC169", role="wedstrijdleider")
    make_season_nu(db_session)
    _set_auth(app, wl=wl)
    start = date.today() + timedelta(days=7)
    await client.post("/beheer/avonden", data={
        "naam": "Lange reeks", "datum": start.isoformat(), "type": "clubavond",
        "herhaal_elke": "1", "herhaal_eenheid": "weken",
        "herhaal_tot": (start + timedelta(weeks=250)).isoformat(),
    })
    assert db_session.query(ClubEvening).count() == 200


async def test_uc170_avond_verwijderen_inclusief_aanmeldingen(client, db_session):
    from app.main import app
    from app.models import ClubEvening, Registration
    admin = make_member(db_session, lidnummer="UC170", role="admin")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    make_registration(db_session, admin.id, evening.id)
    _set_auth(app, admin=admin)
    response = await client.post(f"/beheer/avonden/{evening.id}/verwijder", data={})
    assert response.status_code == 302
    assert db_session.query(ClubEvening).count() == 0
    assert db_session.query(Registration).count() == 0


async def test_uc171_seizoen_aanmaken(client, db_session):
    from app.main import app
    from app.models import Season
    admin = make_member(db_session, lidnummer="UC171", role="admin")
    _set_auth(app, admin=admin)
    response = await client.post("/beheer/seizoenen", data={
        "naam": "2026-2027", "start_datum": "2026-09-01", "eind_datum": "2027-06-30",
    })
    assert response.status_code == 302
    assert db_session.query(Season).filter(Season.naam == "2026-2027").count() == 1


async def test_uc172_seizoen_foute_datum_geen_500(client, db_session):
    """Regressie: ongeldige datum bij seizoen aanmaken gaf een 500."""
    from app.main import app
    from app.models import Season
    admin = make_member(db_session, lidnummer="UC172", role="admin")
    _set_auth(app, admin=admin)
    response = await client.post("/beheer/seizoenen", data={
        "naam": "Kapot", "start_datum": "niet-een-datum", "eind_datum": "2027-06-30",
    })
    assert response.status_code == 302
    assert "fout=datum" in response.headers["location"]
    assert db_session.query(Season).filter(Season.naam == "Kapot").count() == 0


async def test_uc173_seizoen_start_na_eind_geweigerd(client, db_session):
    from app.main import app
    from app.models import Season
    admin = make_member(db_session, lidnummer="UC173", role="admin")
    _set_auth(app, admin=admin)
    response = await client.post("/beheer/seizoenen", data={
        "naam": "Omgekeerd", "start_datum": "2027-06-30", "eind_datum": "2026-09-01",
    })
    assert "fout=datum" in response.headers["location"]
    assert db_session.query(Season).filter(Season.naam == "Omgekeerd").count() == 0


async def test_uc174_seizoen_activeren_deactiveert_andere(client, db_session):
    from app.main import app
    from app.models import Season
    club = make_club(db_session)
    admin = make_member(db_session, lidnummer="UC174", role="admin")
    s1 = make_season_nu(db_session, club_id=club.id, actief=True)
    s2 = make_season_nu(db_session, club_id=club.id, actief=False)
    _set_auth(app, admin=admin)
    response = await client.post(f"/beheer/seizoenen/{s2.id}/activeer", data={})
    assert response.status_code == 302
    db_session.expire_all()
    assert s2.actief is True
    assert s1.actief is False


async def test_uc175_leden_csv_import(client, db_session):
    from app.main import app
    from app.models import Lid
    admin = make_member(db_session, lidnummer="UC175", role="admin")
    _set_auth(app, admin=admin)
    csv_data = b"voornaam,achternaam,nbb_nummer\nJan,Import,111\nPiet,Import,222\n"
    response = await client.post(
        "/beheer/leden/importeer",
        files={"bestand": ("leden.csv", csv_data, "text/csv")},
    )
    assert "import_ok=2" in response.headers["location"]
    assert db_session.query(Lid).count() == 2


async def test_uc176_leden_csv_import_dubbelen_overgeslagen(client, db_session):
    from app.main import app
    from app.models import Lid
    admin = make_member(db_session, lidnummer="UC176", role="admin")
    make_lid_entry(db_session, "Jan", "Bestaand")
    _set_auth(app, admin=admin)
    csv_data = b"voornaam,achternaam\nJan,Bestaand\nNieuw,Persoon\n"
    response = await client.post(
        "/beheer/leden/importeer",
        files={"bestand": ("leden.csv", csv_data, "text/csv")},
    )
    assert "import_ok=1" in response.headers["location"]
    assert "overgeslagen=1" in response.headers["location"]
    assert db_session.query(Lid).count() == 2


async def test_uc177_lid_toevoegen_en_verwijderen(client, db_session):
    from app.main import app
    from app.models import Lid
    admin = make_member(db_session, lidnummer="UC177", role="admin")
    _set_auth(app, admin=admin)
    await client.post("/beheer/leden", data={
        "voornaam": "Hand", "achternaam": "Matig", "nbb_nummer": "999",
    })
    lid = db_session.query(Lid).filter(Lid.achternaam == "Matig").first()
    assert lid is not None
    await client.post(f"/beheer/leden/{lid.id}/verwijder", data={})
    assert db_session.query(Lid).count() == 0


async def test_uc178_aanvraag_goedkeuren_maakt_account(client, db_session):
    from datetime import datetime, timezone
    from app.auth import hash_password
    from app.main import app
    from app.models import AccountRequest, Member
    admin = make_member(db_session, lidnummer="UC178", role="admin")
    toestemming = datetime.now(timezone.utc)
    aanvraag = AccountRequest(
        voornaam="Aan", achternaam="Vraag", email="aanvraag@voorbeeld.nl",
        lidnummer="AV178", wachtwoord_hash=hash_password(WACHTWOORD),
        toestemming_op=toestemming,
    )
    db_session.add(aanvraag)
    db_session.commit()
    _set_auth(app, admin=admin)
    # SMTP kan lokaal geconfigureerd zijn (.env) — geen echte mail sturen
    with patch("app.email.send_approval_email"):
        response = await client.post(f"/beheer/aanvragen/{aanvraag.id}/goedkeuren",
                                     data={"role": "lid"})
    assert response.status_code == 302
    member = db_session.query(Member).filter(Member.lidnummer == "AV178").first()
    assert member is not None
    assert member.toestemming_op is not None  # overgenomen van de aanvraag


async def test_uc179_aanvraag_afwijzen(client, db_session):
    from app.main import app
    from app.models import AccountRequest, AccountRequestStatus
    admin = make_member(db_session, lidnummer="UC179", role="admin")
    aanvraag = AccountRequest(voornaam="Af", achternaam="Gewezen",
                              email="af@voorbeeld.nl", lidnummer="AF179")
    db_session.add(aanvraag)
    db_session.commit()
    _set_auth(app, admin=admin)
    response = await client.post(f"/beheer/aanvragen/{aanvraag.id}/afwijzen", data={})
    assert response.status_code == 302
    db_session.expire_all()
    assert aanvraag.status == AccountRequestStatus.afgewezen


async def test_uc180_rol_toewijzen_en_valideren(client, db_session):
    from app.main import app
    from app.models import EmailRoleAssignment
    admin = make_member(db_session, lidnummer="UC180", role="admin")
    lid = make_member(db_session, lidnummer="UC180L")
    lid.email = "rol@voorbeeld.nl"
    db_session.commit()
    _set_auth(app, admin=admin)
    fout = await client.post("/beheer/rollen", data={
        "email": "rol@voorbeeld.nl", "role": "superuser",
    })
    assert "error=1" in fout.headers["location"]
    ok = await client.post("/beheer/rollen", data={
        "email": "rol@voorbeeld.nl", "role": "wedstrijdleider",
    })
    assert "opgeslagen=1" in ok.headers["location"]
    db_session.expire_all()
    assert lid.role == "wedstrijdleider"
    assert db_session.query(EmailRoleAssignment).count() == 1


# ══════════════════════════════════════════════════════════════════════════════
# F. CLUBS & ROLLEN (UC181–UC186)
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc181_clubs_lijst(client, db_session):
    from app.main import app
    admin = make_member(db_session, lidnummer="UC181", role="admin")
    make_club(db_session)
    _set_auth(app, admin=admin)
    response = await client.get("/beheer/clubs")
    assert response.status_code == 200


async def test_uc182_club_aanmaken_en_bijwerken(client, db_session):
    from app.main import app
    from app.models import Club
    admin = make_member(db_session, lidnummer="UC182", role="admin")
    _set_auth(app, admin=admin)
    await client.post("/beheer/clubs", data={"naam": "BC Nieuw", "stad": "Utrecht"})
    club = db_session.query(Club).filter(Club.naam == "BC Nieuw").first()
    assert club is not None
    await client.post(f"/beheer/clubs/{club.id}/update",
                      data={"naam": "BC Hernoemd", "kleur": "#ff0000"})
    db_session.expire_all()
    assert club.naam == "BC Hernoemd"
    assert club.kleur == "#ff0000"


async def test_uc183_club_lid_toevoegen_synct_globale_rol(client, db_session):
    """Regressie: door autoflush=False werd de globale rol niet bijgewerkt."""
    from app.main import app
    from app.models import MemberClub
    admin = make_member(db_session, lidnummer="UC183", role="admin")
    club = make_club(db_session)
    lid = make_member(db_session, lidnummer="UC183L", role="lid")
    _set_auth(app, admin=admin)
    response = await client.post(f"/beheer/clubs/{club.id}/leden/toevoegen", data={
        "member_id": str(lid.id), "role": "wedstrijdleider",
    })
    assert response.status_code == 302
    db_session.expire_all()
    assert db_session.query(MemberClub).filter(
        MemberClub.member_id == lid.id).count() == 1
    assert lid.role == "wedstrijdleider"


async def test_uc184_club_lid_rol_wijzigen(client, db_session):
    from app.main import app
    admin = make_member(db_session, lidnummer="UC184", role="admin")
    club = make_club(db_session)
    lid = make_member(db_session, lidnummer="UC184L", role="lid")
    make_member_club(db_session, lid.id, club.id, role="lid")
    _set_auth(app, admin=admin)
    response = await client.post(
        f"/beheer/clubs/{club.id}/leden/{lid.id}/rol", data={"role": "admin"})
    assert response.status_code == 302
    db_session.expire_all()
    assert lid.role == "admin"


async def test_uc185_club_lid_verwijderen_rol_valt_terug(client, db_session):
    from app.main import app
    from app.models import MemberClub
    admin = make_member(db_session, lidnummer="UC185", role="admin")
    club_a = make_club(db_session, "Club A")
    club_b = make_club(db_session, "Club B")
    lid = make_member(db_session, lidnummer="UC185L", role="wedstrijdleider")
    make_member_club(db_session, lid.id, club_a.id, role="wedstrijdleider")
    make_member_club(db_session, lid.id, club_b.id, role="lid")
    _set_auth(app, admin=admin)
    response = await client.post(
        f"/beheer/clubs/{club_a.id}/leden/{lid.id}/verwijder", data={})
    assert response.status_code == 302
    db_session.expire_all()
    assert db_session.query(MemberClub).filter(
        MemberClub.member_id == lid.id).count() == 1
    assert lid.role == "lid"


async def test_uc186_clubinstellingen_opslaan(client, db_session):
    from app.main import app
    from app.models import Club
    admin = make_member(db_session, lidnummer="UC186", role="admin")
    club = make_club(db_session)
    _set_auth(app, admin=admin)
    response = await client.post("/beheer/instellingen", data={
        "type_clubavond": "on", "type_speciaal": "on",
        "ranking_spanning": "on", "label_paren": "on",
    })
    assert "opgeslagen=1" in response.headers["location"]
    db_session.expire_all()
    club = db_session.query(Club).first()
    assert club.evenement_types == "clubavond,speciaal"
    assert club.ranking_weergaves == "spanning"
    assert club.labels == "paren"


# ══════════════════════════════════════════════════════════════════════════════
# G. BERICHTEN (UC187–UC193)
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc187_inbox(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC187")
    _no_csrf(app)
    with patch("app.routes.berichten.get_current_user", return_value=lid):
        response = await client.get("/berichten")
    assert response.status_code == 200


async def test_uc188_bericht_sturen(client, db_session):
    from app.main import app
    from app.models import Bericht
    afzender = make_member(db_session, lidnummer="UC188A")
    ontvanger = make_member(db_session, voornaam="Ont", achternaam="Vanger",
                            lidnummer="UC188B")
    _no_csrf(app)
    with patch("app.routes.berichten.get_current_user", return_value=afzender):
        response = await client.post("/berichten/verstuur", data={
            "ontvanger_id": str(ontvanger.id), "onderwerp": "Hoi", "tekst": "Test",
        })
    assert response.status_code == 302
    assert db_session.query(Bericht).count() == 1


async def test_uc189_bericht_aan_zichzelf_geweigerd(client, db_session):
    from app.main import app
    from app.models import Bericht
    lid = make_member(db_session, lidnummer="UC189")
    _no_csrf(app)
    with patch("app.routes.berichten.get_current_user", return_value=lid):
        response = await client.post("/berichten/verstuur", data={
            "ontvanger_id": str(lid.id), "tekst": "Zelf",
        })
    assert "fout=ontvanger" in response.headers["location"]
    assert db_session.query(Bericht).count() == 0


async def test_uc190_nieuws_door_lid_403(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC190", role="lid")
    _no_csrf(app)
    with patch("app.routes.berichten.get_current_user", return_value=lid):
        response = await client.post("/berichten/verstuur", data={
            "is_nieuws": "1", "onderwerp": "Nieuws", "tekst": "X",
        })
    assert response.status_code == 403


async def test_uc191_nieuws_door_per_club_wl(client, db_session):
    """Regressie: per-club WL-rol mocht geen nieuws plaatsen; krijgt nu club_id mee."""
    from app.main import app
    from app.models import Bericht
    club = make_club(db_session)
    wl = make_member(db_session, lidnummer="UC191", role="lid")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    _no_csrf(app)
    with patch("app.routes.berichten.get_current_user", return_value=wl):
        response = await client.post("/berichten/verstuur", data={
            "is_nieuws": "1", "onderwerp": "Clubnieuws", "tekst": "X",
        })
    assert response.status_code == 302
    bericht = db_session.query(Bericht).first()
    assert bericht.is_nieuws is True
    assert bericht.club_id == club.id


async def test_uc192_bericht_naar_niet_clubgenoot_geweigerd(client, db_session):
    from app.main import app
    from app.models import Bericht
    club_a = make_club(db_session, "Club A")
    club_b = make_club(db_session, "Club B")
    lid_a = make_member(db_session, lidnummer="UC192A")
    lid_b = make_member(db_session, lidnummer="UC192B")
    make_member_club(db_session, lid_a.id, club_a.id)
    make_member_club(db_session, lid_b.id, club_b.id)
    _no_csrf(app)
    with patch("app.routes.berichten.get_current_user", return_value=lid_a):
        response = await client.post("/berichten/verstuur", data={
            "ontvanger_id": str(lid_b.id), "tekst": "Hallo",
        })
    assert "fout=ontvanger" in response.headers["location"]
    assert db_session.query(Bericht).count() == 0


async def test_uc193_nieuws_alleen_zichtbaar_voor_eigen_club(client, db_session):
    from app.main import app
    from app.models import Bericht
    club_a = make_club(db_session, "Club A")
    club_b = make_club(db_session, "Club B")
    wl_a = make_member(db_session, lidnummer="UC193W", role="wedstrijdleider")
    make_member_club(db_session, wl_a.id, club_a.id, role="wedstrijdleider")
    lid_a = make_member(db_session, lidnummer="UC193A")
    lid_b = make_member(db_session, lidnummer="UC193B")
    make_member_club(db_session, lid_a.id, club_a.id)
    make_member_club(db_session, lid_b.id, club_b.id)
    db_session.add(Bericht(afzender_id=wl_a.id, onderwerp="GeheimNieuwsA",
                           tekst="X", is_nieuws=True, club_id=club_a.id))
    db_session.commit()
    _no_csrf(app)
    with patch("app.routes.berichten.get_current_user", return_value=lid_a):
        eigen = await client.get("/berichten")
    with patch("app.routes.berichten.get_current_user", return_value=lid_b):
        ander = await client.get("/berichten")
    assert "GeheimNieuwsA" in eigen.text
    assert "GeheimNieuwsA" not in ander.text


# ══════════════════════════════════════════════════════════════════════════════
# H. GDPR, UITSLAGEN, RANKING & OVERIG (UC194–UC200)
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc194_gdpr_download_bevat_partner_registraties(client, db_session):
    import json
    from app.main import app
    from app.models import Registration, RegistrationType
    lid = make_member(db_session, lidnummer="UC194")
    ander = make_member(db_session, lidnummer="UC194B")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    db_session.add(Registration(evening_id=evening.id, person1_id=ander.id,
                                person2_id=lid.id, type=RegistrationType.los))
    db_session.commit()
    _set_auth(app, member=lid)
    response = await client.get("/gdpr/download")
    assert response.status_code == 200
    data = json.loads(response.text)
    assert len(data["aanmeldingen"]) == 1


async def test_uc195_gdpr_verwijder_account_ruimt_alles_op(client, db_session):
    from app.main import app
    from app.models import Member, MemberClub, PasswordResetToken
    club = make_club(db_session)
    lid = make_member(db_session, lidnummer="UC195")
    make_member_club(db_session, lid.id, club.id)
    db_session.add(PasswordResetToken(token="tok-uc195", member_id=lid.id))
    db_session.commit()
    lid_id = lid.id
    _set_auth(app, member=lid)
    response = await client.post("/gdpr/verwijder-account", data={})
    assert response.status_code == 302
    assert db_session.query(Member).filter(Member.id == lid_id).count() == 0
    assert db_session.query(MemberClub).filter(
        MemberClub.member_id == lid_id).count() == 0
    assert db_session.query(PasswordResetToken).count() == 0


async def test_uc196_uitslag_download_bestandsnaam_gesaneerd(client, db_session):
    """Regressie: rare tekens in de bestandsnaam braken de Content-Disposition."""
    from app.main import app
    from app.models import Uitslag
    lid = make_member(db_session, lidnummer="UC196")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    db_session.add(Uitslag(evening_id=evening.id, inhoud=b"<x/>",
                           bestandsnaam='ra"re\rnaam.xml'))
    db_session.commit()
    _set_auth(app, member=lid)
    response = await client.get(f"/uitslagen/{evening.id}/bestand")
    assert response.status_code == 200
    cd = response.headers["content-disposition"]
    assert "\r" not in cd and "\n" not in cd
    assert cd.count('"') == 2  # alleen de omhullende quotes


async def test_uc197_uitslagen_lijst(client, db_session):
    from app.main import app
    lid = make_member(db_session, lidnummer="UC197")
    _set_auth(app, member=lid)
    response = await client.get("/uitslagen")
    assert response.status_code == 200


async def test_uc198_ranking_pagina(client, db_session):
    lid = make_member(db_session, lidnummer="UC198")
    with patch("app.routes.rankings.get_current_user", return_value=lid):
        response = await client.get("/ranking")
    assert response.status_code == 200


async def test_uc199_mijn_overzicht(client, db_session):
    lid = make_member(db_session, lidnummer="UC199")
    with patch("app.routes.rankings.get_current_user", return_value=lid):
        response = await client.get("/ranking/mijn-overzicht")
    assert response.status_code == 200


async def test_uc200_publieke_paginas_en_404(client):
    assert (await client.get("/privacy")).status_code == 200
    assert (await client.get("/offline")).status_code == 200
    assert (await client.get("/pagina-die-niet-bestaat")).status_code == 404
