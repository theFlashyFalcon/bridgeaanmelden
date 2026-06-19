import logging
import math
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ClubEvening, Season, Uitslag
from app.utils.nbb_xml import PaarSpelers, SpelerResultaat, parse_nbb_xml

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ranking")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

EXCLUDED_TYPES = ["jeugdtraining", "training", "eten voor jeugdtraining"]
WEERGAVES = [
    "spanning", "lijn_a", "lijn_b", "iedereen",
    "imp_totaal", "consistentie", "vaste_partners", "vorm",
]


# ── Drempel ────────────────────────────────────────────────────────────────────

def _drempel(n_uitslagen: int) -> int:
    if n_uitslagen <= 5:
        return 1
    elif n_uitslagen <= 10:
        return 3
    elif n_uitslagen <= 15:
        return 8
    return 10


# ── XML helpers ────────────────────────────────────────────────────────────────

def _is_xml(inhoud: bytes) -> bool:
    return bool(inhoud) and inhoud[:200].lstrip().startswith(b"<")


def _decode(inhoud: bytes) -> str | None:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return inhoud.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


# ── Data laden ─────────────────────────────────────────────────────────────────

def _laad_avonden(db: Session, seizoen_id: int) -> tuple[list[dict], list[str]]:
    """
    Laad en parse alle XML-uitslagen voor een seizoen.
    Elke avond is een dict met datum + alle SpelerResultaat- en PaarSpelers-lijsten.
    Gesorteerd op datum oplopend (oudste eerst).
    """
    evenings = (
        db.query(ClubEvening)
        .filter(
            ClubEvening.season_id == seizoen_id,
            ClubEvening.datum < date.today(),
            ClubEvening.type.notin_(EXCLUDED_TYPES),
        )
        .all()
    )
    evening_map = {e.id: e for e in evenings}
    evening_ids = list(evening_map)
    if not evening_ids:
        return [], []

    uitslagen = (
        db.query(Uitslag)
        .filter(Uitslag.evening_id.in_(evening_ids))
        .all()
    )

    avonden: list[dict] = []
    waarschuwingen: list[str] = []

    for u in uitslagen:
        if not _is_xml(u.inhoud):
            continue
        tekst = _decode(u.inhoud)
        if tekst is None:
            waarschuwingen.append(f"Uitslag kon niet gelezen worden (avond {u.evening_id}).")
            continue
        try:
            data = parse_nbb_xml(tekst)
            evening = evening_map.get(u.evening_id)
            data["datum"] = evening.datum if evening else date(2000, 1, 1)
            avonden.append(data)
        except Exception as exc:
            logger.warning("XML parse fout uitslag %s: %s", u.id, exc)
            waarschuwingen.append(f"Uitslag kon niet verwerkt worden (avond {u.evening_id}).")

    avonden.sort(key=lambda a: a["datum"])
    return avonden, waarschuwingen


# ── Aggregatie-functies ────────────────────────────────────────────────────────

def _speler_key(r: SpelerResultaat) -> str:
    return r.league_id or r.global_id or r.naam


def _aggregeer_rang(spelers: list[SpelerResultaat]) -> list[dict]:
    """Gemiddelde rangpositie per speler. Laag = goed."""
    per: dict[str, dict] = {}
    for r in spelers:
        k = _speler_key(r)
        if not k:
            continue
        if k not in per:
            per[k] = {"naam": r.naam, "deelnames": 0, "rang_totaal": 0}
        per[k]["deelnames"] += 1
        per[k]["rang_totaal"] += r.rang

    resultaat = []
    for s in per.values():
        s["gem_rang"] = round(s["rang_totaal"] / s["deelnames"], 2)
        resultaat.append(s)

    resultaat.sort(key=lambda s: (s["gem_rang"], -s["deelnames"]))
    return resultaat


