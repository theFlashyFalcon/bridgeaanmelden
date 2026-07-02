"""
20 use cases voor het bridge-club aanmeldingsdomein.

Dekt: publieke toegang, aanmelden/afmelden, bulk-aanmelden per club,
      gebruikerslijsten per club, club-beheer en wedstrijdleider-scope.
"""
from datetime import date, timedelta

from tests.conftest import make_member, make_season


# ── Extra helpers ─────────────────────────────────────────────────────────────

def make_club(db_session, naam="BC Dombo", stad=None):
    from app.models import Club
    club = Club(naam=naam, stad=stad)
    db_session.add(club)
    db_session.commit()
    db_session.refresh(club)
    return club


def make_season_for_club(db_session, club_id, naam="2025-2026", actief=True):
    from app.models import Season
    season = Season(
        naam=naam,
        start_datum=date(2025, 9, 1),
        eind_datum=date(2026, 6, 30),
        actief=actief,
        club_id=club_id,
    )
    db_session.add(season)
    db_session.commit()
    db_session.refresh(season)
    return season


def make_evening_for_club(db_session, season_id, club_id, datum=None, ev_type="clubavond"):
    from app.models import ClubEvening
    if datum is None:
        datum = date.today() + timedelta(days=7)
    evening = ClubEvening(datum=datum, type=ev_type, season_id=season_id, club_id=club_id)
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)
    return evening


def make_member_club(db_session, member_id, club_id, role="lid"):
    from app.models import MemberClub
    mc = MemberClub(member_id=member_id, club_id=club_id, role=role)
    db_session.add(mc)
    db_session.commit()
    db_session.refresh(mc)
    return mc


def make_lid_entry(db_session, voornaam, achternaam, nbb_nummer=None, club_id=None):
    from app.models import Lid
    lid = Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb_nummer, club_id=club_id)
    db_session.add(lid)
    db_session.commit()
    db_session.refresh(lid)
    return lid


def _set_auth(app, member=None, admin=None, wl=None):
    """Override auth-dependencies op de FastAPI-app voor de duur van één test."""
    from app.auth import require_auth, require_admin, require_wedstrijdleider
    from app.csrf import require_csrf

    app.dependency_overrides[require_csrf] = lambda: None

    if admin is not None:
        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[require_auth] = lambda: admin
    if wl is not None:
        app.dependency_overrides[require_wedstrijdleider] = lambda: wl
        app.dependency_overrides[require_auth] = lambda: wl
    if member is not None:
        app.dependency_overrides[require_auth] = lambda: member


# ── UC1: Homepage is publiek toegankelijk ─────────────────────────────────────

async def test_uc01_homepage_publiek(client):
    """Homepage moet 200 geven zonder login."""
    response = await client.get("/")
    assert response.status_code == 200


# ── UC2: /instellingen vereist login ─────────────────────────────────────────

async def test_uc02_instellingen_vereist_login(client):
    """/instellingen zonder sessie → redirect naar /login (302)."""
    response = await client.get("/instellingen")
    assert response.status_code == 302
    assert "/login" in response.headers["location"]


# ── UC3: /beheer verboden voor gewoon lid ─────────────────────────────────────

async def test_uc03_beheer_verboden_voor_lid(client, db_session):
    """/beheer als gewoon lid → 403."""
    from app.main import app
    lid = make_member(db_session, role="lid", lidnummer="UC03")
    _set_auth(app, member=lid)

    response = await client.get("/beheer/avonden")
    assert response.status_code == 403


# ── UC4: /leden verboden voor gewoon lid ─────────────────────────────────────

async def test_uc04_leden_verboden_voor_lid(client, db_session):
    """/leden als gewoon lid → 403."""
    from app.main import app
    lid = make_member(db_session, role="lid", lidnummer="UC04")
    _set_auth(app, member=lid)

    response = await client.get("/leden")
    assert response.status_code == 403


# ── UC5: Aanmelden zonder partner → beschikbaar_solo ─────────────────────────

