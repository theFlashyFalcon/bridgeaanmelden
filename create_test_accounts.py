"""
Script om 3 testaccounts aan te maken: lid, wedstrijdleider en admin.
Gebruik: python create_test_accounts.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine
from app.models import Base, Member, MemberRole
from app.auth import hash_password

Base.metadata.create_all(bind=engine)

ACCOUNTS = [
    {
        "voornaam": "Jan",
        "achternaam": "Jansen",
        "lidnummer": "TEST001",
        "email": "lid@bridgeclub.test",
        "wachtwoord": "Wachtwoord1!",
        "role": MemberRole.lid,
    },
    {
        "voornaam": "Petra",
        "achternaam": "de Vries",
        "lidnummer": "TEST002",
        "email": "wedstrijdleider@bridgeclub.test",
        "wachtwoord": "Wachtwoord2!",
        "role": MemberRole.wedstrijdleider,
    },
    {
        "voornaam": "Admin",
        "achternaam": "Beheerder",
        "lidnummer": "TEST003",
        "email": "admin@bridgeclub.test",
        "wachtwoord": "Wachtwoord3!",
        "role": MemberRole.admin,
    },
]

db = SessionLocal()
try:
    for account in ACCOUNTS:
        existing = db.query(Member).filter(Member.email == account["email"]).first()
        if existing:
            print(f"Account {account['email']} bestaat al, overgeslagen.")
            continue

        member = Member(
            voornaam=account["voornaam"],
            achternaam=account["achternaam"],
            lidnummer=account["lidnummer"],
            email=account["email"],
            wachtwoord_hash=hash_password(account["wachtwoord"]),
            role=account["role"].value,
            training_eligible=False,
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        print(
            f"Aangemaakt: {account['voornaam']} {account['achternaam']} "
            f"| Rol: {account['role'].value} "
            f"| Email: {account['email']} "
            f"| Wachtwoord: {account['wachtwoord']}"
        )
finally:
    db.close()

print("\nKlaar!")
