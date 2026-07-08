"""
Tests voor de clubinstellingen van de wedstrijdleider (/beheer/instellingen):
welke evenementtypes de club gebruikt (agenda-filters, aanmaakknoppen) en
welke rankingweergaves beschikbaar zijn.
"""
from tests.conftest import make_member, make_season


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_club(db_session, naam="BC Test", stad=None, evenement_types=None,
              ranking_weergaves=None, labels=None):
    from app.models import Club
    club = Club(naam=naam, stad=stad, evenement_types=evenement_types,
                ranking_weergaves=ranking_weergaves, labels=labels)
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


def _wl_met_club(db_session, evenement_types=None, ranking_weergaves=None, labels=None):
    club = make_club(db_session, evenement_types=evenement_types,
                     ranking_weergaves=ranking_weergaves, labels=labels)
    wl = make_member(db_session, voornaam="Wies", achternaam="Leider",
                     lidnummer="WL001", role="wedstrijdleider")
    make_member_club(db_session, wl.id, club.id, role="wedstrijdleider")
    return club, wl


# ── Helpers-module (zonder HTTP) ──────────────────────────────────────────────

def test_enabled_event_types_standaard_alles():
    """Zonder instelling (NULL) zijn alle types beschikbaar."""
    from app.club_settings import EVENT_TYPE_KEYS, enabled_event_types
    from app.models import Club

    club = Club(naam="X")
    assert enabled_event_types(club) == EVENT_TYPE_KEYS
    assert enabled_event_types(None) == EVENT_TYPE_KEYS


def test_enabled_event_types_selectie_en_volgorde():
    """Opgeslagen selectie wordt teruggegeven in canonieke volgorde; onbekende sleutels genegeerd."""
    from app.club_settings import enabled_event_types
    from app.models import Club

    club = Club(naam="X", evenement_types="speciaal,clubavond,onzin")
    assert enabled_event_types(club) == ["clubavond", "speciaal"]


def test_enabled_rankings_selectie():
    from app.club_settings import RANKING_KEYS, enabled_rankings
    from app.models import Club

    assert enabled_rankings(Club(naam="X")) == RANKING_KEYS
    club = Club(naam="X", ranking_weergaves="vorm,spanning")
    assert enabled_rankings(club) == ["spanning", "vorm"]


def test_merged_event_types_vereniging_van_clubs():
    """Lid van meerdere clubs ziet de vereniging van de ingestelde types."""
    from app.club_settings import merged_event_types
    from app.models import Club

    c1 = Club(naam="A", evenement_types="clubavond")
    c2 = Club(naam="B", evenement_types="speciaal")
    assert merged_event_types([c1, c2]) == ["clubavond", "speciaal"]
    assert merged_event_types([]) == ["clubavond", "avondeten", "training", "speciaal"]


# ── Instellingenscherm ────────────────────────────────────────────────────────

async def test_instellingen_vereist_wedstrijdleider(client, db_session):
    """Gewoon lid krijgt 403 op /beheer/instellingen."""
    from app.main import app

    lid = make_member(db_session, lidnummer="LID100", role="lid")
    _set_auth(app, member=lid)
    response = await client.get("/beheer/instellingen")
    assert response.status_code == 403


async def test_instellingen_pagina_toont_keuzes(client, db_session):
    """WL ziet checkboxes voor evenementtypes en rankings."""
    from app.main import app

    club, wl = _wl_met_club(db_session)
    _set_auth(app, wl=wl)
    response = await client.get("/beheer/instellingen")
    assert response.status_code == 200
    assert 'name="type_clubavond"' in response.text
    assert 'name="type_speciaal"' in response.text
    assert 'name="ranking_spanning"' in response.text
    assert 'name="ranking_vorm"' in response.text
    assert 'name="label_paren"' in response.text
    assert 'name="label_individuele_drive"' in response.text


async def test_instellingen_opslaan(client, db_session):
    """POST slaat de selectie op de club op."""
    from app.main import app

    club, wl = _wl_met_club(db_session)
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/instellingen", data={
        "type_clubavond": "1",
        "type_speciaal": "1",
        "ranking_spanning": "1",
        "ranking_imp_totaal": "1",
        "label_paren": "1",
        "label_viertallen": "1",
    })
    assert response.status_code == 302
    assert "opgeslagen=1" in response.headers["location"]

    db_session.refresh(club)
    assert club.evenement_types == "clubavond,speciaal"
    assert club.ranking_weergaves == "spanning,imp_totaal"
    assert club.labels == "viertallen,paren"


