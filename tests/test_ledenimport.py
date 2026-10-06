"""
Tests voor de ledenlijst-import (/beheer/leden/importeer en
/beheer/clubs/{club_id}/leden/importeer): een upload vervangt de huidige
`Lid`-lijst van de club volledig. Leden die in beide lijsten voorkomen
blijven ongewijzigd; alleen echt nieuwe/verdwenen leden worden toegevoegd of
verwijderd. Na afloop wordt een rapport met beide lijsten getoond.
"""
from tests.conftest import make_member


def make_club(db_session, naam="BC Test"):
    from app.models import Club
    club = Club(naam=naam)
    db_session.add(club)
    db_session.commit()
    db_session.refresh(club)
    return club


def make_lid(db_session, voornaam, achternaam, nbb_nummer=None, club_id=None):
    from app.models import Lid
    lid = Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb_nummer, club_id=club_id)
    db_session.add(lid)
    db_session.commit()
    db_session.refresh(lid)
    return lid


def _no_csrf(app):
    from app.csrf import require_csrf
    app.dependency_overrides[require_csrf] = lambda: None


def _set_auth(app, admin):
    from app.auth import get_current_user, require_admin, require_auth, require_wedstrijdleider
    _no_csrf(app)
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[require_wedstrijdleider] = lambda: admin
    app.dependency_overrides[require_auth] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin


# ── Unit-tests voor importeer_ledenlijst_csv ──────────────────────────────────

def test_bestaand_lid_in_nieuwe_lijst_blijft_exact_ongewijzigd(db_session):
    from app.utils.ledenimport import importeer_ledenlijst_csv

    club = make_club(db_session)
    bestaand = make_lid(db_session, "Jan", "Jansen", nbb_nummer="OUD123", club_id=club.id)

    # Nieuw bestand bevat Jan Jansen met een ANDER nbb_nummer — moet genegeerd worden.
    csv_data = b"voornaam,achternaam,nbb_nummer\nJan,Jansen,NIEUW456\n"
    resultaat = importeer_ledenlijst_csv(csv_data, club.id, db_session)

    db_session.refresh(bestaand)
    assert bestaand.nbb_nummer == "OUD123"
    assert resultaat.toegevoegd == 0
    assert resultaat.verwijderd == 0
    assert resultaat.nieuwe_namen == []
    assert resultaat.verwijderde_namen == []


def test_nieuwe_leden_toegevoegd_en_verdwenen_leden_verwijderd(db_session):
    from app.models import Lid
    from app.utils.ledenimport import importeer_ledenlijst_csv

    club = make_club(db_session)
    make_lid(db_session, "Jan", "Jansen", club_id=club.id)
    make_lid(db_session, "Piet", "Pietersen", club_id=club.id)

    csv_data = b"voornaam,achternaam\nJan,Jansen\nNieuwe,Speler\n"
    resultaat = importeer_ledenlijst_csv(csv_data, club.id, db_session)

    overgebleven = {(l.voornaam, l.achternaam) for l in db_session.query(Lid).filter(Lid.club_id == club.id).all()}
    assert overgebleven == {("Jan", "Jansen"), ("Nieuwe", "Speler")}
    assert resultaat.toegevoegd == 1
    assert resultaat.verwijderd == 1
    assert resultaat.nieuwe_namen == ["Nieuwe Speler"]
    assert resultaat.verwijderde_namen == ["Piet Pietersen"]


def test_matching_is_hoofdletterongevoelig(db_session):
    from app.utils.ledenimport import importeer_ledenlijst_csv

    club = make_club(db_session)
    bestaand = make_lid(db_session, "jan", "JANSEN", club_id=club.id)

    csv_data = b"voornaam,achternaam\nJAN,jansen\n"
    resultaat = importeer_ledenlijst_csv(csv_data, club.id, db_session)

    db_session.refresh(bestaand)
    assert resultaat.toegevoegd == 0
    assert resultaat.verwijderd == 0


def test_rij_zonder_naam_wordt_overgeslagen_niet_toegevoegd(db_session):
    from app.models import Lid
    from app.utils.ledenimport import importeer_ledenlijst_csv

    club = make_club(db_session)
    csv_data = b"voornaam,achternaam\n,Zonder Voornaam\nMet,Naam\n"
    resultaat = importeer_ledenlijst_csv(csv_data, club.id, db_session)

    assert resultaat.overgeslagen == 1
    assert resultaat.toegevoegd == 1
    assert db_session.query(Lid).filter(Lid.club_id == club.id).count() == 1


def test_import_raakt_alleen_leden_van_de_opgegeven_club(db_session):
    from app.models import Lid
    from app.utils.ledenimport import importeer_ledenlijst_csv

    club_a = make_club(db_session, naam="Club A")
    club_b = make_club(db_session, naam="Club B")
    lid_b = make_lid(db_session, "Blijft", "InClubB", club_id=club_b.id)

    csv_data = b"voornaam,achternaam\nNieuw,InClubA\n"
    importeer_ledenlijst_csv(csv_data, club_a.id, db_session)

    assert db_session.query(Lid).filter(Lid.id == lid_b.id).first() is not None
    assert db_session.query(Lid).filter(Lid.club_id == club_b.id).count() == 1
    assert db_session.query(Lid).filter(Lid.club_id == club_a.id).count() == 1


# ── Route-niveau: flash-rapport na upload ─────────────────────────────────────

async def test_import_toont_rapport_met_nieuwe_en_verwijderde_leden(client, db_session):
    from app.main import app

    admin = make_member(db_session, lidnummer="LIMP001", role="admin")
    make_lid(db_session, "Oud", "Lid")
    _set_auth(app, admin)

    csv_data = b"voornaam,achternaam\nNieuw,Lid\n"
    response = await client.post(
        "/beheer/leden/importeer",
        files={"bestand": ("leden.csv", csv_data, "text/csv")},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/beheer/leden?import_ok=1"

    pagina = await client.get("/beheer/leden")
    assert pagina.status_code == 200
    tekst = pagina.text
    assert "succesvol geïmporteerd" in tekst
    assert "Nieuw Lid" in tekst
    assert "Oud Lid" in tekst

    # Rapport is eenmalig: een volgende paginabezoek toont het niet opnieuw.
    pagina2 = await client.get("/beheer/leden")
    assert "succesvol geïmporteerd" not in pagina2.text
