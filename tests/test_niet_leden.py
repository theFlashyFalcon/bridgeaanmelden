"""
Tests voor het niet-ledenbeleid (/beheer/instellingen): de gastaanmeldlink
(/gast/{token}), de gast-zelfaanmelding op /aanmelden/{event_id}, het
niet-lid-partnerbeleid voor ingelogde leden, en de WL-goedkeuringsflow in
/beheer/af-aanmeldingen.
"""
from datetime import date, timedelta

from tests.conftest import make_member, make_season


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_club(db_session, naam="BC Test", niet_lid_beleid=None, niet_lid_paar_beleid=None, gast_token=None):
    from app.models import Club
    club = Club(naam=naam, niet_lid_beleid=niet_lid_beleid,
                niet_lid_paar_beleid=niet_lid_paar_beleid, gast_token=gast_token)
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


def make_lid_entry(db_session, voornaam, achternaam, club_id):
    from app.models import Lid
    lid = Lid(voornaam=voornaam, achternaam=achternaam, club_id=club_id)
    db_session.add(lid)
    db_session.commit()
    return lid


def _no_csrf(app):
    from app.csrf import require_csrf
    app.dependency_overrides[require_csrf] = lambda: None


def _set_auth(app, member=None, wl=None):
    from app.auth import get_current_user, require_auth, require_wedstrijdleider
    _no_csrf(app)
    if wl is not None:
        app.dependency_overrides[require_wedstrijdleider] = lambda: wl
        app.dependency_overrides[require_auth] = lambda: wl
        app.dependency_overrides[get_current_user] = lambda: wl
    if member is not None:
        app.dependency_overrides[require_auth] = lambda: member
        app.dependency_overrides[get_current_user] = lambda: member


def _wl_met_club(db_session, **club_kwargs):
    club = make_club(db_session, **club_kwargs)
    wl = make_member(db_session, voornaam="Wies", achternaam="Leider",
                      lidnummer="NLWL001", role="wedstrijdleider")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    return club, wl


# ── Helpers-module (zonder HTTP) ──────────────────────────────────────────────

def test_niet_lid_beleid_standaard_toegestaan():
    from app.models import Club
    from app.niet_leden import niet_lid_beleid

    assert niet_lid_beleid(Club(naam="X")) == "toegestaan"
    assert niet_lid_beleid(None) == "toegestaan"
    assert niet_lid_beleid(Club(naam="X", niet_lid_beleid="onzin")) == "toegestaan"


def test_niet_lid_paar_beleid_standaard_toegestaan():
    from app.models import Club
    from app.niet_leden import niet_lid_paar_beleid

    assert niet_lid_paar_beleid(Club(naam="X")) == "toegestaan"
    assert niet_lid_paar_beleid(Club(naam="X", niet_lid_paar_beleid="geblokkeerd")) == "toegestaan"


def test_niet_lid_beleid_bekende_waarde():
    from app.models import Club
    from app.niet_leden import niet_lid_beleid, niet_lid_paar_beleid

    assert niet_lid_beleid(Club(naam="X", niet_lid_beleid="goedkeuring")) == "goedkeuring"
    assert niet_lid_paar_beleid(Club(naam="X", niet_lid_paar_beleid="verwijderd")) == "verwijderd"


def test_is_bekend_lid(db_session):
    from app.niet_leden import is_bekend_lid

    club = make_club(db_session)
    make_lid_entry(db_session, "Jan", "Jansen", club.id)
    assert is_bekend_lid(db_session, club.id, "jan", "JANSEN") is True
    assert is_bekend_lid(db_session, club.id, "Piet", "Pietersen") is False
    assert is_bekend_lid(db_session, None, "Jan", "Jansen") is False
    assert is_bekend_lid(db_session, club.id, "", "") is False


# ── Instellingenscherm ────────────────────────────────────────────────────────

async def test_instellingen_toont_niet_lid_opties_en_gastlink(client, db_session):
    from app.main import app

    club, wl = _wl_met_club(db_session)
    _set_auth(app, wl=wl)
    response = await client.get("/beheer/instellingen")
    assert response.status_code == 200
    assert 'name="niet_lid_beleid" value="geblokkeerd"' in response.text
    assert 'name="niet_lid_beleid" value="toegestaan"' in response.text
    assert 'name="niet_lid_paar_beleid" value="verwijderd"' in response.text
    assert "/gast/" in response.text


async def test_instellingen_slaat_niet_lid_beleid_op(client, db_session):
    from app.main import app

    club, wl = _wl_met_club(db_session)
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/instellingen", data={
        "type_clubavond": "1",
        "ranking_spanning": "1",
        "label_paren": "1",
        "niet_lid_beleid": "goedkeuring",
        "niet_lid_paar_beleid": "verwijderd",
    })
    assert response.status_code == 302
    db_session.refresh(club)
    assert club.niet_lid_beleid == "goedkeuring"
    assert club.niet_lid_paar_beleid == "verwijderd"


