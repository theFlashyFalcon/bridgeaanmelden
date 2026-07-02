from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_member_club_ids, require_auth, require_wedstrijdleider
from app.database import get_db
from app.models import ClubEvening, Member, Uitslag
from app.utils.nbb_xml import parse_nbb_xml

router = APIRouter(prefix="/uitslagen")
from app.templates_env import templates

EXCLUDED_TYPES = ["jeugdtraining", "training", "eten voor jeugdtraining"]


def _get_display_role(request: Request, current_user) -> str:
    if current_user.role == "admin":
        view_as = request.session.get("view_as_role")
        return view_as if view_as else current_user.role
    return current_user.role


def _is_xml(inhoud: bytes) -> bool:
    return bool(inhoud) and inhoud[:200].lstrip().startswith(b"<")


def _decode(inhoud: bytes) -> str | None:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return inhoud.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


@router.get("")
async def uitslagen_pagina(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    display_role = _get_display_role(request, current_user)
    kan_uploaden = display_role in ("wedstrijdleider", "admin")

    q = request.query_params.get("q", "").strip()
    today = date.today()

    user_club_ids = get_member_club_ids(current_user, db)
    query = db.query(ClubEvening).filter(
        ClubEvening.datum < today,
        ClubEvening.type.notin_(EXCLUDED_TYPES),
    )
    if user_club_ids:
        query = query.filter(
            (ClubEvening.club_id.in_(user_club_ids)) | (ClubEvening.club_id.is_(None))
        )

    if q:
        parsed_date = None
        try:
            parsed_date = datetime.strptime(q, "%d/%m/%Y").date()
        except ValueError:
            pass

        if parsed_date:
            query = query.filter(ClubEvening.datum == parsed_date)
        else:
            query = query.filter(ClubEvening.naam.ilike(f"%{q}%"))

    evenings = query.order_by(ClubEvening.datum.desc()).all()

    evening_ids = [e.id for e in evenings]
    uitslagen_map: dict[int, Uitslag] = {}
    if evening_ids:
        for uitslag in db.query(Uitslag).filter(Uitslag.evening_id.in_(evening_ids)).all():
            uitslagen_map[uitslag.evening_id] = uitslag

    return templates.TemplateResponse(
        request,
        "uitslagen.html",
        {
            "current_user": current_user,
            "display_role": display_role,
            "kan_uploaden": kan_uploaden,
            "evenings": evenings,
            "uitslagen_map": uitslagen_map,
            "q": q,
            "welkom": False,
        },
    )


@router.get("/uploaden")
async def uitslag_upload_algemeen_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    from app.auth import get_admin_club
    club = get_admin_club(current_user, db)
    today = date.today()
    q = db.query(ClubEvening).filter(ClubEvening.datum < today, ClubEvening.type.notin_(EXCLUDED_TYPES))
    if club:
        q = q.filter(ClubEvening.club_id == club.id)
    evenings = q.order_by(ClubEvening.datum.desc()).all()
    uitslagen_ids = {
        u.evening_id
        for u in db.query(Uitslag).filter(
            Uitslag.evening_id.in_([e.id for e in evenings])
        ).all()
    }
    return templates.TemplateResponse(
        request,
        "uitslag_uploaden_select.html",
        {
            "current_user": current_user,
            "evenings": evenings,
            "uitslagen_ids": uitslagen_ids,
            "welkom": False,
        },
    )


@router.post("/uploaden")
async def uitslag_upload_algemeen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    form = await request.form()
    evening_id_str = form.get("evening_id")
    bestand = form.get("bestand")

    if not evening_id_str:
        return RedirectResponse(url="/uitslagen/uploaden?fout=evening", status_code=302)

    try:
        event_id = int(evening_id_str)
    except (ValueError, TypeError):
        return RedirectResponse(url="/uitslagen/uploaden?fout=evening", status_code=302)

    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    if not bestand or not bestand.filename:
        return RedirectResponse(
            url=f"/uitslagen/uploaden?evening_id={event_id}&fout=bestand", status_code=302
        )

    inhoud_bytes = await bestand.read()

    bestaande = db.query(Uitslag).filter(Uitslag.evening_id == event_id).first()
    if bestaande:
        bestaande.inhoud = inhoud_bytes
        bestaande.bestandsnaam = bestand.filename
        bestaande.aangemaakt_door_id = current_user.id
    else:
        db.add(
            Uitslag(
                evening_id=event_id,
                bestandsnaam=bestand.filename,
                inhoud=inhoud_bytes,
                aangemaakt_door_id=current_user.id,
            )
        )

    db.commit()
    return RedirectResponse(url="/uitslagen?upload_ok=1", status_code=302)


@router.get("/{event_id}/weergave")
async def uitslag_weergave(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    uitslag = db.query(Uitslag).filter(Uitslag.evening_id == event_id).first()
    if not uitslag:
        raise HTTPException(status_code=404, detail="Uitslag niet gevonden")

    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()

    if not _is_xml(uitslag.inhoud):
        return RedirectResponse(url=f"/uitslagen/{event_id}/bestand")

    tekst = _decode(uitslag.inhoud)
    parse_fout = None
    wedstrijd_naam = ""
    sessie_datum = ""
    spanning_paren = []
    lijn_a_paren = []
    lijn_b_paren = []

    if tekst:
        try:
            data = parse_nbb_xml(tekst)
            wedstrijd_naam = data["wedstrijd_naam"]
            sessie_datum = data["sessie_datum"]
            spanning_paren = data["spanning_paren"]
            lijn_a_paren = data["lijn_a_paren"]
            lijn_b_paren = data["lijn_b_paren"]
        except Exception as exc:
            parse_fout = str(exc)
    else:
        parse_fout = "Bestand kon niet gelezen worden."

    display_role = _get_display_role(request, current_user)

    return templates.TemplateResponse(
        request,
        "uitslag_weergave.html",
        {
            "current_user": current_user,
            "display_role": display_role,
            "evening": evening,
            "uitslag": uitslag,
            "wedstrijd_naam": wedstrijd_naam,
            "sessie_datum": sessie_datum,
            "spanning_paren": spanning_paren,
            "lijn_a_paren": lijn_a_paren,
            "lijn_b_paren": lijn_b_paren,
            "parse_fout": parse_fout,
            "welkom": False,
        },
    )


@router.get("/{event_id}/bestand")
async def uitslag_bestand(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    uitslag = db.query(Uitslag).filter(Uitslag.evening_id == event_id).first()
    if not uitslag:
        raise HTTPException(status_code=404, detail="Uitslag niet gevonden")

    is_xml = _is_xml(uitslag.inhoud)
    media_type = "application/xml" if is_xml else "application/pdf"
    filename = uitslag.bestandsnaam or ("uitslag.xml" if is_xml else "uitslag.pdf")
    return Response(
        content=uitslag.inhoud,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{event_id}/verwijderen")
async def uitslag_verwijderen(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    uitslag = db.query(Uitslag).filter(Uitslag.evening_id == event_id).first()
    if not uitslag:
        raise HTTPException(status_code=404, detail="Uitslag niet gevonden")
    db.delete(uitslag)
    db.commit()
    return RedirectResponse(url="/uitslagen?verwijderd=1", status_code=302)


@router.get("/{event_id}/uploaden")
async def uitslag_upload_form(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    bestaande_uitslag = db.query(Uitslag).filter(Uitslag.evening_id == event_id).first()

    return templates.TemplateResponse(
        request,
        "uitslag_uploaden.html",
        {
            "current_user": current_user,
            "evening": evening,
            "bestaande_uitslag": bestaande_uitslag,
            "welkom": False,
        },
    )


@router.post("/{event_id}/uploaden")
async def uitslag_upload(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    form = await request.form()
    bestand = form.get("bestand")

    if not bestand or not bestand.filename:
        return RedirectResponse(
            url=f"/uitslagen/{event_id}/uploaden?fout=bestand", status_code=302
        )

    inhoud_bytes = await bestand.read()

    bestaande = db.query(Uitslag).filter(Uitslag.evening_id == event_id).first()
    if bestaande:
        bestaande.inhoud = inhoud_bytes
        bestaande.bestandsnaam = bestand.filename
        bestaande.aangemaakt_door_id = current_user.id
    else:
        db.add(Uitslag(
            evening_id=event_id,
            bestandsnaam=bestand.filename,
            inhoud=inhoud_bytes,
            aangemaakt_door_id=current_user.id,
        ))

    db.commit()
    return RedirectResponse(url="/uitslagen?upload_ok=1", status_code=302)
