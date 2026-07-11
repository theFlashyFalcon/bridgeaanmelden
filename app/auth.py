import hashlib
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Club, Member, MemberClub, MemberRole

_logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "dev-secret-key-change-in-production"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
if SECRET_KEY == _DEFAULT_SECRET:
    if os.getenv("HTTPS_ONLY", "false").lower() == "true":
        # Met de bekende dev-sleutel kan iedereen sessies vervalsen — weiger te starten.
        raise RuntimeError(
            "SECRET_KEY is niet ingesteld terwijl HTTPS_ONLY=true (productie). "
            "Genereer een sleutel met: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "en zet die in .env of de omgeving."
        )
    _logger.warning(
        "SECRET_KEY is niet ingesteld — de standaard dev-sleutel wordt gebruikt. "
        "Stel SECRET_KEY in via .env vóór productiegebruik."
    )

# OWASP-aanbeveling voor PBKDF2-HMAC-SHA256 (2023). Oude hashes (formaat
# "salt$hash", 260k iteraties) blijven geldig en worden bij inloggen
# transparant geüpgraded — zie needs_rehash() en de login-route.
_ITERATIONS = 600_000
_LEGACY_ITERATIONS = 260_000
_HASH_PREFIX = "pbkdf2_sha256$"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"{_HASH_PREFIX}{_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(_HASH_PREFIX):
        try:
            _, iter_str, salt, dk_hex = stored_hash.split("$", 3)
            iterations = int(iter_str)
        except ValueError:
            return False
    else:  # legacy-formaat: "salt$hash"
        try:
            salt, dk_hex = stored_hash.split("$", 1)
        except ValueError:
            return False
        iterations = _LEGACY_ITERATIONS
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return secrets.compare_digest(dk.hex(), dk_hex)


def needs_rehash(stored_hash: str) -> bool:
    """True als de hash in het legacy-formaat staat of met te weinig iteraties is gemaakt."""
    if not stored_hash.startswith(_HASH_PREFIX):
        return True
    try:
        iter_str = stored_hash.split("$", 2)[1]
        return int(iter_str) < _ITERATIONS
    except (ValueError, IndexError):
        return True


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
    db: Session = Depends(get_db),
) -> Member:
    """Geeft toegang aan globale admins/WLs én leden met een per-club WL-rol."""
    if current_user.role in (MemberRole.wedstrijdleider.value, MemberRole.admin.value):
        return current_user
    mc = db.query(MemberClub).filter(
        MemberClub.member_id == current_user.id,
        MemberClub.role.in_([MemberRole.admin.value, MemberRole.wedstrijdleider.value]),
    ).first()
    if not mc:
        raise HTTPException(status_code=403, detail="Geen toegang")
    return current_user


def require_admin(current_user: Member = Depends(require_auth)) -> Member:
    if current_user.role != MemberRole.admin.value:
        raise HTTPException(status_code=403, detail="Geen toegang")
    return current_user


def get_algemene_club_id(db: Session) -> Optional[int]:
    """Id van de algemene club (iedereen is er automatisch lid van), of None."""
    row = db.query(Club.id).filter(Club.is_algemeen == True).first()  # noqa: E712
    return row[0] if row else None


def is_member_of_club(member: Member, club_id: Optional[int], db: Session) -> bool:
    """
    True als het lid bij deze club hoort. club_id None (legacy data) is altijd
    toegankelijk; van de algemene club is iedereen automatisch lid; globale
    admins hebben altijd toegang tot alle clubs.
    """
    if member.role == MemberRole.admin.value:
        return True
    if club_id is None:
        return True
    exists = (
        db.query(MemberClub)
        .filter(MemberClub.member_id == member.id, MemberClub.club_id == club_id)
        .first()
        is not None
    )
    if exists:
        return True
    return club_id == get_algemene_club_id(db)


