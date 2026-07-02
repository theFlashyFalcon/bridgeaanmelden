"""
50 aanvullende use cases — volledige dekking van de hele bridge-aanmeldingsapp.
Nummering: UC21–UC70 (aanvullend op de 20 in test_use_cases.py).
"""
import io
from datetime import date, timedelta
from unittest.mock import patch

from tests.conftest import make_member, make_season


# ── Gedeelde helpers ──────────────────────────────────────────────────────────

def make_club(db_session, naam="BC Test", stad=None):
    from app.models import Club
    club = Club(naam=naam, stad=stad)
    db_session.add(club)
    db_session.commit()
    db_session.refresh(club)
    return club


def make_member_club(db_session, member_id, club_id, role="lid"):
    from app.models import MemberClub
    mc = MemberClub(member_id=member_id, club_id=club_id, role=role)
    db_session.add(mc)
    db_session.commit()
    db_session.refresh(mc)
    return mc


def make_evening(db_session, season_id, club_id=None, ev_type="clubavond", datum=None,
                 deelnemers_type="paren"):
    from app.models import ClubEvening
    if datum is None:
        datum = date.today() + timedelta(days=7)
    ev = ClubEvening(datum=datum, type=ev_type, season_id=season_id,
                     club_id=club_id, deelnemers_type=deelnemers_type)
    db_session.add(ev)
    db_session.commit()
    db_session.refresh(ev)
    return ev


def make_past_evening(db_session, season_id, club_id=None, ev_type="clubavond"):
    from app.models import ClubEvening
    ev = ClubEvening(datum=date.today() - timedelta(days=7), type=ev_type,
                     season_id=season_id, club_id=club_id)
    db_session.add(ev)
    db_session.commit()
    db_session.refresh(ev)
    return ev


def make_registration(db_session, member_id, evening_id, status="aangemeld"):
    from app.models import Registration, RegistrationStatus, RegistrationType
    reg = Registration(
        evening_id=evening_id,
        person1_id=member_id,
        type=RegistrationType.los,
        status=getattr(RegistrationStatus, status),
    )
    db_session.add(reg)
    db_session.commit()
    db_session.refresh(reg)
    return reg


def make_lid_entry(db_session, voornaam, achternaam, nbb_nummer=None, club_id=None):
    from app.models import Lid
    lid = Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb_nummer, club_id=club_id)
    db_session.add(lid)
    db_session.commit()
    db_session.refresh(lid)
    return lid


def _set_auth(app, member=None, admin=None, wl=None):
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


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIEKE PAGINA'S & AUTH FLOW
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc21_homepage_type_filter(client, db_session):
    """GET /?type=clubavond werkt zonder crash."""
    response = await client.get("/?type=clubavond")
    assert response.status_code == 200


async def test_uc22_deelnemers_bekijken(client, db_session):
    """Ingelogd lid ziet deelnemerslijst van een avond."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC22")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    _set_auth(app, member=lid)

    response = await client.get(f"/deelnemers/{evening.id}")
    assert response.status_code == 200


async def test_uc23_deelnemers_404(client, db_session):
    """Deelnemerslijst voor onbestaand evenement geeft 404."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC23")
    _set_auth(app, member=lid)

    response = await client.get("/deelnemers/99999")
    assert response.status_code == 404


async def test_uc24_registreer_pagina(client):
    """GET /registreren geeft 200 zonder login."""
    response = await client.get("/registreren")
    assert response.status_code == 200


async def test_uc25_wachtwoord_vergeten(client):
    """GET /wachtwoord-vergeten geeft 200 zonder login."""
    response = await client.get("/wachtwoord-vergeten")
    assert response.status_code == 200


async def test_uc26_logout_redirect(client):
    """GET /logout stuurt door naar / (homepage) wanneer niet ingelogd."""
    response = await client.get("/logout")
    assert response.status_code == 302
    assert response.headers["location"] == "/"


async def test_uc27_login_pagina(client):
    """GET /login geeft 200 voor niet-ingelogde bezoeker."""
    response = await client.get("/login")
    assert response.status_code == 200


async def test_uc28_admin_bericht_contact(client):
    """POST /admin-bericht sla een contactbericht op en redirect."""
    from app.csrf import require_csrf
    from app.main import app
    app.dependency_overrides[require_csrf] = lambda: None

    response = await client.post(
        "/admin-bericht",
        data={"naam": "Jan Test", "email": "jan@test.nl",
              "bericht": "Dit is een test", "_csrf_token": "x"},
    )
    assert response.status_code == 302


