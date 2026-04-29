import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Member, MemberRole

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, dk_hex = stored_hash.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return secrets.compare_digest(dk.hex(), dk_hex)


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[Member]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    member = db.query(Member).filter(Member.id == user_id).first()
    if member and member.verwijderd_op is not None:
        request.session.clear()
        return None
    return member


def require_auth(
    current_user: Optional[Member] = Depends(get_current_user),
) -> Member:
    if current_user is None:
        raise HTTPException(status_code=401, detail="Niet ingelogd")
    return current_user


def require_role(*roles: str):
    def dependency(current_user: Member = Depends(require_auth)) -> Member:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Geen toegang")
        return current_user

    return dependency


def require_wedstrijdleider(
    current_user: Member = Depends(require_auth),
) -> Member:
    if current_user.role not in (MemberRole.wedstrijdleider.value, MemberRole.admin.value):
        raise HTTPException(status_code=403, detail="Geen toegang")
    return current_user


def require_admin(current_user: Member = Depends(require_auth)) -> Member:
    if current_user.role != MemberRole.admin.value:
        raise HTTPException(status_code=403, detail="Geen toegang")
    return current_user
