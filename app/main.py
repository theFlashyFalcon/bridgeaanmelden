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
    from app.models import EmailRoleAssignment, MemberRole

    db = SessionLocal()
    try:
        admin_email = "marieke@summadigita.com"
        exists = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == admin_email).first()
        if not exists:
            db.add(EmailRoleAssignment(email=admin_email, role=MemberRole.admin))
            db.commit()
    finally:
        db.close()

_seed_admin()

app = FastAPI(title="Bridge Club Aanmeldingsapp", docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(evenings.router)
app.include_router(registrations.router)
app.include_router(members.router)
app.include_router(admin.router)
