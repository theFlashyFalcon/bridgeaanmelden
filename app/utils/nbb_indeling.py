"""Genereert een .nbbcr (ProposedSession) indeling voor de NBB-clubsoftware,
op basis van de aanmeldingen van een avond.

Let op — best-effort, deels niet-geverifieerde aannames (zie implementatieplan):
- MovementId wordt afgeleid met een uit één voorbeeldbestand teruggerekende
  formule, niet bevestigd door de NBB-clubsoftware zelf.
- GlobalId (NBB's interne player-GUID) wordt altijd leeg gelaten — de app
  slaat dit nergens op.
- NBBClubranking (het officiële NBB-percentage) hebben we niet en wordt als
  0.0 weggeschreven; dit veld is puur informatief en beïnvloedt geen koppeling.
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ClubEvening, Lid
from app.routes.rankings import _aggregeer_rang, _laad_avonden

_TUSSENVOEGSELS = [
    "van der", "van den", "van de", "van 't",
    "uit de", "uit het", "op de", "op het", "aan de", "aan het", "in het", "in de",
    "de la", "den", "der", "ten", "ter", "van", "de", "op", "'t",
]


@dataclass
class Speler:
    voornaam: str
    achternaam: str
    lidnummer_hint: Optional[str] = None


def _split_achternaam(achternaam: str) -> tuple[str, str]:
    """Best-effort splitsing in (tussenvoegsel, achternaam) op basis van een
    vaste lijst Nederlandse tussenvoegsels — geen garantie voor elke naam."""
    woorden = achternaam.strip().split(" ")
    for n in (2, 1):
        if len(woorden) > n and " ".join(woorden[:n]).lower() in _TUSSENVOEGSELS:
            return " ".join(woorden[:n]), " ".join(woorden[n:])
    return "", achternaam.strip()


def _leden_lookup(db: Session, club_id: Optional[int]) -> dict[tuple[str, str], Lid]:
    q = db.query(Lid)
    if club_id:
        q = q.filter(Lid.club_id == club_id)
    return {
        (lid.voornaam.strip().lower(), lid.achternaam.strip().lower()): lid
        for lid in q.all()
    }


def _speler_data(speler: Speler, leden: dict[tuple[str, str], Lid]) -> dict:
    key = (speler.voornaam.strip().lower(), speler.achternaam.strip().lower())
    lid = leden.get(key)
    league_id = speler.lidnummer_hint or (lid.nbb_nummer if lid else None) or ""
    prefix, lastname = _split_achternaam(speler.achternaam)
    return {
        "FirstName": speler.voornaam.strip(),
        "Prefix": prefix,
        "LastName": lastname,
        "FullName": f"{speler.voornaam.strip()} {speler.achternaam.strip()}".strip(),
        "LeagueId": league_id,
        "IsNew": not bool(lid or speler.lidnummer_hint),
    }


def _pair_ranking(db: Session, evening: ClubEvening) -> dict[str, float]:
    """Gemiddelde rangpositie per speler (lager = sterker) uit de bestaande
    lokale ranking (zie app/routes/rankings.py), voor het seizoen van deze
    avond. Ontbreekt een speler hierin, dan komt het paar achteraan te staan."""
    club_ids = [evening.club_id] if evening.club_id else None
    avonden, _ = _laad_avonden(db, evening.season_id, club_ids)
    if not avonden:
        return {}
    ranking = _aggregeer_rang([a["spanning_spelers"] for a in avonden])
    return {s["naam"].strip().lower(): s["gem_rang"] for s in ranking}


def _movement_id(n_paren: int, letter: str) -> str:
    """Teruggerekend uit het voorbeeldbestand indeling-2026-05-27.nbbcr
    (16 paren -> '...-16-8-3-3-16Crash03A', 14 paren -> '...-14-7-3-3-14Crash03B').
    Niet bevestigd voor andere aantallen — test bij een echte import."""
    tafels = n_paren // 2
    return f"Clubcompetitie-3 ronden-{n_paren}-{tafels}-3-3-{n_paren}Crash03{letter}"


def _sub(parent: ET.Element, tag: str, text=None) -> ET.Element:
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _speler_element(
    parent: ET.Element, tag: str, data: dict, section_number: int, pair_number: int
) -> None:
    el = _sub(parent, tag)
    _sub(el, "GlobalId")
    _sub(el, "LeagueId", data["LeagueId"])
    _sub(el, "SectionNumber", section_number)
    _sub(el, "PairNumber", pair_number)
    _sub(el, "FullName", data["FullName"])
    _sub(el, "NBBClubranking", "0.0")
    _sub(el, "IsNew", "true" if data["IsNew"] else "false")
    _sub(el, "FirstName", data["FirstName"])
    _sub(el, "Initials")
    _sub(el, "Prefix", data["Prefix"])
    _sub(el, "LastName", data["LastName"])


def genereer_indeling_xml(
    db: Session,
    evening: ClubEvening,
    paren: list[tuple[Speler, Speler]],
    aantal_secties: int = 1,
) -> str:
    """Bouwt een ProposedSession .nbbcr-bestand voor de gegeven paren.

    Paren worden gesorteerd op gemiddelde lokale ranking (sterkste eerst) en
    zo gelijk mogelijk verdeeld over `aantal_secties` secties (A, B, ...).
    """
    leden = _leden_lookup(db, evening.club_id)
    ranking = _pair_ranking(db, evening)

    def _pair_rang(paar: tuple[Speler, Speler]) -> float:
        s1, s2 = paar
        waarden = [
            ranking[key]
            for key in (
                f"{s1.voornaam} {s1.achternaam}".strip().lower(),
                f"{s2.voornaam} {s2.achternaam}".strip().lower(),
            )
            if key in ranking
        ]
        return sum(waarden) / len(waarden) if waarden else float("inf")

    gesorteerd = sorted(paren, key=_pair_rang)

    n = len(gesorteerd)
    secties = max(1, min(aantal_secties, max(n, 1)))
    basis, rest = divmod(n, secties)
    groepen: list[list[tuple[Speler, Speler]]] = []
    idx = 0
    for i in range(secties):
        grootte = basis + (1 if i < rest else 0)
        groepen.append(gesorteerd[idx: idx + grootte])
        idx += grootte

    root = ET.Element("ProposedSession", {
        "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
    })
    naam = evening.naam or evening.type
    _sub(root, "Name", f"{naam} {evening.datum.isoformat()}")
    _sub(root, "DatePlayed", f"{evening.datum.isoformat()}T00:00:00")
    sections_el = _sub(root, "Sections")

    for i, groep in enumerate(groepen):
        if not groep:
            continue
        letter = chr(ord("A") + i)
        section_number = i + 1
        section_el = _sub(sections_el, "ProposedSection")
        _sub(section_el, "Letters", letter)
        _sub(section_el, "Number", section_number)
        _sub(section_el, "MovementId", _movement_id(len(groep), letter))
        _sub(section_el, "NumberOfBoardsPerRound", 8)
        _sub(section_el, "Scoremethod", 2)
        _sub(section_el, "IsCombiSection", "false")
        pairs_el = _sub(section_el, "Pairs")
        for pn, (s1, s2) in enumerate(groep, start=1):
            pair_el = _sub(pairs_el, "ProposedPair")
            _sub(pair_el, "Number", pn)
            _sub(pair_el, "SectionNumber", section_number)
            d1, d2 = _speler_data(s1, leden), _speler_data(s2, leden)
            _speler_element(pair_el, "PlayerOne", d1, section_number, pn)
            _speler_element(pair_el, "PlayerTwo", d2, section_number, pn)
            _sub(pair_el, "IsAbsent", "false")

    kop = '<?xml version="1.0" encoding="utf-8"?>\n'
    return kop + ET.tostring(root, encoding="unicode")
