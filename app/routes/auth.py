import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app import ratelimit
from app.auth import get_current_user, hash_password, needs_rehash, verify_password
from app.database import get_db
from app.models import (
    AccountRequest,
    AccountRequestStatus,
    Club,
    EmailRoleAssignment,
    Invitation,
    Lid,
    Member,
    MemberClub,
    MemberRole,
    PasswordResetToken,
)

router = APIRouter()
from app.templates_env import templates


def _koppel_aan_club(member: Member, db: Session, club_id: int | None = None) -> None:
    """Maak een MemberClub record aan als die nog niet bestaat."""
    if club_id is None:
        club = db.query(Club).first()
        if club is None:
            return
        club_id = club.id
    exists = db.query(MemberClub).filter(
        MemberClub.member_id == member.id,
        MemberClub.club_id == club_id,
    ).first()
    if not exists:
        db.add(MemberClub(member_id=member.id, club_id=club_id, role=member.role))


# ── Login ──────────────────────────────────────────────────────────────────────

def _veilige_next_url(raw: str) -> str:
    """Alleen relatieve paden toestaan (geen open redirect)."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/"


def _escape_like(waarde: str) -> str:
    """Escape LIKE/ILIKE-wildcards in gebruikersinvoer."""
    return waarde.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


@router.get("/login")
async def login_form(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user:
        return RedirectResponse(url="/", status_code=302)
    next_url = request.query_params.get("next", "")
    return templates.TemplateResponse(request, "login.html", {"next": next_url})


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    rate_key = f"login:{ratelimit.client_key(request)}"
    if ratelimit.is_limited(rate_key):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Te veel inlogpogingen. Probeer het over 5 minuten opnieuw."},
            status_code=429,
        )

    form = await request.form()
    login_method = form.get("login_method", "nbb")
    password = form.get("password", "")
    next_url = _veilige_next_url(form.get("next", "").strip())

    member = None
    email = ""

    if login_method == "naam":
        voornaam = form.get("voornaam", "").strip()
        achternaam = form.get("achternaam", "").strip()
        matches = (
            db.query(Member)
            .filter(
                Member.voornaam.ilike(_escape_like(voornaam), escape="\\"),
                Member.achternaam.ilike(_escape_like(achternaam), escape="\\"),
            )
            .all()
        )
        if len(matches) > 1:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Meerdere accounts gevonden met deze naam. Gebruik je NBB-nummer om in te loggen."},
                status_code=401,
            )
        if len(matches) == 1:
            member = matches[0]
            email = member.email or ""
    else:
        nbb = form.get("nbb_nummer", "").strip()
        member = db.query(Member).filter(Member.lidnummer == nbb).first()
        email = member.email or "" if member else ""

    if member and member.verwijderd_op is not None:
        return templates.TemplateResponse(
            request, "login.html", {"login_status": "verwijderd"}, status_code=401
        )

    if member and member.wachtwoord_hash and verify_password(password, member.wachtwoord_hash):
        ratelimit.reset(rate_key)
        # Legacy-hashes transparant upgraden naar het huidige formaat/iteraties
        if needs_rehash(member.wachtwoord_hash):
            member.wachtwoord_hash = hash_password(password)
            db.commit()
        request.session["user_id"] = member.id
        request.session["welkom"] = True
        return RedirectResponse(url=next_url, status_code=302)

    # Elke mislukte poging telt mee voor de rate limit — ook de status-antwoorden
    # hieronder, anders zijn die onbeperkt te gebruiken om accounts te enumereren.
    ratelimit.record_failure(rate_key)

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
        # Alleen relevant voor de oude uitnodigingsflow: het account bestaat nog
        # niet en wacht op activatie via de invite-link. Bestaat het account al
        # (self-service registratie), dan is een mislukte inlogpoging gewoon een
        # onjuist wachtwoord — geen speciale melding nodig.
        account_bestaat = member is not None or (
            email and db.query(Member).filter(Member.email.ilike(email)).first()
        )
        if not account_bestaat:
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
        {"error": "Onbekend NBB-nummer/naam of onjuist wachtwoord."},
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
    nbb_nummer = form.get("lidnummer", "").strip()
    password = form.get("password", "")
    password2 = form.get("password2", "")

    def _render(extra: dict, status: int = 422):
        return templates.TemplateResponse(
            request,
            "registreren.html",
            {
                "voornaam": voornaam,
                "achternaam": achternaam,
                "email": email,
                "lidnummer": nbb_nummer,
                **extra,
            },
            status_code=status,
        )

    # ── Basisvalidatie ────────────────────────────────────────────────────────
    errors = []
    toestemming = form.get("toestemming", "")

    if not voornaam:
        errors.append("Voornaam is verplicht.")
    if not achternaam:
        errors.append("Achternaam is verplicht.")
    if not email:
        errors.append("E-mailadres is verplicht.")
    if not nbb_nummer:
        errors.append("NBB-nummer is verplicht.")
    if len(password) < 8:
        errors.append("Wachtwoord moet minimaal 8 tekens bevatten.")
    if password != password2:
        errors.append("Wachtwoorden komen niet overeen.")
    if not toestemming:
        errors.append("U moet akkoord gaan met het privacybeleid.")
    if errors:
        return _render({"errors": errors})

    # ── Controleer: account bestaat al ───────────────────────────────────────
    # Het lidnummer is de onderscheidende factor voor een account — meerdere
    # leden (bv. gezinsleden) mogen hetzelfde e-mailadres gebruiken.
    bestaand_op_nbb = db.query(Member).filter(Member.lidnummer == nbb_nummer).first()
    if bestaand_op_nbb:
        return _render({"melding": "al_account"})

    # ── Zoek in ledenlijsten van alle aangesloten clubs ───────────────────────
    # Primair: zoek op NBB-nummer
    leden_op_nbb = db.query(Lid).filter(Lid.nbb_nummer == nbb_nummer).all()

    if leden_op_nbb:
        # Dit lidnummer staat in een ledenlijst — de naam moet dan wel kloppen,
        # anders kan iemand met andermans lidnummer een account claimen.
        # Geen account aanmaken in dat geval; de aanvrager moet de gegevens
        # corrigeren of contact opnemen met de wedstrijdleider.
        eerste_lid = leden_op_nbb[0]
        voornaam_klopt = eerste_lid.voornaam.strip().lower() == voornaam.lower()
        achternaam_klopt = eerste_lid.achternaam.strip().lower() == achternaam.lower()
        if not (voornaam_klopt and achternaam_klopt):
            return _render({"melding": "naam_mismatch"})
        gekoppelde_leden = leden_op_nbb
    else:
        # Fallback: handmatig toegevoegde leden hebben geen NBB-nummer; zoek op naam
        gekoppelde_leden = db.query(Lid).filter(
            Lid.voornaam.ilike(voornaam),
            Lid.achternaam.ilike(achternaam),
            Lid.nbb_nummer.is_(None),
        ).all()

    # ── Account aanmaken; clubtoegang volgt uit de ledenlijst ─────────────────
    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == email).first()
    role = assignment.role if assignment else MemberRole.lid

    member = Member(
        voornaam=voornaam,
        achternaam=achternaam,
        lidnummer=nbb_nummer,
        email=email,
        wachtwoord_hash=hash_password(password),
        role=role,
        toestemming_op=datetime.now(timezone.utc),
    )
    db.add(member)
    db.flush()

    # Koppel aan alle clubs waar het lid voorkomt in de ledenlijst; zonder
    # treffer blijft het account clubloos tot een wedstrijdleider het toevoegt
    club_ids = {lid.club_id for lid in gekoppelde_leden if lid.club_id}
    for club_id in club_ids:
        _koppel_aan_club(member, db, club_id=club_id)

    try:
        db.commit()
        db.refresh(member)
    except Exception:
        db.rollback()
        logger.exception("DB-fout bij aanmaken account voor lid-id [verborgen]")
        return _render({"errors": ["Er is een technische fout opgetreden. Probeer het later opnieuw."]})

    request.session["user_id"] = member.id
    request.session["welkom"] = True
    return RedirectResponse(url="/", status_code=302)


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
    # Lidnummer is de onderscheidende factor voor een account, niet e-mail —
    # alleen blokkeren als dit specifieke lidnummer al een account heeft.
    if lidnummer and db.query(Member).filter(Member.lidnummer == lidnummer).first():
        errors.append("Er bestaat al een account met dit lidnummer.")

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
        toestemming_op=datetime.now(timezone.utc),
    )
    db.add(member)
    db.flush()

    # Koppel aan de uitgenodigde club
    _koppel_aan_club(member, db, club_id=invitation.club_id)

    # Zoek ook in alle andere clubs op NBB-nummer of naam
    if lidnummer and not lidnummer.startswith("lid_"):
        extra_leden = db.query(Lid).filter(Lid.nbb_nummer == lidnummer).all()
    else:
        extra_leden = db.query(Lid).filter(
            Lid.voornaam.ilike(voornaam),
            Lid.achternaam.ilike(achternaam),
            Lid.nbb_nummer.is_(None),
        ).all()
    for lid in extra_leden:
        if lid.club_id and lid.club_id != invitation.club_id:
            _koppel_aan_club(member, db, club_id=lid.club_id)

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

    # Begrens het aantal reset-mails per IP
    rate_key = f"reset:{ratelimit.client_key(request)}"
    if ratelimit.is_limited(rate_key):
        return templates.TemplateResponse(
            request, "wachtwoord_vergeten.html", {"verzonden": True}
        )
    ratelimit.record_failure(rate_key)

    form = await request.form()
    email = form.get("email", "").strip().lower()

    member = db.query(Member).filter(Member.email.ilike(email)).first() if email else None
    if not member:
        pass  # Silently ignore unknown addresses — don't log to avoid leaking which emails exist
    else:
        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(token=token, member_id=member.id))
        db.commit()
        base_url = os.getenv("BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
        reset_url = f"{base_url}/wachtwoord-reset/{token}"
        try:
            send_password_reset_email(member.email, member.voornaam, reset_url)
            logger.info("Wachtwoord-reset e-mail verstuurd naar member-id %d", member.id)
        except Exception:
            logger.exception("Wachtwoord-reset e-mail mislukt voor member-id %d", member.id)
            return templates.TemplateResponse(
                request, "wachtwoord_vergeten.html",
                {"error": "Het versturen van de e-mail is mislukt. Probeer het later opnieuw of neem contact op met de beheerder."},
            )

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
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("DB-fout bij wachtwoord-reset voor token %s", token)
        return templates.TemplateResponse(
            request, "wachtwoord_reset.html",
            {"token": token, "errors": ["Er is een technische fout opgetreden. Probeer het later opnieuw."]},
            status_code=500,
        )

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


# ── Admin bericht (publiek) ───────────────────────────────────────────────────

@router.post("/admin-bericht")
async def admin_bericht_submit(request: Request, db: Session = Depends(get_db)):
    from app.models import AdminBericht

    # Publiek formulier: begrens het aantal berichten per IP tegen spam
    rate_key = f"admin_bericht:{ratelimit.client_key(request)}"
    if ratelimit.is_limited(rate_key):
        return RedirectResponse(url="/login?bericht_fout=1", status_code=302)
    ratelimit.record_failure(rate_key)

    form = await request.form()
    naam = form.get("naam", "").strip() or None
    email_val = form.get("email", "").strip() or None
    bericht = form.get("bericht", "").strip()
    type_ = form.get("type", "contact")

    if not bericht:
        return RedirectResponse(url="/login?bericht_fout=1", status_code=302)

    db.add(AdminBericht(naam=naam, email=email_val, bericht=bericht, type=type_))
    db.commit()
    return RedirectResponse(url="/login?bericht_verstuurd=1", status_code=302)


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