def can_manage_club(member: Member, club_id: Optional[int], db: Session) -> bool:
    """
    True als dit lid beheerrechten heeft voor deze club:
    - globale admins altijd;
    - de algemene club kan uitsluitend door globale admins beheerd worden,
      ongeacht eventuele (club-)rollen op MemberClub;
    - club_id None (legacy data zonder club) is voor elke WL toegankelijk;
    - anders is een WL/admin-rol bij die club vereist (globale WL's zonder
      enige clubkoppeling gelden als legacy en mogen ook).
    """
    if member.role == MemberRole.admin.value:
        return True
    if club_id is not None and club_id == get_algemene_club_id(db):
        return False
    if club_id is None:
        return True
    rows = db.query(MemberClub).filter(MemberClub.member_id == member.id).all()
    if not rows and member.role == MemberRole.wedstrijdleider.value:
        return True
    beheer_rollen = (MemberRole.admin.value, MemberRole.wedstrijdleider.value)
    return any(mc.club_id == club_id and mc.role in beheer_rollen for mc in rows)


def sync_global_role(member: Member, db: Session) -> None:
    """Synchroniseert member.role met de hoogste rol in alle MemberClub-rijen."""
    all_mc = db.query(MemberClub).filter(MemberClub.member_id == member.id).all()
    roles = [mc.role for mc in all_mc]
    if MemberRole.admin.value in roles:
        member.role = MemberRole.admin.value
    elif MemberRole.wedstrijdleider.value in roles:
        member.role = MemberRole.wedstrijdleider.value
    else:
        member.role = MemberRole.lid.value


def get_club_role(member: Member, club_id: int, db: Session) -> Optional[str]:
    """Geeft de rol van een lid bij een specifieke club, of None als geen lid."""
    mc = db.query(MemberClub).filter(
        MemberClub.member_id == member.id,
        MemberClub.club_id == club_id,
    ).first()
    return mc.role if mc else None


def get_member_club_ids(member: Member, db: Session) -> list[int]:
    """
    Geeft alle club-id's waarvan dit lid lid is, inclusief de algemene club.
    Globale admins krijgen alle clubs, ongeacht expliciete MemberClub-koppeling.
    """
    if member.role == MemberRole.admin.value:
        return [r[0] for r in db.query(Club.id).all()]
    rows = db.query(MemberClub.club_id).filter(MemberClub.member_id == member.id).all()
    ids = [r[0] for r in rows]
    algemeen_id = get_algemene_club_id(db)
    if algemeen_id is not None and algemeen_id not in ids:
        ids.append(algemeen_id)
    return ids


def get_wedstrijdleider_clubs(member: Member, db: Session) -> list[Club]:
    """Geeft alle clubs waarvan dit lid wedstrijdleider of admin is (via MemberClub)."""
    mc_rows = db.query(MemberClub).filter(
        MemberClub.member_id == member.id,
        MemberClub.role.in_([MemberRole.admin.value, MemberRole.wedstrijdleider.value]),
    ).all()
    if not mc_rows:
        return []
    club_ids = [mc.club_id for mc in mc_rows]
    return db.query(Club).filter(Club.id.in_(club_ids)).order_by(Club.naam).all()


def get_admin_club(
    member: Member,
    db: Session,
    request: Optional[Request] = None,
) -> Optional[Club]:
    """
    Geeft de actieve beheer-club voor dit lid.
    - Admins: volledige toegang; session 'active_beheer_club_id' bepaalt welke club actief is.
    - Wedstrijdleiders: beperkt tot hun eigen clubs; session bepaalt welke actief is.
    - Fallback: eerste club in de database.
    """
    active_id: Optional[int] = None
    if request is not None:
        try:
            raw = request.session.get("active_beheer_club_id")
            if raw is not None:
                active_id = int(raw)
        except (ValueError, TypeError):
            pass

    if member.role == MemberRole.admin.value:
        if active_id:
            club = db.query(Club).filter(Club.id == active_id).first()
            if club:
                return club
        return db.query(Club).first()

    mc_rows = db.query(MemberClub).filter(
        MemberClub.member_id == member.id,
        MemberClub.role.in_([MemberRole.admin.value, MemberRole.wedstrijdleider.value]),
    ).all()
    valid_ids = {mc.club_id for mc in mc_rows}

    if not valid_ids:
        return db.query(Club).first()

    if active_id and active_id in valid_ids:
        return db.query(Club).filter(Club.id == active_id).first()
    return db.query(Club).filter(Club.id.in_(valid_ids)).first()
