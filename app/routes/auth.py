import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import (
    AccountRequest,
    AccountRequestStatus,
    EmailRoleAssignment,
    Invitation,
    Member,
    MemberRole,
    PasswordResetToken,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Login ──────────────────────────────────────────────────────────────────────

@router.get("/login")
async def login_form(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    login_method = form.get("login_method", "email")
    password = form.get("password", "")

    member = None
    email = ""

    if login_method == "naam":
        voornaam = form.get("voornaam", "").strip()
        achternaam = form.get("achternaam", "").strip()
        member = (
            db.query(Member)
            .filter(
                Member.voornaam.ilike(voornaam),
                Member.achternaam.ilike(achternaam),
            )
            .first()
        )
        if member:
            email = member.email or ""
    else:
        email = form.get("email", "").strip().lower()
        member = db.query(Member).filter(Member.email == email).first()

    if member and member.wachtwoord_hash and verify_password(password, member.wachtwoord_hash):
        request.session["user_id"] = member.id
        request.session["welkom"] = True
        return RedirectResponse(url="/", status_code=302)

    account_request = (
        db.query(AccountRequest)
        .filter(AccountRequest.email == email)
        .order_by(AccountRequest.aangemaakt_op.desc())
        .first()
    ) if email else None

    if account_request and account_request.status == AccountRequestStatus.wachtend:
        return templates.TemplateResponse(
            request, "login.html", {"login_status": "wachtend"}, status_code=401
        )
    if account_request and account_request.status == AccountRequestStatus.goedgekeurd:
        return templates.TemplateResponse(
            request, "login.html", {"login_status": "goedgekeurd"}, status_code=401
        )
    if account_request and account_request.status == AccountRequestStatus.afgewezen:
        return templates.TemplateResponse(
            request, "login.html", {"login_status": "afgewezen"}, status_code=401
        )

    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Onbekende naam/e-mailadres of onjuist wachtwoord."},
        status_code=401,
    )


# ── Public registration (no invite) ───────────────────────────────────────────

@router.get("/registreren")
async def registreren_form(request: Request):
    return templates.TemplateResponse(request, "registreren.html", {})


@router.post("/registreren")
async def registreren_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    voornaam = form.get("voornaam", "").strip()
    achternaam = form.get("achternaam", "").strip()
    email = form.get("email", "").strip().lower()
    lidnummer = form.get("lidnummer", "").strip()
    password = form.get("password", "")
    password2 = form.get("password2", "")

    errors = []
    if not voornaam:
        errors.append("Voornaam is verplicht.")
    if not achternaam:
        errors.append("Achternaam is verplicht.")
    if not email:
        errors.append("E-mailadres is verplicht.")
    if not lidnummer:
        errors.append("Lidnummer is verplicht.")
    if len(password) < 8:
        errors.append("Wachtwoord moet minimaal 8 tekens bevatten.")
    if password != password2:
        errors.append("Wachtwoorden komen niet overeen.")

    if not errors:
        if db.query(Member).filter(Member.email == email).first():
            errors.append("Er bestaat al een account met dit e-mailadres.")
        elif (
            db.query(AccountRequest)
            .filter(
                AccountRequest.email == email,
                AccountRequest.status != AccountRequestStatus.afgewezen,
            )
            .first()
        ):
            errors.append("Er loopt al een aanvraag voor dit e-mailadres.")

    if errors:
        return templates.TemplateResponse(
            request,
            "registreren.html",
            {
                "errors": errors,
                "voornaam": voornaam,
                "achternaam": achternaam,
                "email": email,
                "lidnummer": lidnummer,
            },
            status_code=422,
        )

    db.add(AccountRequest(
        voornaam=voornaam,
        achternaam=achternaam,
        email=email,
        lidnummer=lidnummer,
        wachtwoord_hash=hash_password(password),
    ))
    db.commit()
    return templates.TemplateResponse(request, "registreren.html", {"verzonden": True})


# ── Invitation-based registration ─────────────────────────────────────────────

@router.get("/invite/{token}")
async def accept_invitation(token: str, request: Request, db: Session = Depends(get_db)):
    invitation = (
        db.query(Invitation)
        .filter(Invitation.token == token, Invitation.gebruikt_op.is_(None))
        .first()
    )
    if not invitation:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Deze uitnodigingslink is al gebruikt of bestaat niet."},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "register.html",
        {"invitation": invitation, "token": token},
    )


