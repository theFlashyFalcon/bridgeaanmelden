"""Normalisatie van NBB-lidnummers voor vergelijking.

Sommige leden vullen een voorloopnul in (bv. "012345" i.p.v. "12345") omdat
dat vroeger gangbaar was. Nummers worden opgeslagen zoals ingevoerd (om het
brondocument niet te wijzigen), maar bij het vergelijken/matchen wordt altijd
genormaliseerd zodat "012345" en "12345" als hetzelfde nummer herkend worden.
"""
from typing import Optional


def normaliseer_nbb(nummer: Optional[str]) -> str:
    """Geeft een NBB-nummer terug zonder omliggende spaties en voorloopnullen."""
    if not nummer:
        return ""
    kaal = nummer.strip().lstrip("0")
    return kaal or "0"


def zelfde_nbb(a: Optional[str], b: Optional[str]) -> bool:
    """True als a en b hetzelfde NBB-nummer zijn, voorloopnullen genegeerd."""
    na, nb = normaliseer_nbb(a), normaliseer_nbb(b)
    return bool(na) and na == nb