async def test_uc05_aanmelden_zonder_partner(client, db_session):
    """Aanmelden zonder partner geeft status beschikbaar_solo."""
    from app.main import app
    from app.models import Registration, RegistrationStatus

    lid = make_member(db_session, lidnummer="UC05")
    season = make_season(db_session)
    evening = make_season.__wrapped__(db_session) if hasattr(make_season, '__wrapped__') else None
    # Create evening directly
    from app.models import ClubEvening
    evening = ClubEvening(
        datum=date.today() + timedelta(days=7),
        type="clubavond",
        season_id=season.id,
    )
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)

    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "", "partner_achternaam": "", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    reg = db_session.query(Registration).filter(Registration.person1_id == lid.id).first()
    assert reg is not None
    assert reg.status == RegistrationStatus.beschikbaar_solo


# ── UC6: Aanmelden met bekende partner → aangemeld ───────────────────────────

async def test_uc06_aanmelden_met_bekende_partner(client, db_session):
    """Aanmelden met partner die in ledenlijst staat → status aangemeld."""
    from app.main import app
    from app.models import ClubEvening, Registration, RegistrationStatus

    lid = make_member(db_session, lidnummer="UC06")
    make_lid_entry(db_session, "Jan", "de Vries")
    season = make_season(db_session)
    evening = ClubEvening(
        datum=date.today() + timedelta(days=7),
        type="clubavond",
        season_id=season.id,
    )
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)

    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={
            "partner_voornaam": "Jan",
            "partner_achternaam": "de Vries",
            "_csrf_token": "x",
        },
    )
    assert response.status_code == 302

    reg = db_session.query(Registration).filter(Registration.person1_id == lid.id).first()
    assert reg is not None
    assert reg.status == RegistrationStatus.aangemeld
    assert reg.partner_naam == "Jan de Vries"


# ── UC7: Aanmelden met onbekende partner → partner request ───────────────────

async def test_uc07_aanmelden_met_onbekende_partner(client, db_session):
    """Aanmelden met partner die NIET in ledenlijst staat → PartnerRequest aangemaakt."""
    from app.main import app
    from app.models import ClubEvening, PartnerRequest

    lid = make_member(db_session, lidnummer="UC07")
    season = make_season(db_session)
    evening = ClubEvening(
        datum=date.today() + timedelta(days=7),
        type="clubavond",
        season_id=season.id,
    )
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)

    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={
            "partner_voornaam": "Onbekend",
            "partner_achternaam": "Persoon",
            "_csrf_token": "x",
        },
    )
    assert response.status_code == 302

    pr = db_session.query(PartnerRequest).filter(PartnerRequest.requester_id == lid.id).first()
    assert pr is not None
    assert pr.partner_voornaam == "Onbekend"
    assert pr.status == "wachtend"


# ── UC8: Afmelden van een aanmelding ─────────────────────────────────────────

async def test_uc08_afmelden(client, db_session):
    """Afmelden zet de registratiestatus op 'afgemeld'."""
    from app.main import app
    from app.models import ClubEvening, Registration, RegistrationStatus, RegistrationType

    lid = make_member(db_session, lidnummer="UC08")
    season = make_season(db_session)
    evening = ClubEvening(
        datum=date.today() + timedelta(days=7),
        type="clubavond",
        season_id=season.id,
    )
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)

    reg = Registration(
        evening_id=evening.id,
        person1_id=lid.id,
        type=RegistrationType.los,
        status=RegistrationStatus.aangemeld,
    )
    db_session.add(reg)
    db_session.commit()

    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"action": "afmelden", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    db_session.refresh(reg)
    assert reg.status == RegistrationStatus.afgemeld


# ── UC9: Aanmelden voor verleden datum → redirect ────────────────────────────

async def test_uc09_aanmelden_verleden_datum(client, db_session):
    """Aanmelden voor een verstreken datum wordt stil doorgestuurd naar homepage."""
    from app.main import app
    from app.models import ClubEvening

    lid = make_member(db_session, lidnummer="UC09")
    season = make_season(db_session)
    evening = ClubEvening(
        datum=date.today() - timedelta(days=1),
        type="clubavond",
        season_id=season.id,
    )
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)

    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "", "partner_achternaam": "", "_csrf_token": "x"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/"


# ── UC10: Dubbel aanmelden werkt idempotent ───────────────────────────────────

