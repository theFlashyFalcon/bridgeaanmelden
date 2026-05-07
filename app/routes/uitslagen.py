from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_auth, require_wedstrijdleider
from app.database import get_db
from app.models import ClubEvening, Member, Uitslag

router = APIRouter(prefix="/uitslagen")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Evenement-typen die niet in uitslagen worden getoond
EXCLUDED_TYPES = ["jeugdtraining", "training", "eten voor jeugdtraining"]


def _get_display_role(request: Request, current_user) -> str:
    if current_user.role == "admin":
        view_as = request.session.get("view_as_role")
        return view_as if view_as else current_user.role
    return current_user.role


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

    query = db.query(ClubEvening).filter(
        ClubEvening.datum < today,
        ClubEvening.type.notin_(EXCLUDED_TYPES),
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
    today = date.today()
    evenings = (
        db.query(ClubEvening)
        .filter(ClubEvening.datum < today, ClubEvening.type.notin_(EXCLUDED_TYPES))
        .order_by(ClubEvening.datum.desc())
        .all()
    )
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

    filename = uitslag.bestandsnaam or "uitslag.pdf"
    return Response(
        content=uitslag.inhoud,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
