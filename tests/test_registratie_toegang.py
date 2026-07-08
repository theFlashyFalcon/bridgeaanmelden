"""
Registratie- en clubtoegangsflow.

Dekt de gewenste flow:
- Een account aanmaken kan altijd (lidnummer, e-mail, naam, wachtwoord).
- Staat je lidnummer in de ledenlijst van een club → automatisch toegang.
- Anders: account zonder club; de wedstrijdleider van de club voegt je toe.
"""
from tests.conftest import make_member
from tests.test_use_cases import (
    _set_auth,
    make_club,
    make_evening_for_club,
    make_lid_entry,
    make_member_club,
    make_season_for_club,
)


def _registratie_form(**overrides):
    form = {
        "voornaam": "Anna",
        "achternaam": "Devries",
        "email": "anna@test.nl",
        "lidnummer": "777001",
        "password": "wachtwoord123",
        "password2": "wachtwoord123",
        "toestemming": "1",
        "_csrf_token": "x",
    }
    form.update(overrides)
    return form


# ── Registreren: lidnummer in ledenlijst → direct toegang ────────────────────

async def test_registreren_ledenlijst_geeft_direct_toegang(client, db_session):
    from app.main import app
    from app.models import Member, MemberClub

    club = make_club(db_session, naam="BC Ledenlijst")
    make_lid_entry(db_session, "Anna", "Devries", nbb_nummer="777001", club_id=club.id)
    _set_auth(app)  # alleen CSRF uitschakelen

    response = await client.post("/registreren", data=_registratie_form())
    assert response.status_code == 302
    assert response.headers["location"] == "/"

    member = db_session.query(Member).filter(Member.lidnummer == "777001").first()
    assert member is not None
    assert member.email == "anna@test.nl"

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == member.id, MemberClub.club_id == club.id
    ).first()
    assert mc is not None


# ── Registreren: onbekend lidnummer → account zonder club, geen aanvraag ─────

async def test_registreren_onbekend_lidnummer_maakt_toch_account(client, db_session):
    from app.main import app
    from app.models import AccountRequest, Member, MemberClub

    make_club(db_session, naam="BC Zonder Anna")
    _set_auth(app)

    response = await client.post(
        "/registreren",
        data=_registratie_form(lidnummer="999999", email="onbekend@test.nl"),
    )
    assert response.status_code == 302

    member = db_session.query(Member).filter(Member.lidnummer == "999999").first()
    assert member is not None

    koppelingen = db_session.query(MemberClub).filter(
        MemberClub.member_id == member.id
    ).count()
    assert koppelingen == 0

    # Nieuwe flow: er wordt geen goedkeuringsaanvraag meer aangemaakt
    assert db_session.query(AccountRequest).count() == 0


# ── Registreren: NBB-treffer maar andere naam → account wordt geweigerd ──────

async def test_registreren_naam_mismatch_weigert_account(client, db_session):
    from app.main import app
    from app.models import Member

    club = make_club(db_session, naam="BC Mismatch")
    make_lid_entry(db_session, "Piet", "Jansen", nbb_nummer="777003", club_id=club.id)
    _set_auth(app)

    response = await client.post(
        "/registreren",
        data=_registratie_form(
            voornaam="Onbekende", achternaam="Persoon",
            lidnummer="777003", email="vreemd@test.nl",
        ),
    )
    assert response.status_code == 422
    assert "andere naam" in response.text

    assert db_session.query(Member).filter(Member.lidnummer == "777003").count() == 0


# ── Registreren: bestaand account → melding, geen tweede account ─────────────

async def test_registreren_bestaand_account_geeft_melding(client, db_session):
    from app.main import app
    from app.models import Member

    make_member(db_session, voornaam="Anna", achternaam="Devries", lidnummer="777001")
    _set_auth(app)

    response = await client.post("/registreren", data=_registratie_form())
    assert response.status_code == 422
    assert "al een account" in response.text

    assert db_session.query(Member).filter(Member.lidnummer == "777001").count() == 1


# ── Wedstrijdleider: leden toevoegen aan eigen club ──────────────────────────