async def test_uc29_aanmelden_form_get(client, db_session):
    """GET /aanmelden/{id} toont het aanmeldformulier voor een avond."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC29")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    _set_auth(app, member=lid)

    response = await client.get(f"/aanmelden/{evening.id}")
    assert response.status_code == 200


async def test_uc30_aanmelden_form_404(client, db_session):
    """GET /aanmelden/99999 geeft 404 voor onbestaand evenement."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC30")
    _set_auth(app, member=lid)

    response = await client.get("/aanmelden/99999")
    assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# AANMELDEN — EDGE CASES
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc31_aanmelden_individueel(client, db_session):
    """Aanmelden voor individueel evenement heeft geen partner nodig."""
    from app.main import app
    from app.models import Registration, RegistrationStatus

    lid = make_member(db_session, lidnummer="UC31")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="individueel")
    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"_csrf_token": "x"},
    )
    assert response.status_code == 302

    reg = db_session.query(Registration).filter(Registration.person1_id == lid.id).first()
    assert reg is not None
    assert reg.status == RegistrationStatus.aangemeld
    assert reg.partner_naam is None


async def test_uc32_aanmelden_viertallen(client, db_session):
    """Aanmelden voor viertallen slaat teamnaam en partners op."""
    from app.main import app
    from app.models import Registration

    lid = make_member(db_session, lidnummer="UC32")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id, ev_type="speciaal", deelnemers_type="viertallen")
    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={
            "team_naam": "Team Alpha",
            "partner_voornaam": "Jan", "partner_achternaam": "Jansen",
            "partner2_voornaam": "Piet", "partner2_achternaam": "Pieters",
            "partner3_voornaam": "Klaas", "partner3_achternaam": "Klaassen",
            "_csrf_token": "x",
        },
    )
    assert response.status_code == 302

    reg = db_session.query(Registration).filter(Registration.person1_id == lid.id).first()
    assert reg is not None
    assert reg.team_naam == "Team Alpha"
    assert reg.partner_naam == "Jan Jansen"


async def test_uc33_aanmelden_te_laat(client, db_session):
    """Aanmelden na inschrijftermijn zet te_laat=True op de registratie."""
    from app.main import app
    from app.models import ClubEvening, Registration

    lid = make_member(db_session, lidnummer="UC33")
    make_lid_entry(db_session, "Vaste", "Partner")
    season = make_season(db_session)
    evening = ClubEvening(
        datum=date.today() + timedelta(days=1),
        type="clubavond",
        season_id=season.id,
        inschrijftermijn_uren=999,
    )
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)
    _set_auth(app, member=lid)

    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "Vaste", "partner_achternaam": "Partner",
              "_csrf_token": "x"},
    )
    assert response.status_code == 302
    assert "te_laat=1" in response.headers["location"]

    reg = db_session.query(Registration).filter(Registration.person1_id == lid.id).first()
    assert reg is not None and reg.te_laat is True


async def test_uc34_herhaal_stop(client, db_session):
    """POST /instellingen/herhaal/{id}/stop zet herhaalaanmelding op inactief."""
    from app.main import app
    from app.models import RecurringRegistration

    lid = make_member(db_session, lidnummer="UC34")
    rr = RecurringRegistration(
        member_id=lid.id, event_type="clubavond",
        interval=1, actief=True, referentie_datum=date.today(),
    )
    db_session.add(rr)
    db_session.commit()
    db_session.refresh(rr)
    _set_auth(app, member=lid)

    response = await client.post(
        f"/instellingen/herhaal/{rr.id}/stop",
        data={"_csrf_token": "x"},
    )
    assert response.status_code == 302

    db_session.refresh(rr)
    assert rr.actief is False


