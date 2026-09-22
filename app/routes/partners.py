"""Zoeken naar aanmeldpartners (naam of NBB-nummer) en favorieten daarvoor —
zie app/static/partner-zoek.js voor de bijbehorende dropdown-component."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_member_club_ids, require_auth
from app.database import get_db
from app.models import Favorite, Lid, Member
from app.utils.nbb import normaliseer_nbb

router = APIRouter(prefix="/partners")

_MAX_RESULTATEN = 10


def _als_dict(voornaam: str, achternaam: str, nummer: str | None) -> dict:
    return {"voornaam": voornaam, "achternaam": achternaam, "nummer": nummer or ""}


@router.get("/zoek")
async def partners_zoek(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    q = q.strip()

    favorieten = (
        db.query(Favorite)
        .filter(Favorite.member_id == current_user.id)
        .order_by(Favorite.achternaam, Favorite.voornaam)
        .all()
    )
    favorieten_dicts = [_als_dict(f.voornaam, f.achternaam, f.nbb_nummer) for f in favorieten]

    if q:
        genorm_q = normaliseer_nbb(q)
        favorieten_dicts = [
            f for f in favorieten_dicts
            if q.lower() in f"{f['voornaam']} {f['achternaam']}".lower()
            or (f["nummer"] and normaliseer_nbb(f["nummer"]) == genorm_q)
        ]

    resultaten: list[dict] = []
    if q:
        club_ids = get_member_club_ids(current_user, db)
        query = db.query(Lid)
        if club_ids:
            query = query.filter(Lid.club_id.in_(club_ids))
        kandidaten = query.filter(
            or_(
                Lid.voornaam.ilike(f"%{q}%"),
                Lid.achternaam.ilike(f"%{q}%"),
                (Lid.voornaam + " " + Lid.achternaam).ilike(f"%{q}%"),
            )
        ).limit(50).all()
        # NBB-nummer los filteren (met voorloopnul-normalisatie) i.p.v. in de
        # SQL-query, want dat vraagt Python-side normalisatie.
        if not kandidaten and q.isdigit():
            genorm_q = normaliseer_nbb(q)
            alle = query.filter(Lid.nbb_nummer.isnot(None)).all()
            kandidaten = [lid for lid in alle if normaliseer_nbb(lid.nbb_nummer) == genorm_q]

        eigen_naam = f"{current_user.voornaam} {current_user.achternaam}".lower()
        favoriet_namen = {(f["voornaam"].lower(), f["achternaam"].lower()) for f in favorieten_dicts}
        gezien: set[tuple[str, str]] = set()
        for lid in kandidaten:
            sleutel = (lid.voornaam.lower(), lid.achternaam.lower())
            if sleutel in gezien or sleutel in favoriet_namen:
                continue
            if f"{lid.voornaam} {lid.achternaam}".lower() == eigen_naam:
                continue
            gezien.add(sleutel)
            resultaten.append(_als_dict(lid.voornaam, lid.achternaam, lid.nbb_nummer))
            if len(resultaten) >= _MAX_RESULTATEN:
                break

    return JSONResponse({"favorieten": favorieten_dicts, "resultaten": resultaten})


@router.post("/favorieten/toggle")
async def favoriet_toggle(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    form = await request.form()
    voornaam = form.get("voornaam", "").strip()
    achternaam = form.get("achternaam", "").strip()
    nummer = form.get("nummer", "").strip() or None
    if not voornaam or not achternaam:
        return JSONResponse({"fout": "naam_verplicht"}, status_code=400)

    bestaand = (
        db.query(Favorite)
        .filter(
            Favorite.member_id == current_user.id,
            Favorite.voornaam.ilike(voornaam),
            Favorite.achternaam.ilike(achternaam),
        )
        .first()
    )
    if bestaand:
        db.delete(bestaand)
        db.commit()
        return JSONResponse({"favoriet": False})

    db.add(Favorite(
        member_id=current_user.id, voornaam=voornaam, achternaam=achternaam, nbb_nummer=nummer,
    ))
    db.commit()
    return JSONResponse({"favoriet": True})