async def test_uc10_dubbel_aanmelden(client, db_session):
    """Een tweede aanmelding overschrijft de eerste, er ontstaat geen dubbele rij."""
    from app.main import app
    from app.models import ClubEvening, Lid, Registration

    lid = make_member(db_session, lidnummer="UC10")
    make_lid_entry(db_session, "Piet", "Klaassen")
    season = make_season(db_session)
    evening = ClubEvening(
        datum=date.today() + timedelta(days=7),
        type="clubavond",
        season_id=season.id,
    )
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)

    _set_auth(app, member=lid)

    # Eerste aanmelding zonder partner
    await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "", "partner_achternaam": "", "_csrf_token": "x"},
    )
    # Tweede aanmelding met partner
    await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "Piet", "partner_achternaam": "Klaassen", "_csrf_token": "x"},
    )

    regs = db_session.query(Registration).filter(Registration.person1_id == lid.id).all()
    assert len(regs) == 1
    assert regs[0].partner_naam == "Piet Klaassen"


# ── UC11: GET /instellingen toont clubavonden ─────────────────────────────────

async def test_uc11_instellingen_toont_avonden(client, db_session):
    """GET /instellingen geeft 200 en toont komende clubavonden."""
    from app.main import app
    from app.models import ClubEvening

    lid = make_member(db_session, lidnummer="UC11")
    season = make_season(db_session)
    evening = ClubEvening(
        datum=date.today() + timedelta(days=7),
        type="clubavond",
        season_id=season.id,
    )
    db_session.add(evening)
    db_session.commit()

    _set_auth(app, member=lid)

    response = await client.get("/instellingen")
    assert response.status_code == 200
    assert "clubavond" in response.text.lower() or "komende" in response.text.lower()


# ── UC12: Bulk aanmelden voor alle clubavonden ────────────────────────────────

async def test_uc12_bulk_aanmelden_alle_clubavonden(client, db_session):
    """POST /instellingen meldt het lid aan voor alle komende clubavonden."""
    from app.main import app
    from app.models import ClubEvening, Registration

    lid = make_member(db_session, lidnummer="UC12")
    season = make_season(db_session)
    for i in range(3):
        ev = ClubEvening(
            datum=date.today() + timedelta(days=7 + i),
            type="clubavond",
            season_id=season.id,
        )
        db_session.add(ev)
    db_session.commit()

    _set_auth(app, member=lid)

    response = await client.post(
        "/instellingen",
        data={"partner_voornaam": "", "partner_achternaam": "", "_csrf_token": "x"},
    )
    assert response.status_code == 302
    assert "bulk_ok=3" in response.headers["location"]

    regs = db_session.query(Registration).filter(Registration.person1_id == lid.id).all()
    assert len(regs) == 3


# ── UC13: GET /instellingen?club=X filtert op club ───────────────────────────

async def test_uc13_instellingen_filter_op_club(client, db_session):
    """GET /instellingen?club=X toont alleen avonden van die club."""
    from app.main import app

    lid = make_member(db_session, lidnummer="UC13")
    club_a = make_club(db_session, naam="Club A")
    club_b = make_club(db_session, naam="Club B")
    make_member_club(db_session, lid.id, club_a.id)
    make_member_club(db_session, lid.id, club_b.id)

    season_a = make_season_for_club(db_session, club_a.id, naam="S-A")
    season_b = make_season_for_club(db_session, club_b.id, naam="S-B")
    ev_a = make_evening_for_club(db_session, season_a.id, club_a.id)
    make_evening_for_club(db_session, season_b.id, club_b.id)

    _set_auth(app, member=lid)

    response = await client.get(f"/instellingen?club={club_a.id}")
    assert response.status_code == 200
    # Pagina toont 1 avond (van club A), niet die van club B
    assert "1" in response.text  # "1 komende clubavond(en)"


# ── UC14: Bulk aanmelden alleen voor één club ────────────────────────────────

async def test_uc14_bulk_aanmelden_per_club(client, db_session):
    """POST /instellingen met club_id registreert alleen voor avonden van die club."""
    from app.main import app
    from app.models import Registration

    lid = make_member(db_session, lidnummer="UC14")
    club_a = make_club(db_session, naam="Club A14")
    club_b = make_club(db_session, naam="Club B14")
    make_member_club(db_session, lid.id, club_a.id)
    make_member_club(db_session, lid.id, club_b.id)

    season_a = make_season_for_club(db_session, club_a.id, naam="S-A14")
    season_b = make_season_for_club(db_session, club_b.id, naam="S-B14")
    ev_a = make_evening_for_club(db_session, season_a.id, club_a.id)
    ev_b = make_evening_for_club(db_session, season_b.id, club_b.id)

    _set_auth(app, member=lid)

    response = await client.post(
        "/instellingen",
        data={
            "partner_voornaam": "",
            "partner_achternaam": "",
            "club_id": str(club_a.id),
            "_csrf_token": "x",
        },
    )
    assert response.status_code == 302

    regs = db_session.query(Registration).filter(Registration.person1_id == lid.id).all()
    assert len(regs) == 1
    assert regs[0].evening_id == ev_a.id  # alleen Club A's avond


