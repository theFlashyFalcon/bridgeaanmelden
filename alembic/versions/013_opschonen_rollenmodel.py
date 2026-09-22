"""Ruimt data op na het loskoppelen van per-club rollen van de globale Member.role

Wedstrijdleiderschap is voortaan uitsluitend een per-club rol (member_clubs.role).
Er bestaat geen per-club 'admin'-rol meer (die was in de praktijk hetzelfde als
'wedstrijdleider'), en de globale Member.role wordt niet langer automatisch naar
'wedstrijdleider' gepromoveerd zodra iemand ergens WL wordt (zie app/auth.py,
de verwijderde sync_global_role()). Deze migratie ruimt bestaande data op:

1. member_clubs.role == 'admin' -> 'wedstrijdleider' (praktische betekenis
   was al hetzelfde; er is geen aparte per-club adminrol meer).
2. members.role == 'wedstrijdleider' -> 'lid' (deze waarde komt alleen nog
   voor doordat oudere code hem hier automatisch op zette; wedstrijdleiderschap
   staat voortaan uitsluitend in member_clubs).

members.role == 'admin' wordt bewust NIET automatisch aangepast: dat zou
gokken zijn wie een "echte" globale admin hoort te zijn versus per ongeluk
gepromoveerd via de oude sync_global_role(). Na deze migratie is de globale
rol betrouwbaar (nooit meer automatisch afgeleid), dus kunnen per-ongeluk-
gepromoveerde accounts voortaan gewoon via /leden/{id}/rol worden teruggezet.

Revision ID: 013
Revises: 012
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE member_clubs SET role = 'wedstrijdleider' WHERE role = 'admin'"
    )
    op.execute(
        "UPDATE members SET role = 'lid' WHERE role = 'wedstrijdleider'"
    )


def downgrade() -> None:
    # Niet omkeerbaar: welke member_clubs-rijen ooit 'admin' waren, en welke
    # members.role ooit 'wedstrijdleider' was, is niet meer te reconstrueren.
    pass