async def test_instellingen_minimaal_een_type(client, db_session):
    """Zonder gekozen evenementtype wordt niets opgeslagen (foutmelding)."""
    from app.main import app

    club, wl = _wl_met_club(db_session)
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/instellingen", data={
        "ranking_spanning": "1",
    })
    assert response.status_code == 302
    assert "fout=geen_types" in response.headers["location"]
    db_session.refresh(club)
    assert club.evenement_types is None


async def test_instellingen_minimaal_een_ranking(client, db_session):
    """Zonder gekozen ranking wordt niets opgeslagen (foutmelding)."""
    from app.main import app

    club, wl = _wl_met_club(db_session)
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/instellingen", data={
        "type_clubavond": "1",
    })
    assert response.status_code == 302
    assert "fout=geen_rankings" in response.headers["location"]
    db_session.refresh(club)
    assert club.ranking_weergaves is None


async def test_instellingen_minimaal_een_label(client, db_session):
    """Zonder gekozen label wordt niets opgeslagen (foutmelding)."""
    from app.main import app

    club, wl = _wl_met_club(db_session)
    _set_auth(app, wl=wl)
    response = await client.post("/beheer/instellingen", data={
        "type_clubavond": "1",
        "ranking_spanning": "1",
    })
    assert response.status_code == 302
    assert "fout=geen_labels" in response.headers["location"]
    db_session.refresh(club)
    assert club.labels is None


# ── Doorwerking in het hoofdscherm ────────────────────────────────────────────

async def test_homepage_filters_volgen_clubinstellingen(client, db_session):
    """Uitgeschakelde types verschijnen niet als filter of toon-soorten-checkbox."""
    from app.auth import get_current_user
    from app.main import app

    club = make_club(db_session, evenement_types="clubavond,speciaal")
    lid = make_member(db_session, lidnummer="LID200", role="lid")
    make_member_club(db_session, lid.id, club.id, role="lid")
    make_season(db_session)

    app.dependency_overrides[get_current_user] = lambda: lid
    response = await client.get("/")
    assert response.status_code == 200
    assert 'data-value="clubavond"' in response.text
    assert 'data-value="speciaal"' in response.text
    assert 'data-value="training"' not in response.text
    assert 'data-value="avondeten"' not in response.text
    assert 'name="toon_clubavond"' in response.text
    assert 'name="toon_training"' not in response.text


async def test_homepage_zonder_instelling_toont_alles(client, db_session):
    """Club zonder instelling (NULL) houdt alle vier de filters."""
    from app.auth import get_current_user
    from app.main import app

    club = make_club(db_session)
    lid = make_member(db_session, lidnummer="LID201", role="lid")
    make_member_club(db_session, lid.id, club.id, role="lid")
    make_season(db_session)

    app.dependency_overrides[get_current_user] = lambda: lid
    response = await client.get("/")
    assert response.status_code == 200
    for t in ("clubavond", "avondeten", "training", "speciaal"):
        assert f'data-value="{t}"' in response.text


# ── Doorwerking in het avondenbeheer ──────────────────────────────────────────

async def test_avonden_aanmaakknoppen_volgen_instellingen(client, db_session):
    """Aanmaakmenu toont alleen de ingestelde evenementtypes."""
    from app.main import app

    club, wl = _wl_met_club(db_session, evenement_types="clubavond,speciaal")
    _set_auth(app, wl=wl)
    response = await client.get("/beheer/avonden")
    assert response.status_code == 200
    assert "openForm('clubavond')" in response.text
    assert "openForm('speciaal')" in response.text
    assert "openForm('jeugdtraining')" not in response.text
    assert "openForm('eten')" not in response.text
    # Seizoen aanmaken blijft altijd mogelijk
    assert "openForm('seizoen')" in response.text


# ── Doorwerking in de rankingweergaves ────────────────────────────────────────