@router.post("/invite/{token}")
async def register_submit(token: str, request: Request, db: Session = Depends(get_db)):
    invitation = (
        db.query(Invitation)
        .filter(Invitation.token == token, Invitation.gebruikt_op.is_(None))
        .first()
    )
    if not invitation:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Deze uitnodigingslink is al gebruikt of bestaat niet."},
            status_code=404,
        )

    form = await request.form()
    password = form.get("password", "")
    password2 = form.get("password2", "")

    account_request = invitation.account_request
    if account_request:
        voornaam = account_request.voornaam
        achternaam = account_request.achternaam
        lidnummer = account_request.lidnummer
    else:
        voornaam = form.get("voornaam", "").strip()
        achternaam = form.get("achternaam", "").strip()
        lidnummer = None

    errors = []
    if not account_request:
        if not voornaam:
            errors.append("Voornaam is verplicht.")
        if not achternaam:
            errors.append("Achternaam is verplicht.")
    if len(password) < 8:
        errors.append("Wachtwoord moet minimaal 8 tekens bevatten.")
    if password != password2:
        errors.append("Wachtwoorden komen niet overeen.")

    email = invitation.email.lower().strip()
    if db.query(Member).filter(Member.email == email).first():
        errors.append("Er bestaat al een account met dit e-mailadres.")

    if errors:
        return templates.TemplateResponse(
            request,
            "register.html",
            {
                "invitation": invitation,
                "token": token,
                "errors": errors,
                "voornaam": voornaam,
                "achternaam": achternaam,
            },
            status_code=422,
        )

    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == email).first()
    role = assignment.role if assignment else MemberRole.lid

    member = Member(
        voornaam=voornaam,
        achternaam=achternaam,
        lidnummer=lidnummer or f"lid_{secrets.token_hex(4)}",
        email=email,
        wachtwoord_hash=hash_password(password),
        role=role,
    )
    db.add(member)
    db.flush()

    invitation.gebruikt_op = datetime.now(timezone.utc)
    invitation.member_id = member.id
    db.commit()
    db.refresh(member)

    request.session["user_id"] = member.id
    request.session["welkom"] = True
    return RedirectResponse(url="/", status_code=302)


# ── Wachtwoord vergeten ────────────────────────────────────────────────────────

@router.get("/wachtwoord-vergeten")
async def wachtwoord_vergeten_form(request: Request):
    return templates.TemplateResponse(request, "wachtwoord_vergeten.html", {})


@router.post("/wachtwoord-vergeten")
async def wachtwoord_vergeten_submit(request: Request, db: Session = Depends(get_db)):
    from app.email import send_password_reset_email

    form = await request.form()
    email = form.get("email", "").strip().lower()

    member = db.query(Member).filter(Member.email == email).first() if email else None
    if member and member.wachtwoord_hash:
        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(token=token, member_id=member.id))
        db.commit()
        base_url = str(request.base_url).rstrip("/")
        reset_url = f"{base_url}/wachtwoord-reset/{token}"
        try:
            send_password_reset_email(member.email, member.voornaam, reset_url)
        except Exception:
            pass  # stille fout — toon altijd de bevestigingspagina

    return templates.TemplateResponse(
        request, "wachtwoord_vergeten.html", {"verzonden": True}
    )


@router.get("/wachtwoord-reset/{token}")
async def wachtwoord_reset_form(token: str, request: Request, db: Session = Depends(get_db)):
    reset_token = _get_valid_reset_token(token, db)
    if not reset_token:
        return templates.TemplateResponse(
            request, "wachtwoord_vergeten.html",
            {"error": "Deze resetlink is verlopen of ongeldig."},
            status_code=400,
        )
    return templates.TemplateResponse(request, "wachtwoord_reset.html", {"token": token})


@router.post("/wachtwoord-reset/{token}")
async def wachtwoord_reset_submit(token: str, request: Request, db: Session = Depends(get_db)):
    reset_token = _get_valid_reset_token(token, db)
    if not reset_token:
        return templates.TemplateResponse(
            request, "wachtwoord_vergeten.html",
            {"error": "Deze resetlink is verlopen of ongeldig."},
            status_code=400,
        )

    form = await request.form()
    password = form.get("password", "")
    password2 = form.get("password2", "")

    errors = []
    if len(password) < 8:
        errors.append("Wachtwoord moet minimaal 8 tekens bevatten.")
    if password != password2:
        errors.append("Wachtwoorden komen niet overeen.")

    if errors:
        return templates.TemplateResponse(
            request, "wachtwoord_reset.html",
            {"token": token, "errors": errors},
            status_code=422,
        )

    reset_token.member.wachtwoord_hash = hash_password(password)
    reset_token.gebruikt_op = datetime.now(timezone.utc)
    db.commit()

    return templates.TemplateResponse(request, "wachtwoord_reset.html", {"gelukt": True})


def _get_valid_reset_token(token: str, db: Session):
    reset_token = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == token,
            PasswordResetToken.gebruikt_op.is_(None),
        )
        .first()
    )
    if not reset_token:
        return None
    geldig_tot = reset_token.aangemaakt_op.replace(tzinfo=timezone.utc) + timedelta(hours=1)
    if datetime.now(timezone.utc) > geldig_tot:
        return None
    return reset_token


# ── Logout & misc ──────────────────────────────────────────────────────────────

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


@router.get("/privacy")
async def privacy(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(
        request, "privacy.html", {"current_user": current_user}
    )
