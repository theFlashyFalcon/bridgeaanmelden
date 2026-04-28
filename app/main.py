import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

from app.auth import SECRET_KEY  # noqa: E402 — must be after load_dotenv
from app.database import Base, engine  # noqa: E402
from app.routes import admin, auth, evenings, members, registrations  # noqa: E402

# Create all tables (no-op if they already exist; Alembic handles migrations)
Base.metadata.create_all(bind=engine)

# Seed default admin email-role assignment
def _seed_admin():
    from app.database import SessionLocal
    from app.models import EmailRoleAssignment, Member, MemberRole

    db = SessionLocal()
    try:
        admin_email = os.getenv("ADMIN_EMAIL", "marieke@summadigita.com")

        assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == admin_email).first()
        if assignment:
            assignment.role = MemberRole.admin
        else:
            db.add(EmailRoleAssignment(email=admin_email, role=MemberRole.admin))

        member = db.query(Member).filter(Member.email == admin_email).first()
        if member and member.role != MemberRole.admin:
            member.role = MemberRole.admin

        db.commit()
    finally:
        db.close()

_seed_admin()


def _migrate():
    from sqlalchemy import text
    from app.database import engine

    migrations = [
        "ALTER TABLE registrations ADD COLUMN partner_naam TEXT",
        "ALTER TABLE club_evenings ADD COLUMN naam VARCHAR",
        "ALTER TABLE account_requests ADD COLUMN wachtwoord_hash VARCHAR",
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

app = FastAPI(title="Bridge Club Aanmeldingsapp", docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(evenings.router)
app.include_router(registrations.router)
app.include_router(members.router)
app.include_router(admin.router)