def test_beschikbare_weergaves_volgt_seizoensclub(db_session):
    """Seizoen met club → instellingen van die club zijn leidend."""
    from app.routes.rankings import _beschikbare_weergaves
    from app.models import Season
    from datetime import date

    club = make_club(db_session, ranking_weergaves="spanning,vorm")
    season = Season(naam="S", start_datum=date(2025, 9, 1),
                    eind_datum=date(2026, 6, 30), actief=True, club_id=club.id)
    db_session.add(season)
    db_session.commit()

    assert _beschikbare_weergaves(db_session, season, []) == ["spanning", "vorm"]


def test_beschikbare_weergaves_legacy_seizoen_gebruikt_ledenclubs(db_session):
    """Seizoen zonder club → vereniging van de clubs van het lid."""
    from app.routes.rankings import _beschikbare_weergaves

    c1 = make_club(db_session, naam="A", ranking_weergaves="spanning")
    c2 = make_club(db_session, naam="B", ranking_weergaves="imp_totaal")
    season = make_season(db_session)  # club_id None

    assert _beschikbare_weergaves(db_session, season, [c1.id, c2.id]) == ["spanning", "imp_totaal"]


def test_beschikbare_weergaves_zonder_clubs_alles(db_session):
    """Geen clubs bekend → alle weergaves beschikbaar."""
    from app.club_settings import RANKING_KEYS
    from app.routes.rankings import _beschikbare_weergaves

    season = make_season(db_session)
    assert _beschikbare_weergaves(db_session, season, []) == RANKING_KEYS


# ── Labels ────────────────────────────────────────────────────────────────────

def test_evening_label_key_afleiding():
    """Labelsleutel volgt type (training/avondeten) en anders de deelnemersvorm."""
    from app.club_settings import evening_label_key

    assert evening_label_key("jeugdtraining", "individueel") == "training"
    assert evening_label_key("training", None) == "training"
    assert evening_label_key("eten voor jeugdtraining", None) == "avondeten"
    assert evening_label_key("clubavond", "paren") == "paren"
    assert evening_label_key("regulier", None) == "paren"
    assert evening_label_key("speciaal", "viertallen") == "viertallen"
    assert evening_label_key("clubavond", "individueel") == "individuele_drive"


def test_enabled_labels_standaard_en_selectie():
    from app.club_settings import LABEL_KEYS, enabled_labels
    from app.models import Club

    assert enabled_labels(Club(naam="X")) == LABEL_KEYS
    assert enabled_labels(None) == LABEL_KEYS
    club = Club(naam="X", labels="paren,training")
    assert enabled_labels(club) == ["training", "paren"]


def test_evening_label_respecteert_clubinstelling():
    """Uitgeschakeld label → None; ingeschakeld → naam + css-klasse."""
    from app.club_settings import evening_label
    from app.models import Club, ClubEvening

    club = Club(naam="X", labels="training,viertallen")
    ev = ClubEvening(type="clubavond", deelnemers_type="viertallen")
    ev.club = club
    lbl = evening_label(ev)
    assert lbl == {"key": "viertallen", "naam": "Viertallen", "css": "viertallen"}

    ev2 = ClubEvening(type="clubavond", deelnemers_type="individueel")
    ev2.club = club
    assert evening_label(ev2) is None

    ev3 = ClubEvening(type="clubavond", deelnemers_type="individueel")
    ev3.club = None  # legacy: geen club → alle labels
    lbl3 = evening_label(ev3)
    assert lbl3["naam"] == "Individuele drive"
    assert lbl3["css"] == "individuele-drive"


async def test_homepage_badge_volgt_labelinstelling(client, db_session):
    """Evenementkaart toont het clublabel; uitgeschakelde labels verdwijnen."""
    from datetime import date, timedelta

    from app.auth import get_current_user
    from app.main import app
    from app.models import ClubEvening

    club = make_club(db_session, labels="paren,training")
    lid = make_member(db_session, lidnummer="LID300", role="lid")
    make_member_club(db_session, lid.id, club.id, role="lid")
    season = make_season(db_session)

    db_session.add_all([
        ClubEvening(naam="Parenavond", datum=date.today() + timedelta(days=3),
                    type="clubavond", deelnemers_type="paren",
                    season_id=season.id, club_id=club.id),
        ClubEvening(naam="Drive", datum=date.today() + timedelta(days=5),
                    type="clubavond", deelnemers_type="individueel",
                    season_id=season.id, club_id=club.id),
    ])
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: lid
    response = await client.get("/")
    assert response.status_code == 200
    assert ">Paren</span>" in response.text
    # 'individuele_drive' staat niet in de clublabels → geen badge
    assert "Individuele drive" not in response.text