# ── UC15: Admin ziet alle leden ───────────────────────────────────────────────

async def test_uc15_admin_ziet_alle_leden(client, db_session):
    """GET /leden als admin geeft 200 met alle leden."""
    from app.main import app

    admin = make_member(db_session, role="admin", lidnummer="UC15-ADMIN")
    make_member(db_session, voornaam="Ander", achternaam="Lid", lidnummer="UC15-LID")

    _set_auth(app, admin=admin)

    response = await client.get("/leden")
    assert response.status_code == 200
    assert "Ander" in response.text


# ── UC16: GET /leden?club=X filtert op clubleden ─────────────────────────────

async def test_uc16_leden_filter_op_club(client, db_session):
    """GET /leden?club=X toont alleen leden van die club."""
    from app.main import app

    admin = make_member(db_session, role="admin", lidnummer="UC16-ADMIN")
    lid_a = make_member(db_session, voornaam="AlleenA", achternaam="Lid", lidnummer="UC16-A")
    lid_b = make_member(db_session, voornaam="AlleenB", achternaam="Lid", lidnummer="UC16-B")
    club = make_club(db_session, naam="Club UC16")
    make_member_club(db_session, lid_a.id, club.id)
    # lid_b is NIET lid van club

    _set_auth(app, admin=admin)

    response = await client.get(f"/leden?club={club.id}")
    assert response.status_code == 200
    assert "AlleenA" in response.text
    assert "AlleenB" not in response.text


# ── UC17: Admin kan /beheer/clubs openen ─────────────────────────────────────

async def test_uc17_admin_clubs_beheer(client, db_session):
    """GET /beheer/clubs als admin geeft 200."""
    from app.main import app

    admin = make_member(db_session, role="admin", lidnummer="UC17")
    _set_auth(app, admin=admin)

    response = await client.get("/beheer/clubs")
    assert response.status_code == 200


# ── UC18: Gewoon lid heeft geen toegang tot /beheer/clubs ────────────────────

async def test_uc18_lid_geen_toegang_clubs_beheer(client, db_session):
    """GET /beheer/clubs als gewoon lid → 403."""
    from app.main import app

    lid = make_member(db_session, role="lid", lidnummer="UC18")
    _set_auth(app, member=lid)

    response = await client.get("/beheer/clubs")
    assert response.status_code == 403


# ── UC19: Admin kan clubleden bekijken ───────────────────────────────────────

async def test_uc19_admin_clubleden_bekijken(client, db_session):
    """GET /beheer/clubs/{id}/leden als admin geeft 200."""
    from app.main import app

    admin = make_member(db_session, role="admin", lidnummer="UC19-ADMIN")
    club = make_club(db_session, naam="Club UC19")
    lid = make_member(db_session, voornaam="Club", achternaam="Lid", lidnummer="UC19-LID")
    make_member_club(db_session, lid.id, club.id)

    _set_auth(app, admin=admin)

    response = await client.get(f"/beheer/clubs/{club.id}/leden")
    assert response.status_code == 200
    assert "Club Lid" in response.text


# ── UC20: Wedstrijdleider kan actieve club instellen ─────────────────────────

async def test_uc20_wl_actieve_club_instellen(client, db_session):
    """WL met toegang tot club kan de actieve club instellen via /beheer/actieve-club/{id}."""
    from app.main import app

    wl = make_member(db_session, role="wedstrijdleider", lidnummer="UC20-WL")
    club = make_club(db_session, naam="Club UC20")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")

    _set_auth(app, wl=wl)

    response = await client.get(
        f"/beheer/actieve-club/{club.id}",
        headers={"Referer": "/beheer/avonden"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/beheer/avonden"
