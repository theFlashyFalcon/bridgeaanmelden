from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_auth
from app.database import get_db
from app.models import (
    ClubEvening,
    ManualPair,
    Member,
    Registration,
    RegistrationStatus,
    Season,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/")
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[Member] = Depends(get_current_user),
):
    today = date.today()

    evenings = (
        db.query(ClubEvening)
        .join(Season)
        .filter(Season.actief == True, ClubEvening.datum >= today)  # noqa: E712
        .order_by(ClubEvening.datum)
        .limit(30)
        .all()
    )

    user_regs: dict[int, Registration] = {}
    if current_user:
        evening_ids = [e.id for e in evenings]
        regs1 = (
            db.query(Registration)
            .filter(
                Registration.person1_id == current_user.id,
                Registration.evening_id.in_(evening_ids),
                Registration.status != RegistrationStatus.afgemeld,
            )
            .all()
        )
        regs2 = (
            db.query(Registration)
            .filter(
                Registration.person2_id == current_user.id,
                Registration.evening_id.in_(evening_ids),
                Registration.status != RegistrationStatus.afgemeld,
            )
            .all()
        )
        for reg in regs1 + regs2:
            user_regs[reg.evening_id] = reg

    welkom = request.session.pop("welkom", False)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "current_user": current_user,
            "evenings": evenings,
            "user_regs": user_regs,
            "welkom": welkom,
        },
    )


@router.get("/offline")
async def offline(request: Request):
    return templates.TemplateResponse(request, "offline.html", {})


@router.get("/deelnemers/{event_id}")
async def deelnemers(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    registrations = (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.status != RegistrationStatus.afgemeld,
        )
        .all()
    )

    manual_pairs = (
        db.query(ManualPair)
        .filter(ManualPair.evening_id == event_id)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "deelnemers.html",
        {
            "current_user": current_user,
            "evening": evening,
            "registrations": registrations,
            "manual_pairs": manual_pairs,
        },
    )
