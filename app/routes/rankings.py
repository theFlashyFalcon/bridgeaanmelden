import csv
import io
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_wedstrijdleider
from app.database import get_db
from app.models import Ranking

router = APIRouter(prefix="/ranking")
from app.templates_env import templates


def _parse_csv(inhoud: str) -> tuple[list[str], list[list[str]]]:
    inhoud = inhoud.replace('\r\n', '\n').replace('\r', '\n')
    reader = csv.reader(io.StringIO(inhoud))
    rows = list(reader)
    if not rows:
        return [], []
    headers = rows[0]
    data = rows[1:]
    return headers, data


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
    kan_uploaden = display_role in ("wedstrijdleider", "admin")

    laatste = db.query(Ranking).order_by(Ranking.aangemaakt_op.desc()).first()
    headers, rijen = [], []
    if laatste:
        headers, rijen = _parse_csv(laatste.inhoud)

    return templates.TemplateResponse(
        request,
        "ranking.html",
        {
            "current_user": current_user,
            "display_role": display_role,
            "kan_uploaden": kan_uploaden,
            "ranking": laatste,
            "headers": headers,
            "rijen": rijen,
            "welkom": False,
        },
    )


@router.get("/uploaden")
async def ranking_upload_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_wedstrijdleider),
):
    return templates.TemplateResponse(
        request,
        "ranking_uploaden.html",
        {"current_user": current_user, "welkom": False},
    )


@router.post("/uploaden")
async def ranking_upload(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_wedstrijdleider),
):
    form = await request.form()
    bestand = form.get("bestand")

    if not bestand or not bestand.filename:
        return RedirectResponse(url="/ranking/uploaden?fout=bestand", status_code=302)

    inhoud_bytes = await bestand.read()
    try:
        inhoud = inhoud_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        inhoud = inhoud_bytes.decode("latin-1")

    ranking = Ranking(
        inhoud=inhoud,
        bestandsnaam=bestand.filename,
        aangemaakt_door_id=current_user.id,
    )
    db.add(ranking)
    db.commit()

    return RedirectResponse(url="/ranking?upload_ok=1", status_code=302)
