import secrets
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin, require_wedstrijdleider
from app.database import get_db
from app.models import (
    AccountRequest,
    AccountRequestStatus,
    ClubEvening,
    EmailRoleAssignment,
    EveningType,
    Invitation,
    Member,
    MemberRole,
    Registration,
    RegistrationStatus,
    Season,
)

router = APIRouter(prefix="/beheer")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

EVENING_TYPES = [
    ("clubavond", "Clubavond"),
    ("jeugdtraining", "Jeugdtraining"),
    ("eten voor jeugdtraining", "Eten voor jeugdtraining"),
    ("speciaal", "Speciaal"),
]


# ── Avonden (Wedstrijdleider + Admin) ─────────────────────────────────────────

@router.get("/avonden")
async def avonden_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    seasons = db.query(Season).order_by(Season.start_datum.desc()).all()
    evenings = (
        db.query(ClubEvening)
        .join(Season)
        .order_by(ClubEvening.datum)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/avonden.html",
        {
            "current_user": current_user,
            "evenings": evenings,
            "seasons": seasons,
        },
    )


@router.post("/avonden/seizoen")
async def seizoen_add_from_beheren(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    start_str = form.get("start_datum", "")
    eind_str = form.get("eind_datum", "")

    errors = []
    if not naam:
        errors.append("Naam is verplicht.")
    if not start_str or not eind_str:
        errors.append("Start- en einddatum zijn verplicht.")

    if errors:
        return RedirectResponse(url="/beheer/avonden?fout=seizoen", status_code=302)

    start = date.fromisoformat(start_str)
    eind = date.fromisoformat(eind_str)
    if start >= eind:
        return RedirectResponse(url="/beheer/avonden?fout=datum", status_code=302)

    db.add(Season(naam=naam, start_datum=start, eind_datum=eind, actief=False))
    db.commit()
    return RedirectResponse(url="/beheer/avonden?seizoen_aangemaakt=1", status_code=302)


@router.post("/avonden")
async def avonden_add(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    datum_str = form.get("datum", "")
    type_ = form.get("type", "clubavond")

    errors = []
    if not naam:
        errors.append("Naam is verplicht.")
    if not datum_str:
        errors.append("Datum is verplicht.")

    datum = date.fromisoformat(datum_str) if datum_str else None

    season = None
    if datum:
        season = (
            db.query(Season)
            .filter(Season.start_datum <= datum, Season.eind_datum >= datum)
            .first()
        )
        if not season:
            errors.append(f"Geen seizoen gevonden voor {datum_str}. Maak eerst een seizoen aan dat deze datum omvat.")

    if errors:
        seasons = db.query(Season).order_by(Season.start_datum.desc()).all()
        evenings = db.query(ClubEvening).join(Season).order_by(ClubEvening.datum).all()
        return templates.TemplateResponse(
            request,
            "admin/avonden.html",
            {
                "current_user": current_user,
                "evenings": evenings,
                "seasons": seasons,
                "errors": errors,
                "open_type": type_,
            },
            status_code=422,
        )

    db.add(ClubEvening(naam=naam, datum=datum, type=type_, season_id=season.id))
    db.commit()
    return RedirectResponse(url="/beheer/avonden?aangemaakt=1", status_code=302)


@router.post("/avonden/{event_id}/verwijder")
async def avonden_delete(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if evening:
        db.delete(evening)
        db.commit()
    return RedirectResponse(url="/beheer/avonden?verwijderd=1", status_code=302)


# ── Aanmeldingenoverzicht (Wedstrijdleider + Admin) ───────────────────────────

@router.get("/aanmeldingen")
async def aanmeldingen_overview(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evenings = (
        db.query(ClubEvening)
        .join(Season)
        .filter(Season.actief == True, ClubEvening.datum >= date.today())  # noqa: E712
        .order_by(ClubEvening.datum)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/aanmeldingen.html",
        {"current_user": current_user, "evenings": evenings},
    )


@router.get("/aanmeldingen/{event_id}")
async def aanmeldingen_detail(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    evening = db.query(ClubEvening).filter(ClubEvening.id == event_id).first()
    if not evening:
        raise HTTPException(status_code=404)

    all_regs = (
        db.query(Registration)
        .filter(Registration.evening_id == event_id)
        .order_by(Registration.gewijzigd_op.desc())
        .all()
    )

    active = [r for r in all_regs if r.status != RegistrationStatus.afgemeld]
    recent_changes = all_regs[:10]

    loslopers = [
        r for r in active
        if r.person2_id is None or r.status == RegistrationStatus.beschikbaar_solo
    ]

    return templates.TemplateResponse(
        request,
        "admin/event_detail.html",
        {
            "current_user": current_user,
            "evening": evening,
            "active": active,
            "recent_changes": recent_changes,
            "loslopers": loslopers,
        },
    )


# ── Loslopers (Wedstrijdleider + Admin) ───────────────────────────────────────

@router.get("/loslopers")
async def loslopers(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_wedstrijdleider),
):
    solo = (
        db.query(Registration)
        .filter(Registration.status == RegistrationStatus.beschikbaar_solo)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/loslopers.html",
        {"current_user": current_user, "solo_registrations": solo},
    )


# ── Seizoenen (Admin only) ────────────────────────────────────────────────────

@router.get("/seizoenen")
async def seizoenen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    seasons = db.query(Season).order_by(Season.start_datum.desc()).all()
    return templates.TemplateResponse(
        request,
        "admin/seizoenen.html",
        {"current_user": current_user, "seasons": seasons},
    )


@router.post("/seizoenen")
async def seizoen_add(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    naam = form.get("naam", "").strip()
    start = form.get("start_datum", "")
    eind = form.get("eind_datum", "")
    actief = form.get("actief") == "on"

    if naam and start and eind:
        if actief:
            db.query(Season).update({"actief": False})
        db.add(Season(
            naam=naam,
            start_datum=date.fromisoformat(start),
            eind_datum=date.fromisoformat(eind),
            actief=actief,
        ))
        db.commit()
    return RedirectResponse(url="/beheer/seizoenen?aangemaakt=1", status_code=302)


@router.post("/seizoenen/{season_id}/activeer")
async def seizoen_activeer(
    season_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    db.query(Season).update({"actief": False})
    season = db.query(Season).filter(Season.id == season_id).first()
    if season:
        season.actief = True
    db.commit()
    return RedirectResponse(url="/beheer/seizoenen", status_code=302)


# ── Uitnodigingen (Admin only) ────────────────────────────────────────────────

@router.get("/uitnodigingen")
async def uitnodigingen(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    invitations = db.query(Invitation).order_by(Invitation.aangemaakt_op.desc()).all()
    return templates.TemplateResponse(
        request,
        "admin/uitnodigingen.html",
        {
            "current_user": current_user,
            "invitations": invitations,
            "roles": [r.value for r in MemberRole],
        },
    )


@router.post("/uitnodigingen")
async def create_invitation(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    from app.email import send_invitation_email

    form = await request.form()
    email = form.get("email", "").strip().lower()
    role = form.get("role", MemberRole.lid)

    if not email:
        return RedirectResponse(url="/beheer/uitnodigingen?error=email_required", status_code=302)

    # Set role assignment
    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == email).first()
    if assignment:
        assignment.role = role
    else:
        db.add(EmailRoleAssignment(email=email, role=role))

    token = secrets.token_urlsafe(32)
    invitation = Invitation(token=token, email=email)
    db.add(invitation)
    db.commit()

    base = str(request.base_url).rstrip("/")
    invite_url = f"{base}/invite/{token}"
    try:
        send_invitation_email(email, invite_url)
        return RedirectResponse(url="/beheer/uitnodigingen?verstuurd=1", status_code=302)
    except Exception:
        return RedirectResponse(
            url=f"/beheer/uitnodigingen?aangemaakt=1&email_fout=1&token={token}",
            status_code=302,
        )


# ── Accountaanvragen (Admin only) ────────────────────────────────────────────

@router.get("/aanvragen")
async def aanvragen_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    aanvragen = (
        db.query(AccountRequest)
        .order_by(AccountRequest.aangemaakt_op.desc())
        .all()
    )
    pending_count = sum(1 for a in aanvragen if a.status == AccountRequestStatus.wachtend)
    return templates.TemplateResponse(
        request,
        "admin/aanvragen.html",
        {
            "current_user": current_user,
            "aanvragen": aanvragen,
            "pending_count": pending_count,
            "roles": [r.value for r in MemberRole],
        },
    )


@router.post("/aanvragen/{aanvraag_id}/goedkeuren")
async def aanvraag_goedkeuren(
    aanvraag_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    from app.email import send_approval_email, send_invitation_email

    form = await request.form()
    role = form.get("role", MemberRole.lid)

    aanvraag = db.query(AccountRequest).filter(AccountRequest.id == aanvraag_id).first()
    if not aanvraag or aanvraag.status != AccountRequestStatus.wachtend:
        return RedirectResponse(url="/beheer/aanvragen", status_code=302)

    aanvraag.status = AccountRequestStatus.goedgekeurd
    aanvraag.beoordeeld_op = datetime.now(timezone.utc)

    if aanvraag.wachtwoord_hash:
        # User provided a password during registration — create member directly
        member = Member(
            voornaam=aanvraag.voornaam,
            achternaam=aanvraag.achternaam,
            lidnummer=aanvraag.lidnummer,
            email=aanvraag.email,
            wachtwoord_hash=aanvraag.wachtwoord_hash,
            role=role,
        )
        db.add(member)
        db.commit()
        try:
            send_approval_email(aanvraag.email, aanvraag.voornaam)
            return RedirectResponse(url="/beheer/aanvragen?goedgekeurd=1", status_code=302)
        except Exception:
            return RedirectResponse(url="/beheer/aanvragen?goedgekeurd=1&email_fout=1", status_code=302)
    else:
        # Legacy: send invite link
        assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == aanvraag.email).first()
        if assignment:
            assignment.role = role
        else:
            db.add(EmailRoleAssignment(email=aanvraag.email, role=role))

        token = secrets.token_urlsafe(32)
        db.add(Invitation(token=token, email=aanvraag.email, account_request_id=aanvraag.id))
        db.commit()

        base = str(request.base_url).rstrip("/")
        invite_url = f"{base}/invite/{token}"
        try:
            send_invitation_email(aanvraag.email, invite_url)
            return RedirectResponse(url="/beheer/aanvragen?goedgekeurd=1", status_code=302)
        except Exception:
            return RedirectResponse(
                url=f"/beheer/aanvragen?goedgekeurd=1&email_fout=1&token={token}",
                status_code=302,
            )


@router.post("/aanvragen/{aanvraag_id}/afwijzen")
async def aanvraag_afwijzen(
    aanvraag_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    aanvraag = db.query(AccountRequest).filter(AccountRequest.id == aanvraag_id).first()
    if aanvraag and aanvraag.status == AccountRequestStatus.wachtend:
        aanvraag.status = AccountRequestStatus.afgewezen
        aanvraag.beoordeeld_op = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url="/beheer/aanvragen?afgewezen=1", status_code=302)


# ── Roltoewijzingen (Admin only) ──────────────────────────────────────────────

@router.get("/rollen")
async def rollen_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    assignments = db.query(EmailRoleAssignment).order_by(EmailRoleAssignment.email).all()
    return templates.TemplateResponse(
        request,
        "admin/rollen.html",
        {
            "current_user": current_user,
            "assignments": assignments,
            "roles": [r.value for r in MemberRole],
        },
    )


@router.post("/rollen")
async def upsert_role(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    email = form.get("email", "").strip().lower()
    role = form.get("role", "").strip()

    if not email or role not in [r.value for r in MemberRole]:
        return RedirectResponse(url="/beheer/rollen?error=1", status_code=302)

    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == email).first()
    if assignment:
        assignment.role = role
    else:
        db.add(EmailRoleAssignment(email=email, role=role))

    member = db.query(Member).filter(Member.email == email).first()
    if member:
        member.role = role

    db.commit()
    return RedirectResponse(url="/beheer/rollen?opgeslagen=1", status_code=302)


@router.post("/rollen/verwijder")
async def delete_role(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Member = Depends(require_admin),
):
    form = await request.form()
    assignment_id = form.get("id")
    if assignment_id:
        db.query(EmailRoleAssignment).filter(EmailRoleAssignment.id == int(assignment_id)).delete()
        db.commit()
    return RedirectResponse(url="/beheer/rollen", status_code=302)