# ── Handmatig gekozen label ────────────────────────────────────────────────────

def test_evening_label_handmatige_keuze_krijgt_voorrang():
    """Een expliciet gekozen label wint van de automatische afleiding."""
    from app.club_settings import evening_label
    from app.models import Club, ClubEvening

    club = Club(naam="X")  # geen instelling → alle labels aan
    ev = ClubEvening(type="clubavond", deelnemers_type="paren", label="training")
    ev.club = club
    lbl = evening_label(ev)
    assert lbl["key"] == "training"
    assert lbl["naam"] == "Training"


def test_evening_label_handmatige_keuze_respecteert_clubinstelling():
    """Een handmatig label dat de club niet (meer) gebruikt, wordt verborgen."""
    from app.club_settings import evening_label
    from app.models import Club, ClubEvening

    club = Club(naam="X", labels="paren")
    ev = ClubEvening(type="clubavond", deelnemers_type="paren", label="training")
    ev.club = club
    assert evening_label(ev) is None


def test_evening_label_ongeldige_handmatige_waarde_valt_terug_op_afleiding():
    """Onbekende/oude waarde in ClubEvening.label → gedraagt zich als 'automatisch'."""
    from app.club_settings import evening_label
    from app.models import Club, ClubEvening

    club = Club(naam="X")
    ev = ClubEvening(type="clubavond", deelnemers_type="paren", label="onzin")
    ev.club = club
    lbl = evening_label(ev)
    assert lbl["key"] == "paren"


async def test_avonden_formulier_toont_labelkeuze(client, db_session):
    """Aanmaakformulier bevat een labelkeuze met de ingestelde labels van de club."""
    from app.main import app

    club, wl = _wl_met_club(db_session, evenement_types="clubavond", labels="training,paren")
    _set_auth(app, wl=wl)
    response = await client.get("/beheer/avonden")
    assert response.status_code == 200
    assert 'name="label"' in response.text
    assert '<option value="">Automatisch' in response.text
    assert '<option value="training">Training</option>' in response.text
    assert '<option value="paren">Paren</option>' in response.text
    assert '<option value="viertallen">Viertallen</option>' not in response.text


async def test_avonden_aanmaken_met_handmatig_label(client, db_session):
    """POST met een gekozen label slaat dat label op het evenement op."""
    from app.main import app
    from app.models import ClubEvening
    from datetime import date, timedelta

    from app.models import Season

    club, wl = _wl_met_club(db_session, labels="training,paren")
    season = Season(naam="S", start_datum=date(2020, 1, 1), eind_datum=date(2030, 12, 31),
                    actief=True, club_id=club.id)
    db_session.add(season)
    db_session.commit()

    _set_auth(app, wl=wl)
    datum = (date.today() + timedelta(days=10)).isoformat()
    response = await client.post("/beheer/avonden", data={
        "naam": "Speciale clubavond",
        "datum": datum,
        "type": "clubavond",
        "deelnemers_type": "paren",
        "label": "training",
    })
    assert response.status_code == 302

    evt = db_session.query(ClubEvening).filter(ClubEvening.naam == "Speciale clubavond").first()
    assert evt is not None
    assert evt.label == "training"


async def test_avonden_aanmaken_zonder_labelkeuze_blijft_automatisch(client, db_session):
    """Leeg gelaten labelveld (Automatisch) slaat geen label op."""
    from app.main import app
    from app.models import ClubEvening, Season
    from datetime import date, timedelta

    club, wl = _wl_met_club(db_session)
    season = Season(naam="S", start_datum=date(2020, 1, 1), eind_datum=date(2030, 12, 31),
                    actief=True, club_id=club.id)
    db_session.add(season)
    db_session.commit()

    _set_auth(app, wl=wl)
    datum = (date.today() + timedelta(days=11)).isoformat()
    response = await client.post("/beheer/avonden", data={
        "naam": "Gewone clubavond",
        "datum": datum,
        "type": "clubavond",
        "deelnemers_type": "paren",
    })
    assert response.status_code == 302

    evt = db_session.query(ClubEvening).filter(ClubEvening.naam == "Gewone clubavond").first()
    assert evt is not None
    assert evt.label is None
