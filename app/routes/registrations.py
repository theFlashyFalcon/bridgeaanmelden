from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_auth
from app.database import get_db
from app.models import (
    ClubEvening,
    EveningType,
    Lid,
    Member,
    PartnerRequest,
    Registration,
    RegistrationStatus,
    RegistrationType,
    Season,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


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
            Registration.status != RegistrationStatus.afgemeld,
        )
        .first()
    )

    pending_request = (
        db.query(PartnerRequest)
        .filter(
            PartnerRequest.evening_id == event_id,
            PartnerRequest.requester_id == current_user.id,
            PartnerRequest.status == "wachtend",
        )
        .first()
    )

    return templates.TemplateResponse(
        request,
        "registrations/start.html",
        {
            "current_user": current_user,
            "evening": evening,
            "existing": existing,
            "pending_request": pending_request,
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
    partner_voornaam = form.get("partner_voornaam", "").strip()
    partner_achternaam = form.get("partner_achternaam", "").strip()

    existing = (
        db.query(Registration)
        .filter(
            Registration.evening_id == event_id,
            Registration.person1_id == current_user.id,
            Registration.status != RegistrationStatus.afgemeld,
        )
        .first()
    )

    if action == "afmelden":
        if existing:
            existing.status = RegistrationStatus.afgemeld
            existing.partner_naam = None
            db.commit()
        # Also cancel pending partner request
        db.query(PartnerRequest).filter(
            PartnerRequest.evening_id == event_id,
            PartnerRequest.requester_id == current_user.id,
            PartnerRequest.status == "wachtend",
        ).delete()
        db.commit()
        return RedirectResponse(url="/", status_code=302)

    # Determine partner name and status
    if partner_voornaam and partner_achternaam:
        partner_naam = f"{partner_voornaam} {partner_achternaam}"

        lid = (
            db.query(Lid)
            .filter(
                func.lower(Lid.voornaam) == partner_voornaam.lower(),
                func.lower(Lid.achternaam) == partner_achternaam.lower(),
            )
            .first()
        )

        if lid:
            # Partner found in leden DB → direct registration
            if existing:
                existing.status = RegistrationStatus.aangemeld
                existing.partner_naam = partner_naam
            else:
                db.add(Registration(
                    evening_id=event_id,
                    person1_id=current_user.id,
                    partner_naam=partner_naam,
                    type=RegistrationType.los,
                    status=RegistrationStatus.aangemeld,
                ))
            db.commit()
            return RedirectResponse(url="/?bevestigd=1", status_code=302)
        else:
            # Partner not in leden DB → create partner request
            # Remove existing pending request first
            db.query(PartnerRequest).filter(
                PartnerRequest.evening_id == event_id,
                PartnerRequest.requester_id == current_user.id,
                PartnerRequest.status == "wachtend",
            ).delete()
            db.add(PartnerRequest(
                evening_id=event_id,
                requester_id=current_user.id,
                partner_voornaam=partner_voornaam,
                partner_achternaam=partner_achternaam,
            ))
            db.commit()
            return RedirectResponse(url="/?verzoek_ingediend=1", status_code=302)
    else:
        # Solo registration
        reg_status = RegistrationStatus.beschikbaar_solo
        if existing:
            existing.status = reg_status
            existing.partner_naam = None
        else:
            db.add(Registration(
                evening_id=event_id,
                person1_id=current_user.id,
                partner_naam=None,
                type=RegistrationType.los,
                status=reg_status,
            ))
        db.commit()
        return RedirectResponse(url="/?bevestigd=1", status_code=302)


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

    return templates.TemplateResponse(
        request,
        "registrations/instellingen.html",
        {
            "current_user": current_user,
            "upcoming_clubavonden": upcoming_clubavonden,
        },
    )


@router.post("/instellingen")
async def instellingen_submit(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    form = await request.form()
    partner_voornaam = form.get("partner_voornaam", "").strip()
    partner_achternaam = form.get("partner_achternaam", "").strip()

    partner_naam = None
    if partner_voornaam and partner_achternaam:
        lid = (
            db.query(Lid)
            .filter(
                func.lower(Lid.voornaam) == partner_voornaam.lower(),
                func.lower(Lid.achternaam) == partner_achternaam.lower(),
            )
            .first()
        )
        if lid:
            partner_naam = f"{partner_voornaam} {partner_achternaam}"

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
            status = RegistrationStatus.aangemeld if partner_naam else RegistrationStatus.beschikbaar_solo
            db.add(Registration(
                evening_id=evening.id,
                person1_id=current_user.id,
                partner_naam=partner_naam,
                type=RegistrationType.vast,
                status=status,
            ))
            count += 1

    db.commit()
    return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)


# ── Wijzigen (redirect) ───────────────────────────────────────────────────────

@router.get("/aanmelden/wijzigen")
async def wijzigen_redirect(request: Request):
    return RedirectResponse(url="/", status_code=302)