async def test_instellingen_negeert_ongeldige_niet_lid_waarde(client, db_session):
    from app.main import app

    club, wl = _wl_met_club(db_session, niet_lid_beleid="toegestaan")
    _set_auth(app, wl=wl)
    await client.post("/beheer/instellingen", data={
        "type_clubavond": "1", "ranking_spanning": "1", "label_paren": "1",
        "niet_lid_beleid": "onzin",
    })
    db_session.refresh(club)
    assert club.niet_lid_beleid == "toegestaan"


async def test_instellingen_gast_token_lazy_en_idempotent(client, db_session):
    from app.main import app

    club, wl = _wl_met_club(db_session)
    assert club.gast_token is None
    _set_auth(app, wl=wl)
    await client.get("/beheer/instellingen")
    db_session.refresh(club)
    token1 = club.gast_token
    assert token1
    await client.get("/beheer/instellingen")
    db_session.refresh(club)
    assert club.gast_token == token1


# ── Gastflow ──────────────────────────────────────────────────────────────────

async def test_gast_link_onbekend_token_redirect_naar_home(client, db_session):
    response = await client.get("/gast/onzin-token")
    assert response.status_code == 302
    assert response.headers["location"] == "/"


async def test_gast_link_scoped_agenda(client, db_session):
    club = make_club(db_session, gast_token="tok-scope")
    andere_club = make_club(db_session, naam="Andere club")
    season = make_season(db_session)
    ev_eigen = make_evening(db_session, season.id, club_id=club.id)
    ev_ander = make_evening(db_session, season.id, club_id=andere_club.id)

    r = await client.get("/gast/tok-scope")
    assert r.status_code == 302
    assert r.headers["location"] == "/?gast=1"

    response = await client.get("/")
    assert response.status_code == 200
    assert "als gast" in response.text
    assert f'data-club="{ev_eigen.club_id}"' in response.text
    assert f'data-club="{ev_ander.club_id}"' not in response.text


async def test_aanmelden_zonder_login_en_zonder_gastlink_vereist_login(client, db_session):
    club = make_club(db_session)
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="individueel")

    response = await client.get(f"/aanmelden/{ev.id}")
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login")


async def test_gast_aanmelden_individueel_toegestaan(client, db_session):
    from app.main import app
    from app.models import Member, Registration

    _no_csrf(app)
    club = make_club(db_session, niet_lid_beleid="toegestaan", gast_token="tok-ok")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="individueel")

    await client.get("/gast/tok-ok")
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "eigen_voornaam": "Gast", "eigen_achternaam": "Speler",
    })
    assert response.status_code == 302
    assert "bevestigd=1" in response.headers["location"]

    reg = db_session.query(Registration).join(Member, Registration.person1_id == Member.id).filter(
        Member.voornaam == "Gast", Member.achternaam == "Speler",
    ).first()
    assert reg is not None
    assert reg.status == "aangemeld"
    assert reg.niet_lid_goedkeuring_vereist is False


async def test_gast_aanmelden_zonder_eigen_naam_geweigerd(client, db_session):
    from app.main import app
    from app.models import Registration

    _no_csrf(app)
    club = make_club(db_session, niet_lid_beleid="toegestaan", gast_token="tok-naam")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="individueel")

    await client.get("/gast/tok-naam")
    response = await client.post(f"/aanmelden/{ev.id}", data={})
    assert response.status_code == 302
    assert "fout=eigen_naam" in response.headers["location"]
    assert db_session.query(Registration).count() == 0


async def test_gast_aanmelden_geblokkeerd(client, db_session):
    from app.main import app
    from app.models import Member, Registration

    _no_csrf(app)
    club = make_club(db_session, niet_lid_beleid="geblokkeerd", gast_token="tok-blocked")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="individueel")

    await client.get("/gast/tok-blocked")
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "eigen_voornaam": "Gast", "eigen_achternaam": "Speler",
    })
    assert response.status_code == 302
    assert "fout=niet_lid" in response.headers["location"]
    assert db_session.query(Registration).count() == 0
    assert db_session.query(Member).count() == 0


async def test_gast_aanmelden_goedkeuring_verschijnt_pas_na_goedkeuring(client, db_session):
    from app.main import app
    from app.routes.admin.aanmeldingen import _af_aanmeldingen_data

    _no_csrf(app)
    club = make_club(db_session, niet_lid_beleid="goedkeuring", gast_token="tok-goedkeuring")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="individueel")

    await client.get("/gast/tok-goedkeuring")
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "eigen_voornaam": "Gast", "eigen_achternaam": "Speler",
    })
    assert response.status_code == 302
    assert "wacht_goedkeuring=1" in response.headers["location"]

    data = _af_aanmeldingen_data(db_session, ev.id)
    assert len(data["niet_lid_wachtend"]) == 1
    assert len(data["volledig_aangemeld"]) == 0

    wl = make_member(db_session, lidnummer="WLGOED", role="wedstrijdleider")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    _set_auth(app, wl=wl)

    reg_id = data["niet_lid_wachtend"][0].id
    approve = await client.post(f"/beheer/niet-lid/{reg_id}/goedkeuren")
    assert approve.status_code == 302
    assert "niet_lid_goedgekeurd=1" in approve.headers["location"]

    data2 = _af_aanmeldingen_data(db_session, ev.id)
    assert len(data2["niet_lid_wachtend"]) == 0
    assert len(data2["volledig_aangemeld"]) == 1


