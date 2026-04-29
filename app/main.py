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

from app.auth import SECRET_KEY  # noqa: E402 — must be after load_dotenv
from app.database import Base, engine  # noqa: E402
from app.routes import admin, auth, evenings, members, registrations  # noqa: E402

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
        "ALTER TABLE members ADD COLUMN verwijderd_op TIMESTAMP",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass


_migrate()


def _seed_admin():
    from app.auth import hash_password
    from app.database import SessionLocal
    from app.models import EmailRoleAssignment, Member, MemberRole

    db = SessionLocal()
    try:
        admin_email = os.getenv("ADMIN_EMAIL", "marieke@summadigita.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "")

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
            # Maak admin-account aan als ADMIN_PASSWORD is ingesteld en account nog niet bestaat
            db.add(Member(
                voornaam="Admin",
                achternaam="",
                lidnummer=f"admin_{admin_email.split('@')[0]}",
                email=admin_email,
                wachtwoord_hash=hash_password(admin_password),
                role=MemberRole.admin,
            ))
            print(f"[seed_admin] Admin-account aangemaakt voor {admin_email}", flush=True)

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
                print(f"[startup] {n} leden van Crash geladen.")
    except Exception as e:
        print(f"[startup] Seed crash-leden mislukt: {e}")
    finally:
        db.close()


_seed_crash_leden()

app = FastAPI(title="Bridge Club Aanmeldingsapp", docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


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
