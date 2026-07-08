"""
Opstarttaken: schemasynchronisatie, seeds en opschoning.

Deze draaien in de lifespan-handler van app.main — bij het starten van de
server, niet bij import. Zo blijven imports (tests, scripts) vrij van
bijwerkingen op de database.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from app.auth import hash_password
from app.config import CLUB_LEDENLIJST_CSV, CLUB_NAAM, CLUB_STAD
from app.database import SessionLocal, engine
from app.models import (
    AccountRequest,
    AccountRequestStatus,
    Club,
    EmailRoleAssignment,
    Lid,
    Member,
    MemberClub,
    MemberRole,
    PasswordResetToken,
)
from app.schema_sync import sync_schema

logger = logging.getLogger(__name__)


def run_startup_tasks() -> None:
    sync_schema(engine)
    seed_admin()
    seed_club()
    seed_algemene_club()
    seed_leden()
    cleanup_expired_data()


def seed_admin() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "")
    if not admin_email:
        return

    admin_password = os.getenv("ADMIN_PASSWORD", "")
    db = SessionLocal()
    try:
        assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == admin_email).first()
        if assignment:
            assignment.role = MemberRole.admin
        else:
            db.add(EmailRoleAssignment(email=admin_email, role=MemberRole.admin))

        member = db.query(Member).filter(Member.email == admin_email).first()
        if member:
            if member.role != MemberRole.admin:
                member.role = MemberRole.admin
            if member.lidnummer != "ADMIN001":
                member.lidnummer = "ADMIN001"
            if admin_password:
                member.wachtwoord_hash = hash_password(admin_password)
                logger.info("Admin-wachtwoord bijgewerkt voor %s", admin_email)
        elif admin_password:
            db.add(Member(
                voornaam="Admin",
                achternaam="",
                lidnummer=f"admin_{admin_email.split('@')[0]}",
                email=admin_email,
                wachtwoord_hash=hash_password(admin_password),
                role=MemberRole.admin,
            ))
            logger.info("Admin-account aangemaakt voor %s", admin_email)

        db.commit()
    finally:
        db.close()


def seed_club() -> None:
    """Maak de initiële club aan en koppel bestaande data als er nog geen clubs zijn."""
    db = SessionLocal()
    try:
        club = db.query(Club).first()
        if club is None:
            club = Club(naam=CLUB_NAAM, stad=CLUB_STAD or None)
            db.add(club)
            db.flush()

            cid = club.id
            for tabel in ("seasons", "club_evenings", "leden", "rankings",
                          "berichten", "account_requests", "invitations"):
                db.execute(text(f"UPDATE {tabel} SET club_id = :cid WHERE club_id IS NULL"), {"cid": cid})

            members = db.query(Member).filter(Member.verwijderd_op.is_(None)).all()
            for m in members:
                exists = db.query(MemberClub).filter(
                    MemberClub.member_id == m.id,
                    MemberClub.club_id == cid,
                ).first()
                if not exists:
                    db.add(MemberClub(member_id=m.id, club_id=cid, role=m.role))

            db.commit()
            logger.info("Club '%s' aangemaakt (id=%d), bestaande data gekoppeld.", CLUB_NAAM, cid)
        else:
            cid = club.id
            for tabel in ("seasons", "club_evenings", "leden"):
                db.execute(text(f"UPDATE {tabel} SET club_id = :cid WHERE club_id IS NULL"), {"cid": cid})
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Seed club mislukt: %s", e)
    finally:
        db.close()


def seed_algemene_club() -> None:
    """
    Maak de club 'Algemeen' aan als die nog niet bestaat. Iedereen is hier
    automatisch lid van (zie app.auth); evenementen van deze club zijn dus
    zichtbaar voor alle gebruikers. Moet ná seed_club() draaien, zodat
    bestaande data (club_id NULL) aan de gewone club gekoppeld wordt.
    """
    db = SessionLocal()
    try:
        bestaat = db.query(Club).filter(Club.is_algemeen == True).first()  # noqa: E712
        if bestaat is None:
            db.add(Club(naam="Algemeen", is_algemeen=True))
            db.commit()
            logger.info("Algemene club 'Algemeen' aangemaakt.")
    except Exception as e:
        db.rollback()
        logger.warning("Seed algemene club mislukt: %s", e)
    finally:
        db.close()


def seed_leden() -> None:
    csv_path = Path(CLUB_LEDENLIJST_CSV)
    if not csv_path.exists():
        return

    db = SessionLocal()
    try:
        if db.query(Lid).first() is None:
            from scripts.seed_crash_leden import seed
            n = seed(db, csv_path=csv_path)
            if n:
                logger.info("%d leden van %s geladen.", n, CLUB_NAAM)
    except Exception as e:
        logger.warning("Seed leden mislukt: %s", e)
    finally:
        db.close()


def cleanup_expired_data() -> None:
    """Verwijder verlopen tokens en afgewezen aanvragen (bewaartermijn handhaving)."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        deleted_tokens = (
            db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.aangemaakt_op < now - timedelta(hours=24),
                PasswordResetToken.gebruikt_op.is_(None),
            )
            .delete(synchronize_session=False)
        )

        deleted_requests = (
            db.query(AccountRequest)
            .filter(
                AccountRequest.status == AccountRequestStatus.afgewezen,
                AccountRequest.aangemaakt_op < now - timedelta(days=90),
            )
            .delete(synchronize_session=False)
        )

        db.commit()
        if deleted_tokens or deleted_requests:
            logger.info(
                "Opschoning: %d verlopen tokens, %d afgewezen aanvragen verwijderd",
                deleted_tokens,
                deleted_requests,
            )
    except Exception as e:
        db.rollback()
        logger.warning("Opschoning mislukt: %s", e)
    finally:
        db.close()
