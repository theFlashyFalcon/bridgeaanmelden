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
    RecurringRegistration,
    Registration,
    RegistrationStatus,
    RegistrationType,
    Season,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Per-evenement aanmelden ───────────────────────────────────────────────────

_TRAINING_TYPES = {EveningType.jeugdtraining, EveningType.jeugdtraining.value,
                   "eten voor jeugdtraining", EveningType.eten_voor_jeugdtraining}


def _is_training(evening: ClubEvening) -> bool:
    return evening.type in _TRAINING_TYPES


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

    if _is_training(evening) and not current_user.training_eligible:
        return templates.TemplateResponse(
            request,
            "registrations/start.html",
            {
                "current_user": current_user,
                "evening": evening,
                "existing": None,
                "pending_request": None,
                "training_niet_toegestaan": True,
            },
        )

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

    if _is_training(evening) and not current_user.training_eligible:
        raise HTTPException(status_code=403, detail="Geen toegang tot trainingsavonden")

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
        return RedirectResponse(url="/?afgemeld=1", status_code=302)

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

    herhalingen = (
        db.query(RecurringRegistration)
        .filter(
            RecurringRegistration.member_id == current_user.id,
            RecurringRegistration.actief == True,  # noqa: E712
        )
        .order_by(RecurringRegistration.aangemaakt_op)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "registrations/instellingen.html",
        {
            "current_user": current_user,
            "upcoming_clubavonden": upcoming_clubavonden,
            "herhalingen": herhalingen,
        },
    )


@router.post("/instellingen/herhaal/{herhaal_id}/stop")
async def herhaal_stop(
    herhaal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    rr = (
        db.query(RecurringRegistration)
        .filter(
            RecurringRegistration.id == herhaal_id,
            RecurringRegistration.member_id == current_user.id,
        )
        .first()
    )
    if rr:
        rr.actief = False
        db.commit()
    return RedirectResponse(url="/instellingen?herhaal_gestopt=1", status_code=302)


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


# ── Herhaal-aanmelding ────────────────────────────────────────────────────────

@router.post("/aanmelden/{event_id}/herhaal")
async def registration_herhaal(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_auth),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404)

    form = await request.form()
    alles = form.get("alles") == "on"
    alles_tot_str = form.get("alles_tot", "").strip()
    elke_str = form.get("elke", "").strip()
    herhaal_tot_str = form.get("herhaal_tot", "").strip()
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

    def _register_for_events(events):
        count = 0
        for evt in events:
            existing = (
                db.query(Registration)
                .filter(
                    Registration.evening_id == evt.id,
                    Registration.person1_id == current_user.id,
                    Registration.status != RegistrationStatus.afgemeld,
                )
                .first()
            )
            if not existing:
                status = RegistrationStatus.aangemeld if partner_naam else RegistrationStatus.beschikbaar_solo
                db.add(Registration(
                    evening_id=evt.id,
                    person1_id=current_user.id,
                    partner_naam=partner_naam,
                    type=RegistrationType.vast,
                    status=status,
                ))
                count += 1
        return count

    if alles:
        alles_tot = date.fromisoformat(alles_tot_str) if alles_tot_str else None

        query = (
            db.query(ClubEvening)
            .join(Season)
            .filter(
                ClubEvening.type == evening.type,
                ClubEvening.datum >= today,
                Season.actief == True,  # noqa: E712
            )
        )
        if alles_tot:
            query = query.filter(ClubEvening.datum <= alles_tot)

        future_events = query.order_by(ClubEvening.datum).all()
        count = _register_for_events(future_events)

        # Without end date: store recurring registration for auto-apply on new events
        if not alles_tot:
            db.query(RecurringRegistration).filter(
                RecurringRegistration.member_id == current_user.id,
                RecurringRegistration.event_type == evening.type,
                RecurringRegistration.actief == True,  # noqa: E712
            ).update({"actief": False})
            db.add(RecurringRegistration(
                member_id=current_user.id,
                event_type=evening.type,
                partner_naam=partner_naam,
                interval=1,
                herhaal_tot=None,
                referentie_datum=today,
            ))

        db.commit()
        return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)

    elif elke_str:
        try:
            elke = max(1, int(elke_str))
        except ValueError:
            elke = 1

        herhaal_tot = date.fromisoformat(herhaal_tot_str) if herhaal_tot_str else None

        query = (
            db.query(ClubEvening)
            .join(Season)
            .filter(
                ClubEvening.type == evening.type,
                ClubEvening.datum >= today,
                Season.actief == True,  # noqa: E712
            )
        )
        if herhaal_tot:
            query = query.filter(ClubEvening.datum <= herhaal_tot)

        future_events = query.order_by(ClubEvening.datum).all()
        selected = [evt for i, evt in enumerate(future_events) if i % elke == 0]
        count = _register_for_events(selected)

        db.commit()
        return RedirectResponse(url=f"/?bulk_ok={count}", status_code=302)

    return RedirectResponse(url=f"/aanmelden/{event_id}", status_code=302)


# ── Wijzigen (redirect) ───────────────────────────────────────────────────────

@router.get("/aanmelden/wijzigen")
async def wijzigen_redirect(request: Request):
    return RedirectResponse(url="/", status_code=302)
