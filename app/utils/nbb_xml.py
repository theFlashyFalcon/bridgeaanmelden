"""Parser voor NBB XML-uitslagen (ReportablePairsSession formaat)."""
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class PaarResultaat:
    """Paar-resultaat voor weergave op de uitslag-pagina."""
    paar_naam: str
    rang: int
    score: float
    sectie: str  # 'A' of 'B'
    absolute_result: int = 0  # totale IMP die avond


@dataclass
class SpelerResultaat:
    """Individueel resultaat voor ranking-berekeningen."""
    league_id: str
    global_id: str
    naam: str
    rang: int
    sectie: str
    absolute_result: int = 0   # totale IMP die avond
    number_of_boards: int = 0  # aantal gespeelde spellen


@dataclass
class PaarSpelers:
    """Twee spelers die samen speelden — voor partnership-statistieken."""
    speler1_id: str
    speler1_naam: str
    speler2_id: str
    speler2_naam: str
    display_naam: str          # gesorteerd op naam voor consistente weergave
    rang: int
    absolute_result: int
    number_of_boards: int


def _bouw_naam(el: ET.Element) -> str:
    voornaam = (el.findtext("Voornaam") or "").strip()
    tussen = (el.findtext("Tussenvoegsel") or "").strip()
    achter = (el.findtext("Achternaam") or "").strip()
    return " ".join(d for d in [voornaam, tussen, achter] if d)


def _int(tekst: str | None) -> int:
    try:
        return int((tekst or "0").strip())
    except (ValueError, AttributeError):
        return 0


def _float(tekst: str | None) -> float:
    try:
        return float((tekst or "0").strip())
    except (ValueError, AttributeError):
        return 0.0


def parse_nbb_xml(xml_tekst: str) -> dict:
    """
    Parse NBB XML uitslag.

    Returns dict met:
      wedstrijd_naam, sessie_datum,
      spanning_paren / lijn_a_paren / lijn_b_paren      (voor weergave),
      spanning_spelers / lijn_a_spelers / lijn_b_spelers (voor ranking),
      spanning_paren_spelers                             (voor partnership-stats).
    """
    try:
        root = ET.fromstring(xml_tekst.encode("utf-8"))
    except ET.ParseError:
        root = ET.fromstring(xml_tekst)

    wedstrijd_naam = (root.findtext("CompetitionName") or "").strip()
    sessie_datum = (root.findtext("SessionDate") or "").strip()

    spanning_paren: list[PaarResultaat] = []
    lijn_a_paren: list[PaarResultaat] = []
    lijn_b_paren: list[PaarResultaat] = []
    spanning_spelers: list[SpelerResultaat] = []
    lijn_a_spelers: list[SpelerResultaat] = []
    lijn_b_spelers: list[SpelerResultaat] = []
    spanning_paren_spelers: list[PaarSpelers] = []

    for res in root.findall(".//ReportableSessionResult"):
        is_spanning = (res.findtext("IsSpanningResult") or "false").lower() == "true"
        is_eigen = (res.findtext("IsCalculatedInOwnSection") or "false").lower() == "true"

        if not is_spanning and not is_eigen:
            continue

        rang = _int(res.findtext("ParticipantRank"))
        score = _float(res.findtext("Result"))
        absolute_result = _int(res.findtext("AbsoluteResult"))
        number_of_boards = _int(res.findtext("NumberOfBoards"))
        sectie = (res.findtext("SectionLetters") or "").strip()
        paar_naam = (res.findtext("ParticipantName") or "").strip()

        paar = PaarResultaat(paar_naam=paar_naam, rang=rang, score=score, sectie=sectie, absolute_result=absolute_result)
        if is_spanning:
            spanning_paren.append(paar)
        if is_eigen:
            if sectie == "A":
                lijn_a_paren.append(paar)
            elif sectie == "B":
                lijn_b_paren.append(paar)

        # Individuele spelers
        speler1_el = res.find("PlayerOne")
        speler2_el = res.find("PlayerTwo")

        for speler_el in (speler1_el, speler2_el):
            if speler_el is None:
                continue
            league_id = (speler_el.findtext("LeagueId") or "").strip()
            global_id = (speler_el.findtext("GlobalId") or "").strip()
            naam = _bouw_naam(speler_el)

            r = SpelerResultaat(
                league_id=league_id,
                global_id=global_id,
                naam=naam,
                rang=rang,
                sectie=sectie,
                absolute_result=absolute_result,
                number_of_boards=number_of_boards,
            )
            if is_spanning:
                spanning_spelers.append(r)
            if is_eigen:
                if sectie == "A":
                    lijn_a_spelers.append(r)
                elif sectie == "B":
                    lijn_b_spelers.append(r)

        # Partnership-statistieken (alleen spanning, één entry per paar per avond)
        if is_spanning and speler1_el is not None and speler2_el is not None:
            id1 = (speler1_el.findtext("LeagueId") or "").strip() or (speler1_el.findtext("GlobalId") or "").strip()
            id2 = (speler2_el.findtext("LeagueId") or "").strip() or (speler2_el.findtext("GlobalId") or "").strip()
            naam1 = _bouw_naam(speler1_el)
            naam2 = _bouw_naam(speler2_el)

            # Gesorteerde namen voor consistente weergave over avonden
            if naam1 <= naam2:
                display_naam = f"{naam1} & {naam2}"
                s1_id, s1_naam, s2_id, s2_naam = id1, naam1, id2, naam2
            else:
                display_naam = f"{naam2} & {naam1}"
                s1_id, s1_naam, s2_id, s2_naam = id2, naam2, id1, naam1

            spanning_paren_spelers.append(PaarSpelers(
                speler1_id=s1_id,
                speler1_naam=s1_naam,
                speler2_id=s2_id,
                speler2_naam=s2_naam,
                display_naam=display_naam,
                rang=rang,
                absolute_result=absolute_result,
                number_of_boards=number_of_boards,
            ))

    for lst in [spanning_paren, lijn_a_paren, lijn_b_paren]:
        lst.sort(key=lambda p: p.rang)

    return {
        "wedstrijd_naam": wedstrijd_naam,
        "sessie_datum": sessie_datum,
        "spanning_paren": spanning_paren,
        "lijn_a_paren": lijn_a_paren,
        "lijn_b_paren": lijn_b_paren,
        "spanning_spelers": spanning_spelers,
        "lijn_a_spelers": lijn_a_spelers,
        "lijn_b_spelers": lijn_b_spelers,
        "spanning_paren_spelers": spanning_paren_spelers,
    }
