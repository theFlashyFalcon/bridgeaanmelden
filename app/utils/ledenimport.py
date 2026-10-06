"""Gedeelde CSV-ledenlijst-import (gebruikt door /beheer/leden/importeer en
/beheer/clubs/{club_id}/leden/importeer) — vervangt de huidige `Lid`-lijst
(de NBB-ledenlijst, los van gebruikersaccounts) van een club volledig door de
geïmporteerde lijst. Leden die in beide lijsten voorkomen (zelfde voornaam +
achternaam) blijven ongewijzigd staan; de rest wordt toegevoegd of verwijderd.
Corrigeert daarbij namen die dubbel UTF-8/Latin-1-gecodeerd zijn geraakt
(herkenbaar aan tekens als "Ã©"), zoals vaak voorkomt bij een export vanuit
het bondssysteem.
"""
import csv
import io
from dataclasses import dataclass, field

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
    verwijderd: int = 0
    overgeslagen: int = 0
    gecorrigeerd: list[str] = field(default_factory=list)
    nieuwe_namen: list[str] = field(default_factory=list)
    verwijderde_namen: list[str] = field(default_factory=list)


def importeer_ledenlijst_csv(inhoud: bytes, club_id: int | None, db: Session) -> ImportResultaat:
    try:
        tekst = inhoud.decode("utf-8-sig")  # utf-8-sig handles Excel BOM
    except UnicodeDecodeError:
        tekst = inhoud.decode("latin-1")

    reader = csv.DictReader(io.StringIO(tekst))
    resultaat = ImportResultaat()

    # (voornaam_lower, achternaam_lower) -> (voornaam, achternaam, nbb_nummer)
    geimporteerd: dict[tuple[str, str], tuple[str, str, str | None]] = {}
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
        geimporteerd[(voornaam.lower(), achternaam.lower())] = (voornaam, achternaam, nbb)

    bestaand_per_sleutel = {
        (lid.voornaam.strip().lower(), lid.achternaam.strip().lower()): lid
        for lid in db.query(Lid).filter(Lid.club_id == club_id).all()
    }

    nieuwe_sleutels = set(geimporteerd.keys())
    bestaande_sleutels = set(bestaand_per_sleutel.keys())

    # Alleen in de oude lijst: verwijderen. Aanwezig in beide: ongewijzigd laten.
    for sleutel in bestaande_sleutels - nieuwe_sleutels:
        lid = bestaand_per_sleutel[sleutel]
        resultaat.verwijderde_namen.append(f"{lid.voornaam} {lid.achternaam}")
        db.delete(lid)
        resultaat.verwijderd += 1

    # Alleen in de nieuwe lijst: toevoegen.
    for sleutel in nieuwe_sleutels - bestaande_sleutels:
        voornaam, achternaam, nbb = geimporteerd[sleutel]
        db.add(Lid(voornaam=voornaam, achternaam=achternaam, nbb_nummer=nbb, club_id=club_id))
        resultaat.nieuwe_namen.append(f"{voornaam} {achternaam}")
        resultaat.toegevoegd += 1

    resultaat.nieuwe_namen.sort()
    resultaat.verwijderde_namen.sort()

    db.commit()
    return resultaat