async def test_gast_aanmelden_afwijzen_verwijdert_registratie(client, db_session):
    from app.main import app
    from app.models import Registration
    from app.routes.admin.aanmeldingen import _af_aanmeldingen_data

    _no_csrf(app)
    club = make_club(db_session, niet_lid_beleid="goedkeuring", gast_token="tok-afwijzen")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="individueel")

    await client.get("/gast/tok-afwijzen")
    await client.post(f"/aanmelden/{ev.id}", data={
        "eigen_voornaam": "Gast", "eigen_achternaam": "Speler",
    })
    data = _af_aanmeldingen_data(db_session, ev.id)
    reg_id = data["niet_lid_wachtend"][0].id

    wl = make_member(db_session, lidnummer="WLAFW", role="wedstrijdleider")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    _set_auth(app, wl=wl)
    response = await client.post(f"/beheer/niet-lid/{reg_id}/afwijzen")
    assert response.status_code == 302
    assert "niet_lid_afgewezen=1" in response.headers["location"]
    assert db_session.query(Registration).filter(Registration.id == reg_id).first() is None


# ── Niet-lid-partnerbeleid (ingelogd lid) ─────────────────────────────────────

async def test_partner_toegestaan_standaard_ongewijzigd(client, db_session):
    """Standaard (geen instelling) mag een lid een onbekende partner opgeven, zoals nu."""
    from app.main import app
    from app.models import Registration

    club = make_club(db_session)
    lid = make_member(db_session, lidnummer="PARTNER1")
    make_member_club(db_session, lid.id, club.id, role="lid")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="paren")

    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "partner_voornaam": "Onbekende", "partner_achternaam": "Partner",
    })
    assert response.status_code == 302
    assert "bevestigd=1" in response.headers["location"]
    reg = db_session.query(Registration).first()
    assert reg.partner_naam == "Onbekende Partner"
    assert reg.niet_lid_goedkeuring_vereist is False


async def test_partner_verwijderd_blokkeert_onbekende_partner(client, db_session):
    from app.main import app
    from app.models import Registration

    club = make_club(db_session, niet_lid_paar_beleid="verwijderd")
    lid = make_member(db_session, lidnummer="PARTNER2")
    make_member_club(db_session, lid.id, club.id, role="lid")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="paren")

    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "partner_voornaam": "Onbekende", "partner_achternaam": "Partner",
    })
    assert response.status_code == 302
    assert "fout=niet_lid_partner" in response.headers["location"]
    assert db_session.query(Registration).count() == 0


async def test_partner_verwijderd_staat_bekend_lid_toe(client, db_session):
    from app.main import app
    from app.models import Registration

    club = make_club(db_session, niet_lid_paar_beleid="verwijderd")
    lid = make_member(db_session, lidnummer="PARTNER3")
    make_member_club(db_session, lid.id, club.id, role="lid")
    make_lid_entry(db_session, "Bekende", "Partner", club.id)
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="paren")

    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "partner_voornaam": "Bekende", "partner_achternaam": "Partner",
    })
    assert response.status_code == 302
    assert "bevestigd=1" in response.headers["location"]
    reg = db_session.query(Registration).first()
    assert reg is not None


async def test_partner_goedkeuring_wacht_tot_wl_goedkeurt(client, db_session):
    from app.main import app
    from app.routes.admin.aanmeldingen import _af_aanmeldingen_data

    club = make_club(db_session, niet_lid_paar_beleid="goedkeuring")
    lid = make_member(db_session, lidnummer="PARTNER4")
    make_member_club(db_session, lid.id, club.id, role="lid")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="paren")

    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "partner_voornaam": "Onbekende", "partner_achternaam": "Partner",
    })
    assert response.status_code == 302
    assert "wacht_goedkeuring=1" in response.headers["location"]

    data = _af_aanmeldingen_data(db_session, ev.id)
    assert len(data["niet_lid_wachtend"]) == 1
    assert len(data["volledig_aangemeld"]) == 0


async def test_partner_gemeld_telt_direct_mee(client, db_session):
    from app.main import app
    from app.routes.admin.aanmeldingen import _af_aanmeldingen_data

    club = make_club(db_session, niet_lid_paar_beleid="gemeld")
    lid = make_member(db_session, lidnummer="PARTNER5")
    make_member_club(db_session, lid.id, club.id, role="lid")
    season = make_season(db_session)
    ev = make_evening(db_session, season.id, club_id=club.id, deelnemers_type="paren")

    _set_auth(app, member=lid)
    response = await client.post(f"/aanmelden/{ev.id}", data={
        "partner_voornaam": "Onbekende", "partner_achternaam": "Partner",
    })
    assert response.status_code == 302
    assert "bevestigd=1" in response.headers["location"]

    data = _af_aanmeldingen_data(db_session, ev.id)
    assert len(data["niet_lid_wachtend"]) == 0
    assert len(data["volledig_aangemeld"]) == 1
