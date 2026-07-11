"""
Beleid rond niet-leden: hoe een club omgaat met (1) niet-leden die zichzelf
aanmelden via de gepersonaliseerde gastlink en (2) leden die een niet-lid als
partner opgeven. Opgeslagen als een enkele string op Club.niet_lid_beleid /
Club.niet_lid_paar_beleid; NULL/onbekend betekent: "toegestaan" (huidig gedrag).
"""
import secrets

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Club, Lid

# Beleid voor niet-leden die zichzelf aanmelden via de gastlink
NIET_LID_BELEID_KEUZES: list[tuple[str, str]] = [
    ("geblokkeerd", "Niet toestaan — de gebruiker krijgt de melding "
                    "“niet-leden kunnen niet aangemeld worden”"),
    ("goedkeuring", "Alleen na goedkeuring van de wedstrijdleider"),
    ("gemeld", "Direct goedgekeurd, met melding aan de wedstrijdleider"),
    ("toegestaan", "Direct goedgekeurd, er gebeurt verder niets"),
]
NIET_LID_BELEID_KEYS = [k for k, _ in NIET_LID_BELEID_KEUZES]
_NIET_LID_BELEID_STANDAARD = "toegestaan"

# Beleid voor leden die een niet-lid als partner opgeven
NIET_LID_PAAR_BELEID_KEUZES: list[tuple[str, str]] = [
    ("verwijderd", "Nee — een niet-lid partner opgeven is niet mogelijk"),
    ("goedkeuring", "Ja, maar alleen na goedkeuring van de wedstrijdleider"),
    ("gemeld", "Ja, het paar wordt aangemeld maar de wedstrijdleider krijgt "
               "een melding"),
    ("toegestaan", "Ja, er gebeurt verder niets"),
]
NIET_LID_PAAR_BELEID_KEYS = [k for k, _ in NIET_LID_PAAR_BELEID_KEUZES]
_NIET_LID_PAAR_BELEID_STANDAARD = "toegestaan"


def niet_lid_beleid(club: Club | None) -> str:
    """Beleid van deze club voor gast-zelfaanmeldingen; NULL/onbekend → 'toegestaan'."""
    if club is None or club.niet_lid_beleid not in NIET_LID_BELEID_KEYS:
        return _NIET_LID_BELEID_STANDAARD
    return club.niet_lid_beleid


def niet_lid_paar_beleid(club: Club | None) -> str:
    """Beleid van deze club voor niet-lid-partners; NULL/onbekend → 'toegestaan'."""
    if club is None or club.niet_lid_paar_beleid not in NIET_LID_PAAR_BELEID_KEYS:
        return _NIET_LID_PAAR_BELEID_STANDAARD
    return club.niet_lid_paar_beleid


def is_bekend_lid(
    db: Session, club_id: int | None, voornaam: str, achternaam: str,
) -> bool:
    """True als (voornaam, achternaam) voorkomt in de ledenlijst (Lid) van deze club."""
    if not club_id or not voornaam or not achternaam:
        return False
    return (
        db.query(Lid)
        .filter(
            Lid.club_id == club_id,
            func.lower(Lid.voornaam) == voornaam.strip().lower(),
            func.lower(Lid.achternaam) == achternaam.strip().lower(),
        )
        .first()
        is not None
    )


def maak_gast_token() -> str:
    return secrets.token_urlsafe(16)
