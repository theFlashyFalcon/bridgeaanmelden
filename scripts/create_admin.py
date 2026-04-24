"""Run once to create (or reset the password of) the admin member.

Usage:
    python scripts/create_admin.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import EmailRoleAssignment, Member, MemberRole

EMAIL = "marieke@summadigita.com"
PASSWORD = "adminww1"  # change as desired — must be ≥ 8 characters

Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    # Ensure the email-role assignment exists
    assignment = db.query(EmailRoleAssignment).filter(EmailRoleAssignment.email == EMAIL).first()
    if not assignment:
        db.add(EmailRoleAssignment(email=EMAIL, role=MemberRole.admin))

    member = db.query(Member).filter(Member.email == EMAIL).first()
    if member:
        member.wachtwoord_hash = hash_password(PASSWORD)
        print(f"Wachtwoord bijgewerkt voor {EMAIL}")
    else:
        db.add(Member(
            voornaam="Marieke",
            achternaam="Admin",
            lidnummer="admin-001",
            email=EMAIL,
            wachtwoord_hash=hash_password(PASSWORD),
            role=MemberRole.admin,
        ))
        print(f"Admin account aangemaakt voor {EMAIL}")

    db.commit()
    print(f"Klaar — log in met: {EMAIL} / {PASSWORD}")
finally:
    db.close()