def _aggregeer_imps(avonden: list[dict]) -> list[dict]:
    """Totale IMP-score per speler over het seizoen (spanning-resultaten)."""
    per: dict[str, dict] = {}
    for avond in avonden:
        for r in avond["spanning_spelers"]:
            k = _speler_key(r)
            if not k:
                continue
            if k not in per:
                per[k] = {"naam": r.naam, "deelnames": 0, "imp_totaal": 0, "boards_totaal": 0}
            per[k]["deelnames"] += 1
            per[k]["imp_totaal"] += r.absolute_result
            per[k]["boards_totaal"] += r.number_of_boards

    resultaat = []
    for s in per.values():
        s["gem_imp_per_board"] = (
            round(s["imp_totaal"] / s["boards_totaal"], 3)
            if s["boards_totaal"] > 0 else 0.0
        )
        resultaat.append(s)

    # Hoogste totaal IMP eerst; gelijkspel → meeste deelnames
    resultaat.sort(key=lambda s: (-s["imp_totaal"], -s["deelnames"]))
    return resultaat


def _aggregeer_consistentie(avonden: list[dict], sleutel: str = "spanning_spelers") -> list[dict]:
    """
    Standaarddeviatie van rangpositie per speler.
    Lager = consistenter. Minimaal 2 deelnames.
    """
    per: dict[str, dict] = {}
    for avond in avonden:
        for r in avond[sleutel]:
            k = _speler_key(r)
            if not k:
                continue
            if k not in per:
                per[k] = {"naam": r.naam, "rangen": []}
            per[k]["rangen"].append(r.rang)

    resultaat = []
    for s in per.values():
        rangen = s["rangen"]
        if len(rangen) < 2:
            continue
        gem = sum(rangen) / len(rangen)
        variantie = sum((x - gem) ** 2 for x in rangen) / len(rangen)
        s["deelnames"] = len(rangen)
        s["gem_rang"] = round(gem, 2)
        s["std_dev"] = round(math.sqrt(variantie), 2)
        resultaat.append(s)

    resultaat.sort(key=lambda s: (s["std_dev"], s["gem_rang"]))
    return resultaat


def _aggregeer_vaste_partners(avonden: list[dict], min_samen: int = 2) -> list[dict]:
    """
    Partnership-statistieken: hoe vaak speelde elk paar samen, met hun gem. resultaat.
    Gesorteerd op aantal keren samen (meest frequent bovenaan).
    """
    per: dict[tuple, dict] = {}
    for avond in avonden:
        for p in avond["spanning_paren_spelers"]:
            k = tuple(sorted([p.speler1_id or p.speler1_naam,
                               p.speler2_id or p.speler2_naam]))
            if k not in per:
                per[k] = {
                    "display_naam": p.display_naam,
                    "samen": 0,
                    "rang_totaal": 0,
                    "imp_totaal": 0,
                    "boards_totaal": 0,
                }
            per[k]["samen"] += 1
            per[k]["rang_totaal"] += p.rang
            per[k]["imp_totaal"] += p.absolute_result
            per[k]["boards_totaal"] += p.number_of_boards

    resultaat = []
    for s in per.values():
        if s["samen"] < min_samen:
            continue
        s["gem_rang"] = round(s["rang_totaal"] / s["samen"], 2)
        s["gem_imp_per_board"] = (
            round(s["imp_totaal"] / s["boards_totaal"], 3)
            if s["boards_totaal"] > 0 else 0.0
        )
        resultaat.append(s)

    resultaat.sort(key=lambda s: (-s["samen"], s["gem_rang"]))
    return resultaat


def _aggregeer_vorm(avonden: list[dict], n_avonden: int) -> list[dict]:
    """Spanning-ranking van de meest recente N avonden."""
    recente = avonden[-n_avonden:] if n_avonden < len(avonden) else avonden
    spelers = [r for avond in recente for r in avond["spanning_spelers"]]
    return _aggregeer_rang(spelers)


# ── Route ──────────────────────────────────────────────────────────────────────