async def test_uc35_weergave_voorkeuren_opslaan(client, db_session):
    """POST /instellingen/verborgen-types slaat verborgen types op voor het lid."""
    from app.main import app

    lid = make_member(db_session, lidnummer="UC35")
    _set_auth(app, member=lid)

    response = await client.post(
        "/instellingen/verborgen-types",
        data={"toon_clubavond": "on", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    db_session.refresh(lid)
    assert lid.verborgen_types is not None
    assert "training" in lid.verborgen_types


# ══════════════════════════════════════════════════════════════════════════════
# BULK AANMELDEN / AFMELDEN
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc36_voor_alles_aanmelden(client, db_session):
    """POST /voor-alles-aanmelden registreert lid voor alle komende avonden."""
    from app.main import app
    from app.models import Registration

    lid = make_member(db_session, lidnummer="UC36")
    season = make_season(db_session)
    for ev_type in ["clubavond", "speciaal"]:
        make_evening(db_session, season.id, ev_type=ev_type, deelnemers_type="individueel")
    _set_auth(app, member=lid)

    response = await client.post("/voor-alles-aanmelden", data={"_csrf_token": "x"})
    assert response.status_code == 302
    assert "bulk_ok=2" in response.headers["location"]

    regs = db_session.query(Registration).filter(Registration.person1_id == lid.id).all()
    assert len(regs) == 2


async def test_uc37_voor_alles_afmelden(client, db_session):
    """POST /voor-alles-afmelden cancelt alle aankomende aanmeldingen."""
    from app.main import app
    from app.models import RegistrationStatus

    lid = make_member(db_session, lidnummer="UC37")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    reg = make_registration(db_session, lid.id, evening.id)
    _set_auth(app, member=lid)

    response = await client.post("/voor-alles-afmelden", data={"_csrf_token": "x"})
    assert response.status_code == 302
    assert "afgemeld_alles=1" in response.headers["location"]

    db_session.refresh(reg)
    assert reg.status == RegistrationStatus.afgemeld


async def test_uc38_definitief_aanmelden_clubavond(client, db_session):
    """POST /definitief-aanmelden/clubavond registreert en maakt herhaalaanmelding."""
    from app.main import app
    from app.models import RecurringRegistration, Registration

    lid = make_member(db_session, lidnummer="UC38")
    season = make_season(db_session)
    make_evening(db_session, season.id, deelnemers_type="individueel")
    _set_auth(app, member=lid)

    response = await client.post(
        "/definitief-aanmelden/clubavond", data={"_csrf_token": "x"}
    )
    assert response.status_code == 302

    regs = db_session.query(Registration).filter(Registration.person1_id == lid.id).all()
    assert len(regs) == 1

    rr = db_session.query(RecurringRegistration).filter(
        RecurringRegistration.member_id == lid.id, RecurringRegistration.actief == True  # noqa: E712
    ).first()
    assert rr is not None


async def test_uc39_definitief_aanmelden_speciaal(client, db_session):
    """POST /definitief-aanmelden/speciaal registreert voor speciale avonden."""
    from app.main import app
    from app.models import Registration

    lid = make_member(db_session, lidnummer="UC39")
    season = make_season(db_session)
    make_evening(db_session, season.id, ev_type="speciaal", deelnemers_type="individueel")
    _set_auth(app, member=lid)

    response = await client.post(
        "/definitief-aanmelden/speciaal", data={"_csrf_token": "x"}
    )
    assert response.status_code == 302

    regs = db_session.query(Registration).filter(Registration.person1_id == lid.id).all()
    assert len(regs) == 1


async def test_uc40_profiel_pagina(client, db_session):
    """GET /profiel geeft 200 en toont de voornaam van het lid."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC40")
    _set_auth(app, member=lid)

    response = await client.get("/profiel")
    assert response.status_code == 200
    assert "Test" in response.text


# ══════════════════════════════════════════════════════════════════════════════
# BERICHTEN
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc41_berichten_inbox(client, db_session):
    """GET /berichten geeft 200 voor een ingelogd lid."""
    lid = make_member(db_session, lidnummer="UC41")

    with patch("app.routes.berichten.get_current_user", return_value=lid):
        response = await client.get("/berichten")
    assert response.status_code == 200


async def test_uc42_bericht_versturen(client, db_session):
    """POST /berichten/verstuur maakt een bericht aan van afzender naar ontvanger."""
    from app.csrf import require_csrf
    from app.main import app
    from app.models import Bericht

    afzender = make_member(db_session, lidnummer="UC42-A")
    ontvanger = make_member(db_session, voornaam="Bob", achternaam="Bekker", lidnummer="UC42-B")
    app.dependency_overrides[require_csrf] = lambda: None

    with patch("app.routes.berichten.get_current_user", return_value=afzender):
        response = await client.post(
            "/berichten/verstuur",
            data={"ontvanger_id": str(ontvanger.id), "tekst": "Hoi Bob!",
                  "_csrf_token": "x"},
        )
    assert response.status_code == 302

    bericht = db_session.query(Bericht).filter(Bericht.afzender_id == afzender.id).first()
    assert bericht is not None
    assert bericht.ontvanger_id == ontvanger.id
    assert bericht.tekst == "Hoi Bob!"


async def test_uc43_bericht_aan_jezelf_verboden(client, db_session):
    """Bericht versturen naar jezelf redirect met fout=ontvanger."""
    from app.csrf import require_csrf
    from app.main import app

    lid = make_member(db_session, lidnummer="UC43")
    app.dependency_overrides[require_csrf] = lambda: None

    with patch("app.routes.berichten.get_current_user", return_value=lid):
        response = await client.post(
            "/berichten/verstuur",
            data={"ontvanger_id": str(lid.id), "tekst": "Hallo mij",
                  "_csrf_token": "x"},
        )
    assert response.status_code == 302
    assert "fout=ontvanger" in response.headers["location"]


async def test_uc44_berichten_telling_unauthenticated(client):
    """GET /berichten/telling zonder login geeft JSON {"ongelezen": 0}."""
    response = await client.get("/berichten/telling")
    assert response.status_code == 200
    assert response.json()["ongelezen"] == 0


async def test_uc45_bericht_antwoord(client, db_session):
    """POST /berichten/{id}/antwoord voegt een reply toe aan het gesprek."""
    from app.models import Bericht

    afzender = make_member(db_session, lidnummer="UC45-A")
    ontvanger = make_member(db_session, voornaam="Claire", achternaam="Costa", lidnummer="UC45-B")

    root = Bericht(afzender_id=afzender.id, ontvanger_id=ontvanger.id, tekst="Eerste bericht")
    db_session.add(root)
    db_session.commit()
    db_session.refresh(root)

    from app.csrf import require_csrf
    from app.main import app
    app.dependency_overrides[require_csrf] = lambda: None

    with patch("app.routes.berichten.get_current_user", return_value=ontvanger):
        response = await client.post(
            f"/berichten/{root.id}/antwoord",
            data={"tekst": "Antwoord terug!", "_csrf_token": "x"},
        )
    assert response.status_code == 302

    replies = db_session.query(Bericht).filter(Bericht.parent_id == root.id).all()
    assert len(replies) == 1
    assert replies[0].tekst == "Antwoord terug!"


# ══════════════════════════════════════════════════════════════════════════════
# UITSLAGEN
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc46_uitslagen_pagina(client, db_session):
    """GET /uitslagen geeft 200 voor ingelogd lid."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC46")
    _set_auth(app, member=lid)

    response = await client.get("/uitslagen")
    assert response.status_code == 200


async def test_uc47_uitslag_upload_form(client, db_session):
    """GET /uitslagen/uploaden geeft 200 voor wedstrijdleider."""
    from app.main import app
    wl = make_member(db_session, role="wedstrijdleider", lidnummer="UC47")
    _set_auth(app, wl=wl)

    response = await client.get("/uitslagen/uploaden")
    assert response.status_code == 200


async def test_uc48_uitslag_uploaden(client, db_session):
    """POST /uitslagen/{id}/uploaden slaat het bestand op in de database."""
    from app.main import app
    from app.models import Uitslag

    wl = make_member(db_session, role="wedstrijdleider", lidnummer="UC48")
    season = make_season(db_session)
    evening = make_past_evening(db_session, season.id)
    _set_auth(app, wl=wl)

    file_bytes = b"pdf inhoud"
    response = await client.post(
        f"/uitslagen/{evening.id}/uploaden",
        files={"bestand": ("uitslag.pdf", io.BytesIO(file_bytes), "application/pdf")},
        data={"_csrf_token": "x"},
    )
    assert response.status_code == 302

    uitslag = db_session.query(Uitslag).filter(Uitslag.evening_id == evening.id).first()
    assert uitslag is not None
    assert uitslag.inhoud == file_bytes


async def test_uc49_uitslag_verwijderen(client, db_session):
    """POST /uitslagen/{id}/verwijderen verwijdert een bestaande uitslag."""
    from app.main import app
    from app.models import Uitslag

    wl = make_member(db_session, role="wedstrijdleider", lidnummer="UC49")
    season = make_season(db_session)
    evening = make_past_evening(db_session, season.id)
    uitslag = Uitslag(evening_id=evening.id, bestandsnaam="u.pdf", inhoud=b"data",
                      aangemaakt_door_id=wl.id)
    db_session.add(uitslag)
    db_session.commit()
    _set_auth(app, wl=wl)

    response = await client.post(
        f"/uitslagen/{evening.id}/verwijderen", data={"_csrf_token": "x"}
    )
    assert response.status_code == 302

    check = db_session.query(Uitslag).filter(Uitslag.evening_id == evening.id).first()
    assert check is None


async def test_uc50_uitslag_weergave_404(client, db_session):
    """GET /uitslagen/99999/weergave geeft 404 voor onbekend evenement."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC50")
    _set_auth(app, member=lid)

    response = await client.get("/uitslagen/99999/weergave")
    assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# RANKINGS
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc51_ranking_lege_staat(client, db_session):
    """GET /ranking zonder uitslagen geeft 200 met lege ranglijst."""
    lid = make_member(db_session, lidnummer="UC51")

    with patch("app.routes.rankings.get_current_user", return_value=lid):
        response = await client.get("/ranking")
    assert response.status_code == 200


async def test_uc52_mijn_overzicht(client, db_session):
    """GET /ranking/mijn-overzicht geeft 200 voor ingelogd lid."""
    lid = make_member(db_session, lidnummer="UC52")

    with patch("app.routes.rankings.get_current_user", return_value=lid):
        response = await client.get("/ranking/mijn-overzicht")
    assert response.status_code == 200


async def test_uc53_ranking_zonder_login(client):
    """GET /ranking zonder sessie redirect naar /login."""
    response = await client.get("/ranking")
    assert response.status_code == 302
    assert "/login" in response.headers["location"]


async def test_uc54_gdpr_download(client, db_session):
    """GET /gdpr/download geeft een JSON-bestand met persoonsgegevens."""
    from app.main import app
    lid = make_member(db_session, lidnummer="UC54")
    _set_auth(app, member=lid)

    response = await client.get("/gdpr/download")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — AVONDEN & SEIZOENEN
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc55_admin_avonden_overzicht(client, db_session):
    """GET /beheer/avonden geeft 200 voor admin."""
    from app.main import app
    admin = make_member(db_session, role="admin", lidnummer="UC55")
    _set_auth(app, admin=admin)

    response = await client.get("/beheer/avonden")
    assert response.status_code == 200


async def test_uc56_admin_seizoen_aanmaken(client, db_session):
    """POST /beheer/avonden/seizoen maakt een seizoen aan in de database."""
    from app.main import app
    from app.models import Season

    admin = make_member(db_session, role="admin", lidnummer="UC56")
    _set_auth(app, admin=admin)

    response = await client.post(
        "/beheer/avonden/seizoen",
        data={"naam": "2026-2027", "start_datum": "2026-09-01",
              "eind_datum": "2027-06-30", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    season = db_session.query(Season).filter(Season.naam == "2026-2027").first()
    assert season is not None


async def test_uc57_admin_avond_aanmaken(client, db_session):
    """POST /beheer/avonden maakt een nieuw evenement aan (met club+seizoen als context)."""
    from app.main import app
    from app.models import ClubEvening, Season

    admin = make_member(db_session, role="admin", lidnummer="UC57")
    club = make_club(db_session, naam="Club UC57")
    avond_datum = date.today() + timedelta(days=14)
    season = Season(
        naam="UC57 Seizoen", club_id=club.id,
        start_datum=date.today(), eind_datum=date.today() + timedelta(days=365),
        actief=True,
    )
    db_session.add(season)
    db_session.commit()
    db_session.refresh(season)
    _set_auth(app, admin=admin)

    response = await client.post(
        "/beheer/avonden",
        data={"naam": "Testkampioenschappen",
              "datum": str(avond_datum),
              "type": "speciaal", "deelnemers_type": "paren",
              "_csrf_token": "x"},
    )
    assert response.status_code == 302

    evening = db_session.query(ClubEvening).filter(
        ClubEvening.naam == "Testkampioenschappen"
    ).first()
    assert evening is not None
    assert evening.season_id == season.id


async def test_uc58_admin_avond_verwijderen(client, db_session):
    """POST /beheer/avonden/{id}/verwijder verwijdert het evenement uit de database."""
    from app.main import app
    from app.models import ClubEvening

    admin = make_member(db_session, role="admin", lidnummer="UC58")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    _set_auth(app, admin=admin)

    response = await client.post(
        f"/beheer/avonden/{evening.id}/verwijder", data={"_csrf_token": "x"}
    )
    assert response.status_code == 302

    check = db_session.query(ClubEvening).filter(ClubEvening.id == evening.id).first()
    assert check is None


async def test_uc59_admin_aanmeldingen_per_avond(client, db_session):
    """GET /beheer/aanmeldingen/{id} toont aangemelde leden voor een avond."""
    from app.main import app

    admin = make_member(db_session, role="admin", lidnummer="UC59-A")
    lid = make_member(db_session, voornaam="Daan", achternaam="Dam", lidnummer="UC59-L")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)
    make_registration(db_session, lid.id, evening.id)
    _set_auth(app, admin=admin)

    response = await client.get(f"/beheer/aanmeldingen/{evening.id}")
    assert response.status_code == 200
    assert "Daan" in response.text


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — AANVRAGEN & UITNODIGINGEN
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc60_admin_aanvragen_overzicht(client, db_session):
    """GET /beheer/aanvragen geeft 200 voor admin."""
    from app.main import app
    admin = make_member(db_session, role="admin", lidnummer="UC60")
    _set_auth(app, admin=admin)

    response = await client.get("/beheer/aanvragen")
    assert response.status_code == 200


async def test_uc61_admin_aanvraag_goedkeuren(client, db_session):
    """POST /beheer/aanvragen/{id}/goedkeuren keurt de aanvraag goed."""
    from app.main import app
    from app.models import AccountRequest, AccountRequestStatus

    admin = make_member(db_session, role="admin", lidnummer="UC61-A")
    aanvraag = AccountRequest(
        voornaam="Niek", achternaam="Nieuw",
        email="niek@test.nl", lidnummer="UC61-LID",
        status=AccountRequestStatus.wachtend,
    )
    db_session.add(aanvraag)
    db_session.commit()
    db_session.refresh(aanvraag)
    _set_auth(app, admin=admin)

    response = await client.post(
        f"/beheer/aanvragen/{aanvraag.id}/goedkeuren",
        data={"role": "lid", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    db_session.refresh(aanvraag)
    assert aanvraag.status == AccountRequestStatus.goedgekeurd


async def test_uc62_admin_aanvraag_afwijzen(client, db_session):
    """POST /beheer/aanvragen/{id}/afwijzen wijst de aanvraag af."""
    from app.main import app
    from app.models import AccountRequest, AccountRequestStatus

    admin = make_member(db_session, role="admin", lidnummer="UC62-A")
    aanvraag = AccountRequest(
        voornaam="Afg", achternaam="Wezen",
        email="afg@test.nl", lidnummer="UC62-LID",
        status=AccountRequestStatus.wachtend,
    )
    db_session.add(aanvraag)
    db_session.commit()
    db_session.refresh(aanvraag)
    _set_auth(app, admin=admin)

    response = await client.post(
        f"/beheer/aanvragen/{aanvraag.id}/afwijzen", data={"_csrf_token": "x"}
    )
    assert response.status_code == 302

    db_session.refresh(aanvraag)
    assert aanvraag.status == AccountRequestStatus.afgewezen


async def test_uc63_admin_uitnodiging_aanmaken(client, db_session):
    """POST /beheer/uitnodigingen maakt een uitnodiging met token aan."""
    from app.main import app
    from app.models import Invitation

    admin = make_member(db_session, role="admin", lidnummer="UC63")
    _set_auth(app, admin=admin)

    response = await client.post(
        "/beheer/uitnodigingen",
        data={"email": "uitgenodigd@test.nl", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    inv = db_session.query(Invitation).filter(
        Invitation.email == "uitgenodigd@test.nl"
    ).first()
    assert inv is not None
    assert inv.token is not None and len(inv.token) > 10


async def test_uc64_admin_uitnodigingen_overzicht(client, db_session):
    """GET /beheer/uitnodigingen geeft 200 voor admin."""
    from app.main import app
    admin = make_member(db_session, role="admin", lidnummer="UC64")
    _set_auth(app, admin=admin)

    response = await client.get("/beheer/uitnodigingen")
    assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — CLUBS & ROLLEN
# ══════════════════════════════════════════════════════════════════════════════

async def test_uc65_admin_club_aanmaken(client, db_session):
    """POST /beheer/clubs maakt een nieuwe club aan in de database."""
    from app.main import app
    from app.models import Club

    admin = make_member(db_session, role="admin", lidnummer="UC65")
    _set_auth(app, admin=admin)

    response = await client.post(
        "/beheer/clubs",
        data={"naam": "BC Teststad", "stad": "Teststad", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    club = db_session.query(Club).filter(Club.naam == "BC Teststad").first()
    assert club is not None
    assert club.stad == "Teststad"


async def test_uc66_admin_rollen_overzicht(client, db_session):
    """GET /beheer/rollen geeft 200 voor admin."""
    from app.main import app
    admin = make_member(db_session, role="admin", lidnummer="UC66")
    _set_auth(app, admin=admin)

    response = await client.get("/beheer/rollen")
    assert response.status_code == 200


async def test_uc67_admin_rol_toewijzen(client, db_session):
    """POST /beheer/rollen koppelt een e-mailadres aan een rol."""
    from app.main import app
    from app.models import EmailRoleAssignment

    admin = make_member(db_session, role="admin", lidnummer="UC67")
    _set_auth(app, admin=admin)

    response = await client.post(
        "/beheer/rollen",
        data={"email": "wl@test.nl", "role": "wedstrijdleider", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    toewijzing = db_session.query(EmailRoleAssignment).filter(
        EmailRoleAssignment.email == "wl@test.nl"
    ).first()
    assert toewijzing is not None
    assert toewijzing.role == "wedstrijdleider"


async def test_uc68_admin_lid_toevoegen_aan_club(client, db_session):
    """POST /beheer/clubs/{id}/leden/toevoegen voegt een bestaand lid toe aan een club."""
    from app.main import app
    from app.models import MemberClub

    admin = make_member(db_session, role="admin", lidnummer="UC68-A")
    lid = make_member(db_session, voornaam="Nieuw", achternaam="Lid", lidnummer="UC68-L")
    club = make_club(db_session, naam="Club UC68")
    _set_auth(app, admin=admin)

    response = await client.post(
        f"/beheer/clubs/{club.id}/leden/toevoegen",
        data={"member_id": str(lid.id), "role": "lid", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == lid.id, MemberClub.club_id == club.id
    ).first()
    assert mc is not None and mc.role == "lid"


async def test_uc69_admin_clubrol_wijzigen(client, db_session):
    """POST /beheer/clubs/{id}/leden/{mid}/rol → rol wordt bijgewerkt en global role gesynchroniseerd."""
    from app.main import app
    from app.models import MemberClub

    admin = make_member(db_session, role="admin", lidnummer="UC69-A")
    lid = make_member(db_session, voornaam="Bestaand", achternaam="Lid", lidnummer="UC69-L")
    club = make_club(db_session, naam="Club UC69")
    make_member_club(db_session, lid.id, club.id, role="lid")
    _set_auth(app, admin=admin)

    response = await client.post(
        f"/beheer/clubs/{club.id}/leden/{lid.id}/rol",
        data={"role": "wedstrijdleider", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == lid.id, MemberClub.club_id == club.id
    ).first()
    assert mc.role == "wedstrijdleider"

    db_session.refresh(lid)
    assert lid.role == "wedstrijdleider"


async def test_uc70_admin_lid_verwijderen_uit_club_synct_global_rol(client, db_session):
    """Verwijderen uit WL-club terwijl lid ook gewone-lid-club heeft → global role → 'lid'."""
    from app.main import app
    from app.models import MemberClub

    admin = make_member(db_session, role="admin", lidnummer="UC70-A")
    lid = make_member(db_session, voornaam="Vertrek", achternaam="Lid",
                      role="wedstrijdleider", lidnummer="UC70-L")
    club_wl = make_club(db_session, naam="Club UC70-WL")
    club_lid = make_club(db_session, naam="Club UC70-Lid")
    make_member_club(db_session, lid.id, club_wl.id, role="wedstrijdleider")
    make_member_club(db_session, lid.id, club_lid.id, role="lid")
    _set_auth(app, admin=admin)

    response = await client.post(
        f"/beheer/clubs/{club_wl.id}/leden/{lid.id}/verwijder",
        data={"_csrf_token": "x"},
    )
    assert response.status_code == 302

    mc = db_session.query(MemberClub).filter(
        MemberClub.member_id == lid.id, MemberClub.club_id == club_wl.id
    ).first()
    assert mc is None

    db_session.refresh(lid)
    assert lid.role == "lid"
