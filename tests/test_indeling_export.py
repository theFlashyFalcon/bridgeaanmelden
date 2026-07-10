"""Tests voor het 'Maak export'-scherm en de .nbbcr-indeling-generator."""
import xml.etree.ElementTree as ET

from tests.conftest import make_member
from tests.test_100_use_cases import (
    _set_auth,
    make_evening,
    make_lid_entry,
    make_registration,
    make_season_nu,
)


# ── nbb_indeling.genereer_indeling_xml (unit) ─────────────────────────────────

def test_genereer_indeling_xml_een_sectie(db_session):
    from app.utils.nbb_indeling import Speler, genereer_indeling_xml

    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="paren")

    paren = [
        (Speler(f"Voornaam{i}", f"Achternaam{i}"), Speler(f"Partner{i}", f"Achternaam{i}"))
        for i in range(16)
    ]

    xml_tekst = genereer_indeling_xml(db_session, evening, paren, aantal_secties=1)
    root = ET.fromstring(xml_tekst)

    sections = root.findall(".//ProposedSection")
    assert len(sections) == 1
    assert sections[0].findtext("Letters") == "A"
    assert sections[0].findtext("MovementId") == "Clubcompetitie-3 ronden-16-8-3-3-16Crash03A"
    pairs = sections[0].findall(".//ProposedPair")
    assert len(pairs) == 16


def test_genereer_indeling_xml_meerdere_secties(db_session):
    """30 paren over 2 secties verdelen, movement-formule per sectiegrootte."""
    from app.utils.nbb_indeling import Speler, genereer_indeling_xml

    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="paren")

    paren = [
        (Speler(f"Voornaam{i}", f"Achternaam{i}"), Speler(f"Partner{i}", f"Achternaam{i}"))
        for i in range(30)
    ]

    xml_tekst = genereer_indeling_xml(db_session, evening, paren, aantal_secties=2)
    root = ET.fromstring(xml_tekst)

    sections = root.findall(".//ProposedSection")
    assert len(sections) == 2
    totaal_paren = sum(len(s.findall(".//ProposedPair")) for s in sections)
    assert totaal_paren == 30
    for s in sections:
        n = len(s.findall(".//ProposedPair"))
        letter = s.findtext("Letters")
        assert s.findtext("MovementId") == f"Clubcompetitie-3 ronden-{n}-{n // 2}-3-3-{n}Crash03{letter}"


def test_genereer_indeling_xml_onbekende_speler_is_new(db_session):
    """Speler zonder match in de ledenlijst krijgt IsNew=true en leeg LeagueId."""
    from app.utils.nbb_indeling import Speler, genereer_indeling_xml

    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="paren")
    make_lid_entry(db_session, "Piet", "Klaassen", nbb_nummer="12345")

    paren = [(Speler("Piet", "Klaassen"), Speler("Onbekende", "Gast"))]
    xml_tekst = genereer_indeling_xml(db_session, evening, paren, aantal_secties=1)
    root = ET.fromstring(xml_tekst)

    player_one = root.find(".//PlayerOne")
    player_two = root.find(".//PlayerTwo")
    assert player_one.findtext("IsNew") == "false"
    assert player_one.findtext("LeagueId") == "12345"
    assert player_two.findtext("IsNew") == "true"
    assert player_two.findtext("LeagueId") == ""


# ── Exportscherm en indeling-route ────────────────────────────────────────────

async def test_export_scherm_toont_print_en_indeling_knop(client, db_session):
    wl = make_member(db_session, lidnummer="WL-EXP", role="wedstrijdleider")
    lid1 = make_member(db_session, voornaam="Emma", achternaam="Smit", lidnummer="ES01")
    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="paren")
    make_registration(db_session, lid1.id, evening.id, partner_naam="Frans de Groot")
    from app.main import app
    _set_auth(app, wl=wl)

    response = await client.get(f"/beheer/af-aanmeldingen/{evening.id}/export")
    assert response.status_code == 200
    assert "Maak print versie" in response.text
    assert "Maak indeling" in response.text


async def test_export_scherm_geen_indeling_voor_viertallen(client, db_session):
    from app.main import app
    wl = make_member(db_session, lidnummer="WL-EXP2", role="wedstrijdleider")
    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="viertallen")
    _set_auth(app, wl=wl)

    response = await client.get(f"/beheer/af-aanmeldingen/{evening.id}/export")
    assert response.status_code == 200
    assert "Maak indeling" not in response.text

    response = await client.post(f"/beheer/af-aanmeldingen/{evening.id}/indeling", data={})
    assert response.status_code == 400


async def test_indeling_download_bevat_aangemelde_paren(client, db_session):
    from app.main import app
    wl = make_member(db_session, lidnummer="WL-EXP3", role="wedstrijdleider")
    lid1 = make_member(db_session, voornaam="Anna", achternaam="Jansen", lidnummer="AJ01")
    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="paren")
    make_registration(db_session, lid1.id, evening.id, partner_naam="Bea Bakker")

    _set_auth(app, wl=wl)
    response = await client.post(
        f"/beheer/af-aanmeldingen/{evening.id}/indeling",
        data={"secties": "1"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "attachment" in response.headers["content-disposition"]

    root = ET.fromstring(response.text)
    namen = {el.text for el in root.findall(".//FullName")}
    assert "Anna Jansen" in namen
    assert "Bea Bakker" in namen


# ── Detailscherm: partnerverzoeken weg, blauwe gloed, tegelvolgorde ──────────

async def test_af_aanmeldingen_detail_geen_partnerverzoeken_wel_export_tegel(client, db_session):
    from app.main import app
    wl = make_member(db_session, lidnummer="WL-DET1", role="wedstrijdleider")
    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="paren")
    _set_auth(app, wl=wl)

    response = await client.get(f"/beheer/af-aanmeldingen/{evening.id}")
    assert response.status_code == 200
    assert "Partnerverzoeken" not in response.text
    assert "Maak export" in response.text


async def test_af_aanmeldingen_detail_blauwe_gloed_voor_onbekende_partner(client, db_session):
    from app.main import app
    wl = make_member(db_session, lidnummer="WL-DET2", role="wedstrijdleider")
    lid1 = make_member(db_session, voornaam="Cor", achternaam="Visser", lidnummer="CV01")
    make_lid_entry(db_session, "Cor", "Visser", nbb_nummer="999")
    season = make_season_nu(db_session)
    evening = make_evening(db_session, season.id, deelnemers_type="paren")
    make_registration(db_session, lid1.id, evening.id, partner_naam="Onbekende Gast")

    _set_auth(app, wl=wl)
    response = await client.get(f"/beheer/af-aanmeldingen/{evening.id}")
    assert response.status_code == 200
    assert 'class="naam-niet-lid"' in response.text
    assert "Onbekende Gast" in response.text
