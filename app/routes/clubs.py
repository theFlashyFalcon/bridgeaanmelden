import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import ANDERE_CLUBS, INTER_CLUB_SECRET
from app.database import get_db
from app.models import Member
from app.templates_env import templates

logger = logging.getLogger(__name__)
router = APIRouter()

_TOKEN_TTL = 30  # seconden


def _maak_token(email: str) -> str:
    payload = json.dumps({"email": email, "exp": int(time.time()) + _TOKEN_TTL})
    b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(INTER_CLUB_SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _verifieer_token(token: str) -> str | None:
    """Geeft email terug als het token geldig en niet verlopen is, anders None."""
    try:
        b64, sig = token.split(".", 1)
        verwacht = hmac.new(INTER_CLUB_SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, verwacht):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64 + "==").decode())
        if payload["exp"] < int(time.time()):
            return None
        return payload["email"]
    except Exception:
        return None


@router.get("/wissel-club")
async def wissel_club(request: Request, naar: str, db: Session = Depends(get_db)):
    """Genereert een tijdelijk token en stuurt de gebruiker door naar de doelclub."""
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if not INTER_CLUB_SECRET:
        return RedirectResponse(url="/", status_code=302)

    bekende_urls = {c["url"] for c in ANDERE_CLUBS}
    if naar.rstrip("/") not in bekende_urls:
        return RedirectResponse(url="/", status_code=302)

    token = _maak_token(current_user.email)
    return RedirectResponse(url=f"{naar.rstrip('/')}/club-login?token={token}", status_code=302)


@router.get("/club-login")
async def club_login(request: Request, token: str, db: Session = Depends(get_db)):
    """Ontvangt token van een andere club en logt de gebruiker automatisch in."""
    if not INTER_CLUB_SECRET:
        return RedirectResponse(url="/login", status_code=302)

    email = _verifieer_token(token)
    if not email:
        return RedirectResponse(url="/login?error=1", status_code=302)

    member = (
        db.query(Member)
        .filter(Member.email == email, Member.verwijderd_op.is_(None))
        .first()
    )
    if not member:
        return templates.TemplateResponse(
            request,
            "club_login_geen_account.html",
            {"current_user": None, "welkom": False, "email": email},
            status_code=403,
        )

    request.session["user_id"] = member.id
    logger.info("Club-wissel inlog: %s (id=%d)", email, member.id)
    return RedirectResponse(url="/?welkom=1", status_code=302)
