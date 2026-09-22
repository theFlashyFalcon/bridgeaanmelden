"""Gedeelde CSV-ledenlijst-import (gebruikt door /beheer/leden/importeer en
/beheer/clubs/{club_id}/leden/importeer) — importeert namen in de `Lid`-tabel
(de NBB-ledenlijst, los van gebruikersaccounts) en corrigeert daarbij namen
die dubbel UTF-8/Latin-1-gecodeerd zijn geraakt (herkenbaar aan tekens als
"Ã©"), zoals vaak voorkomt bij een export vanuit het bondssysteem.
"""
import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Lid

_VERDACHTE_TEKENS = ("Ã", "Â", "â€")


def _corrigeer_mojibake(tekst: str) -> str:
    """Als tekst tekenen bevat die op dubbele encodering wijzen, probeer de
    oorspronkelijke UTF-8-tekst terug te winnen; anders ongewijzigd terug."""
    if not tekst or not any(teken in tekst for teken in _VERDACHTE_TEKENS):
        return tekst
    try:
        hersteld = tekst.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return tekst
    # Alleen gebruiken als het herstel geen nieuwe verdachte tekens oplevert
    # (anders was de oorspronkelijke tekst toch al correct).
    if any(teken in hersteld for teken in _VERDACHTE_TEKENS):
        return tekst
    return hersteld


@dataclass
class ImportResultaat:
    toegevoegd: int = 0
    overgeslagen: int = 0
    gecorrigeerd: list[str] = field(default_factory=list)


def importeer_ledenlijst_csv(inhoud: bytes, club_id: int | None, db: Session) -> ImportResultaat:
    try:
        tekst = inhoud.decode("utf-8-sig")  # utf-8-sig handles Excel BOM
    except UnicodeDecodeError:
        tekst = inhoud.decode("latin-1")

    reader = csv.DictReader(io.StringIO(tekst))
    resultaat = ImportResultaat()
    for rij in reader:
        ruwe_voornaam = (rij.get("voornaam") or rij.get("Voornaam") or "").strip()
        ruwe_achternaam = (rij.get("achternaam") or rij.get("Achternaam") or "").strip()
        nbb = (rij.get("nbb_nummer") or rij.get("NBB") or rij.get("nbb") or "").strip() or None

        voornaam = _corrigeer_mojibake(ruwe_voornaam)
        achternaam = _corrigeer_mojibake(ruwe_achternaam)
        if voornaam != ruwe_voornaam or achternaam != ruwe_achternaam:
            resultaat.gecorrigeerd.append(f"{ruwe_voornaam} {ruwe_achternaam} → {voornaam} {achternaam}")

        if not voornaam or not achternaam:
            resultaat.overgeslagen += 1
            continue
        al_aanwezig = (
            db.query(Lid)
            .filter(
                func.lower(Lid.voornaam) == voornaam.lower(),
                func.lower(Lid.achternaam) == achternaam.lower(),
                Lid.club_id == club_id,
            )
            .first()
        )
        if not al_aanwezig:
            db.add(Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb, club_id=club_id))
            resultaat.toegevoegd += 1
        else:
            resultaat.overgeslagen += 1
    db.commit()
    return resultaat