async def test_wl_kan_lid_toevoegen_aan_eigen_club(client, db_session):
    from app.main import app
    from app.models import MemberClub

    club = make_club(db_session, naam="BC Eigen")
    wl = make_member(db_session, role="wedstrijdleider", lidnummer="WL-1")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    nieuw = make_member(db_session, voornaam="Nieuw", achternaam="Clublid",
                        lidnummer="NW-1")
    _set_auth(app, wl=wl)

    response = await client.post(
        f"/beheer/clubs/{club.id}/leden/toevoegen",
        data={"member_id": str(nieuw.id), "role": "lid", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == nieuw.id, MemberClub.club_id == club.id
    ).first()
    assert mc is not None and mc.role == "lid"


async def test_wl_kan_geen_lid_toevoegen_aan_andere_club(client, db_session):
    from app.main import app
    from app.models import MemberClub

    eigen_club = make_club(db_session, naam="BC Eigen")
    andere_club = make_club(db_session, naam="BC Andermans")
    wl = make_member(db_session, role="wedstrijdleider", lidnummer="WL-2")
    make_member_club(db_session, wl.id, eigen_club.id, role="wedstrijdleider")
    nieuw = make_member(db_session, voornaam="Nieuw", achternaam="Lid",
                        lidnummer="NW-2")
    _set_auth(app, wl=wl)

    response = await client.post(
        f"/beheer/clubs/{andere_club.id}/leden/toevoegen",
        data={"member_id": str(nieuw.id), "role": "lid", "_csrf_token": "x"},
    )
    assert response.status_code == 403

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == nieuw.id, MemberClub.club_id == andere_club.id
    ).first()
    assert mc is None


async def test_wl_kan_geen_admin_rol_toekennen(client, db_session):
    from app.main import app
    from app.models import MemberClub

    club = make_club(db_session, naam="BC Escalatie")
    wl = make_member(db_session, role="wedstrijdleider", lidnummer="WL-3")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    nieuw = make_member(db_session, voornaam="Zogenaamd", achternaam="Admin",
                        lidnummer="NW-3")
    _set_auth(app, wl=wl)

    response = await client.post(
        f"/beheer/clubs/{club.id}/leden/toevoegen",
        data={"member_id": str(nieuw.id), "role": "admin", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == nieuw.id, MemberClub.club_id == club.id
    ).first()
    assert mc is not None and mc.role == "lid"

    db_session.refresh(nieuw)
    assert nieuw.role == "lid"


async def test_wl_kan_clubadmin_niet_verwijderen(client, db_session):
    from app.main import app
    from app.models import MemberClub

    club = make_club(db_session, naam="BC Beschermd")
    wl = make_member(db_session, role="wedstrijdleider", lidnummer="WL-4")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    club_admin = make_member(db_session, voornaam="Club", achternaam="Admin",
                             role="admin", lidnummer="CA-4")
    make_member_club(db_session, club_admin.id, club.id, role="admin")
    _set_auth(app, wl=wl)

    response = await client.post(
        f"/beheer/clubs/{club.id}/leden/{club_admin.id}/verwijder",
        data={"_csrf_token": "x"},
    )
    assert response.status_code == 302
    assert "fout=rol" in response.headers["location"]

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == club_admin.id, MemberClub.club_id == club.id
    ).first()
    assert mc is not None


async def test_gewoon_lid_geen_toegang_tot_clubleden_beheer(client, db_session):
    from app.main import app

    club = make_club(db_session, naam="BC Dicht")
    lid = make_member(db_session, role="lid", lidnummer="LID-5")
    make_member_club(db_session, lid.id, club.id, role="lid")
    _set_auth(app, member=lid)

    response = await client.get(f"/beheer/clubs/{club.id}/leden")
    assert response.status_code == 403


# ── Lid zonder club: melding en geen avonden van andere clubs ────────────────

async def test_lid_zonder_club_ziet_melding_en_geen_clubavonden(client, db_session):
    from app.auth import get_current_user
    from app.main import app

    club = make_club(db_session, naam="BC Verborgen")
    season = make_season_for_club(db_session, club.id)
    evening = make_evening_for_club(db_session, season.id, club.id)

    clubloos = make_member(db_session, voornaam="Zwevend", achternaam="Lid",
                           lidnummer="ZW-1")
    app.dependency_overrides[get_current_user] = lambda: clubloos
    _set_auth(app, member=clubloos)

    response = await client.get("/")
    assert response.status_code == 200
    assert "Nog geen toegang tot een club" in response.text
    assert f"/aanmelden/{evening.id}" not in response.text


async def test_lid_met_club_ziet_geen_melding(client, db_session):
    from app.auth import get_current_user
    from app.main import app

    club = make_club(db_session, naam="BC Thuis")
    lid = make_member(db_session, lidnummer="TH-1")
    make_member_club(db_session, lid.id, club.id, role="lid")
    app.dependency_overrides[get_current_user] = lambda: lid
    _set_auth(app, member=lid)

    response = await client.get("/")
    assert response.status_code == 200
    assert "Nog geen toegang tot een club" not in response.text
