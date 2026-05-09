import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from app.auth import SECRET_KEY  # noqa: E402 — must be after load_dotenv
from app.database import Base, engine  # noqa: E402
from app.routes import admin, auth, berichten, evenings, members, registrations, rankings, uitslagen  # noqa: E402

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _get_user_for_request(request: Request):
    try:
        from app.database import SessionLocal
        from app.models import Member
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        db = SessionLocal()
        try:
            return db.query(Member).filter(Member.id == user_id).first()
        finally:
            db.close()
    except Exception:
        return None

# Create all tables (no-op if they already exist; Alembic handles migrations)
Base.metadata.create_all(bind=engine)


def _migrate():
    from sqlalchemy import text
    from app.database import engine

    migrations = [
        "ALTER TABLE registrations ADD COLUMN partner_naam TEXT",
        "ALTER TABLE club_evenings ADD COLUMN naam VARCHAR",
        "ALTER TABLE account_requests ADD COLUMN wachtwoord_hash VARCHAR",
        "ALTER TABLE members ADD COLUMN wachtwoord_hash VARCHAR",
        "ALTER TABLE members ADD COLUMN training_eligible BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE members ADD COLUMN verwijderd_op TIMESTAMP",
        "ALTER TABLE members ADD COLUMN verborgen_types VARCHAR",
        "ALTER TABLE club_evenings ADD COLUMN deelnemers_type VARCHAR NOT NULL DEFAULT 'paren'",
        "ALTER TABLE club_evenings ADD COLUMN inschrijftermijn_uren INTEGER",
        "ALTER TABLE registrations ADD COLUMN partner2_naam VARCHAR",
        "ALTER TABLE registrations ADD COLUMN partner3_naam VARCHAR",
        "ALTER TABLE registrations ADD COLUMN substitute_name TEXT",
        "ALTER TABLE registrations ADD COLUMN available_person_id INTEGER REFERENCES members(id)",
        "ALTER TABLE registrations ADD COLUMN combo_partner_reg_id INTEGER REFERENCES registrations(id)",
        "ALTER TABLE registrations ADD COLUMN te_laat BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE registrations ADD COLUMN te_laat_goedgekeurd BOOLEAN",
        (
            "CREATE TABLE IF NOT EXISTS berichten ("
            "id INTEGER PRIMARY KEY, "
            "afzender_id INTEGER NOT NULL REFERENCES members(id), "
            "ontvanger_id INTEGER NOT NULL REFERENCES members(id), "
            "onderwerp VARCHAR, "
            "tekst TEXT NOT NULL, "
            "aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "gelezen BOOLEAN NOT NULL DEFAULT 0, "
            "parent_id INTEGER REFERENCES berichten(id))"
        ),
        (
            "CREATE TABLE IF NOT EXISTS rankings ("
            "id INTEGER PRIMARY KEY, "
            "inhoud TEXT NOT NULL, "
            "bestandsnaam VARCHAR, "
            "aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "aangemaakt_door_id INTEGER REFERENCES members(id))"
        ),
        (
            "CREATE TABLE IF NOT EXISTS uitslagen ("
            "id INTEGER PRIMARY KEY, "
            "evening_id INTEGER NOT NULL UNIQUE REFERENCES club_evenings(id), "
            "bestandsnaam VARCHAR, "
            "inhoud BLOB NOT NULL, "
            "aangemaakt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "aangemaakt_door_id INTEGER REFERENCES members(id))"
        ),
        "ALTER TABLE berichten ADD COLUMN is_nieuws BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE berichten ALTER COLUMN ontvanger_id DROP NOT NULL",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception as rollback_exc:
                    logger.warning("Rollback mislukt na migratiefout: %s", rollback_exc)


_migrate()


def _seed_admin():
    from app.auth import hash_password
    from app.database import SessionLocal
    from app.models import EmailRoleAssignment, Member, MemberRole

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


_seed_admin()


def _seed_crash_leden():
    from app.database import SessionLocal
    from app.models import Lid

    db = SessionLocal()
    try:
        if db.query(Lid).first() is None:
            from scripts.seed_crash_leden import seed
            n = seed(db)
            if n:
                logger.info("%d leden van Crash geladen.", n)
    except Exception as e:
        logger.warning("Seed crash-leden mislukt: %s", e)
    finally:
        db.close()


_seed_crash_leden()

app = FastAPI(title="Bridge Club Aanmeldingsapp", docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="strict")


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=302)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    current_user = _get_user_for_request(request)
    return _templates.TemplateResponse(
        request, "errors/403.html",
        {"current_user": current_user, "welkom": False},
        status_code=403,
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    current_user = _get_user_for_request(request)
    return _templates.TemplateResponse(
        request, "errors/404.html",
        {"current_user": current_user, "welkom": False},
        status_code=404,
    )

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(evenings.router)
app.include_router(registrations.router)
app.include_router(members.router)
app.include_router(admin.router)
app.include_router(berichten.router)
app.include_router(rankings.router)
app.include_router(uitslagen.router)
