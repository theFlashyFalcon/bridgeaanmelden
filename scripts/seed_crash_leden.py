"""
Vul de 'leden' tabel met leden van Crash (NBBR 9040).

Uitvoeren:
    python -m scripts.seed_crash_leden

Het script is idempotent: bestaande records (op nbb_nummer) worden
overgeslagen zodat het meerdere keren veilig gedraaid kan worden.
"""
import re
import sys
from pathlib import Path

# Zorg dat de app-root op het pad staat
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.models import Lid


CSV_PATH = Path(__file__).parent.parent / "data" / "ledenlijst_nbbr_9040.csv"

# Aantal velden per record in het NBB-Rekenprogramma exportformaat
_RECORD_SIZE = 16


def parse_nbbr_csv(content: str) -> list[dict]:
    """Verwerk de NBB-Rekenprogramma CSV naar een lijst met lidgegevens.

    Kolomindeling (1-indexed, zoals NBB exporteert):
      1  = NBB-nummer
      2  = Geslacht
      3  = Voornaam
      4  = Initialen
      5  = Tussenvoegsel
      6  = Achternaam
      7–16 = Adres, contact, etc. (niet opgeslagen)
    """
    # Verwijder de bestandsheader inclusief het versienummer (3 cijfers na '=')
    # Voorbeeld: "Import=SpelerTarget=NBB-RekenprogrammaVersion=210669660;M;..."
    # Na strip: "669660;M;..."
    content = re.sub(r"^Import=SpelerTarget=NBB-RekenprogrammaVersion=\d{3}", "", content.strip())

    fields = content.split(";")

    records = []
    for i in range(0, len(fields), _RECORD_SIZE):
        chunk = fields[i : i + _RECORD_SIZE]
        if len(chunk) < 6:
            break

        nbb = chunk[0].lstrip("0")
        if not nbb:
            continue  # eindregel (alles nullen)

        voornaam = chunk[2].strip()
        tussenvoegsel = chunk[4].strip()
        achternaam_raw = chunk[5].strip()

        if not voornaam or not achternaam_raw:
            continue

        # Combineer tussenvoegsel en achternaam (zoals ook in Member.achternaam)
        achternaam = f"{tussenvoegsel} {achternaam_raw}".strip() if tussenvoegsel else achternaam_raw

        records.append(
            {
                "nbb_nummer": nbb,
                "voornaam": voornaam,
                "achternaam": achternaam,
            }
        )

    return records


def seed(db=None) -> int:
    """Voeg ontbrekende Crash-leden toe aan de leden-tabel.

    Geeft het aantal nieuw toegevoegde records terug.
    """
    close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        content = CSV_PATH.read_text(encoding="utf-8")
        records = parse_nbbr_csv(content)

        toegevoegd = 0
        for r in records:
            exists = (
                db.query(Lid).filter(Lid.nbb_nummer == r["nbb_nummer"]).first()
            )
            if not exists:
                db.add(
                    Lid(
                        nbb_nummer=r["nbb_nummer"],
                        voornaam=r["voornaam"],
                        achternaam=r["achternaam"],
                    )
                )
                toegevoegd += 1

        db.commit()
        return toegevoegd
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    n = seed()
    print(f"{n} leden van Crash toegevoegd aan de database.")
