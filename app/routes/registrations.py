from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_auth
from app.database import get_db
from app.models import (
    ClubEvening,
    EveningType,
    Member,
    Registration,
    RegistrationStatus,
    RegistrationType,
    Season,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _get_partner(current_user: Member, reg: Registration) -> Member | None:
    if reg.person1_id == current_user.id:
        return reg.person2
    return reg.person1


# ── Per-evenement aanmelden ───────────────────────────────────────────────────

@router.get("/aanmelden/{event_id}")
async def registration_form(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404, detail="Evenement niet gevonden")

    existing = (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.person1_id == current_user.id,
        )
        .first()
    ) or (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.person2_id == current_user.id,
        )
        .first()
    )

    members = (
        db.query(Member)
        .filter(Member.id != current_user.id)
        .order_by(Member.achternaam, Member.voornaam)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "registrations/start.html",
        {
            "current_user": current_user,
            "evening": evening,
            "existing": existing,
            "members": members,
        },
    )


@router.post("/aanmelden/{event_id}")
async def registration_submit(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404)

    form = await request.form()
    action = form.get("action", "aanmelden")
    partner_id_str = form.get("partner_id", "")
    partner_id = int(partner_id_str) if partner_id_str else None

    existing = (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.person1_id == current_user.id,
        )
        .first()
    )

    if action == "afmelden":
        if existing:
            existing.status = RegistrationStatus.afgemeld
            existing.person2_id = None
            db.commit()
        return RedirectResponse(url="/", status_code=302)

    if existing:
        existing.status = RegistrationStatus.aangemeld
        existing.person2_id = partner_id
    else:
        db.add(Registration(
            evening_id=event_id,
            person1_id=current_user.id,
            person2_id=partner_id,
            type=RegistrationType.los,
            status=RegistrationStatus.aangemeld,
        ))

    db.commit()
    return RedirectResponse(url="/", status_code=302)


# ── Instellingen / bulk aanmelden ─────────────────────────────────────────────

@router.get("/instellingen")
async def instellingen_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    today = date.today()
    upcoming_clubavonden = (
        db.query(ClubEvening)
        .join(Season)
        .filter(
            ClubEvening.datum >= today,
            ClubEvening.type.in_([EveningType.clubavond, "regulier"]),
            Season.actief == True,  # noqa: E712
        )
        .order_by(ClubEvening.datum)
        .all()
    )

    members = (
        db.query(Member)
        .filter(Member.id != current_user.id)
        .order_by(Member.achternaam, Member.voornaam)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "registrations/instellingen.html",
        {
            "current_user": current_user,
            "upcoming_clubavonden": upcoming_clubavonden,
            "members": members,
        },
    )


@router.post("/instellingen")
async def instellingen_submit(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    form = await request.form()
    partner_id_str = form.get("partner_id", "")
    partner_id = int(partner_id_str) if partner_id_str else None

    today = date.today()
    upcoming_clubavonden = (
        db.query(ClubEvening)
        .join(Season)
        .filter(
            ClubEvening.datum >= today,
            ClubEvening.type.in_([EveningType.clubavond, "regulier"]),
            Season.actief == True,  # noqa: E712
        )
        .all()
    )

    count = 0
    for evening in upcoming_clubavonden:
        existing = (
            db.query(Registration)
            .filter(
                Registration.evening_id == evening.id,
                Registration.person1_id == current_user.id,
                Registration.status != RegistrationStatus.afgemeld,
            )
            .first()
        )
        if not existing:
            db.add(Registration(
                evening_id=evening.id,
                person1_id=current_user.id,
                person2_id=partner_id,
                type=RegistrationType.vast,
                status=RegistrationStatus.aangemeld,
            ))
            count += 1

    db.commit()
    return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)


# ── Wijzigen (redirect) ───────────────────────────────────────────────────────

@router.get("/aanmelden/wijzigen")
async def wijzigen_redirect(request: Request):
    return RedirectResponse(url="/", status_code=302)