def _get_display_role(request: Request, current_user) -> str:
    if current_user.role == "admin":
        view_as = request.session.get("view_as_role")
        return view_as if view_as else current_user.role
    return current_user.role


@router.get("")
async def ranking_pagina(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=401)

    display_role = _get_display_role(request, current_user)
    seizoenen = db.query(Season).order_by(Season.start_datum.desc()).all()
    actief = next((s for s in seizoenen if s.actief), None)

    try:
        seizoen_id = int(request.query_params.get("seizoen_id", ""))
    except (ValueError, TypeError):
        seizoen_id = actief.id if actief else (seizoenen[0].id if seizoenen else None)

    geselecteerd = next((s for s in seizoenen if s.id == seizoen_id), None)

    weergave = request.query_params.get("weergave", "spanning")
    if weergave not in WEERGAVES:
        weergave = "spanning"

    try:
        n_avonden = max(1, int(request.query_params.get("n_avonden", "5")))
    except (ValueError, TypeError):
        n_avonden = 5

    # Laad alle avonden voor dit seizoen
    avonden, waarschuwingen = _laad_avonden(db, seizoen_id) if seizoen_id else ([], [])
    n_uitslagen = len(avonden)
    drempel = _drempel(n_uitslagen)

    # Bereken data voor de gekozen weergave
    hoofd_ranking: list[dict] = []
    volledige_lijst: list[dict] = []
    partner_lijst: list[dict] = []

    if n_uitslagen > 0:
        if weergave == "spanning":
            spelers = [r for a in avonden for r in a["spanning_spelers"]]
            alle = _aggregeer_rang(spelers)
            hoofd_ranking = [s for s in alle if s["deelnames"] >= drempel]
            volledige_lijst = alle

        elif weergave == "lijn_a":
            spelers = [r for a in avonden for r in a["lijn_a_spelers"]]
            alle = _aggregeer_rang(spelers)
            hoofd_ranking = [s for s in alle if s["deelnames"] >= drempel]
            volledige_lijst = alle

        elif weergave == "lijn_b":
            spelers = [r for a in avonden for r in a["lijn_b_spelers"]]
            alle = _aggregeer_rang(spelers)
            hoofd_ranking = [s for s in alle if s["deelnames"] >= drempel]
            volledige_lijst = alle

        elif weergave == "iedereen":
            spelers = [r for a in avonden for r in a["spanning_spelers"]]
            hoofd_ranking = _aggregeer_rang(spelers)

        elif weergave == "imp_totaal":
            hoofd_ranking = _aggregeer_imps(avonden)

        elif weergave == "consistentie":
            hoofd_ranking = _aggregeer_consistentie(avonden)
            volledige_lijst = hoofd_ranking  # altijd al min. 2 deelnames

        elif weergave == "vaste_partners":
            partner_lijst = _aggregeer_vaste_partners(avonden)

        elif weergave == "vorm":
            hoofd_ranking = _aggregeer_vorm(avonden, n_avonden)

    # Voeg rang toe
    for i, s in enumerate(hoofd_ranking, 1):
        s["rang"] = i
    for i, s in enumerate(volledige_lijst, 1):
        s["rang"] = i
    for i, s in enumerate(partner_lijst, 1):
        s["rang"] = i

    return templates.TemplateResponse(
        request,
        "ranking.html",
        {
            "current_user": current_user,
            "display_role": display_role,
            "seizoenen": seizoenen,
            "geselecteerd": geselecteerd,
            "seizoen_id": seizoen_id,
            "weergave": weergave,
            "n_uitslagen": n_uitslagen,
            "n_avonden": n_avonden,
            "drempel": drempel,
            "hoofd_ranking": hoofd_ranking,
            "volledige_lijst": volledige_lijst,
            "partner_lijst": partner_lijst,
            "waarschuwingen": waarschuwingen,
            "welkom": False,
        },
    )
