"""Gedeelde hulpfuncties voor de beheer-routes."""
import os
from typing import Optional

from fastapi import Request

from app.models import Club, MemberRole


def _base_url(request: Request) -> str:
    configured = os.getenv("BASE_URL", "").rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _rol_opties(club: Optional[Club]) -> list[tuple[str, str]]:
    """
    Rol-keuzes voor een dropdown, als (waarde, label)-paren. 'wedstrijdleider'
    wordt gelabeld met de betreffende club en helemaal weggelaten zonder club
    of voor de algemene club — die kan uitsluitend door admins beheerd worden.
    """
    opties = [(MemberRole.lid.value, "lid")]
    if club is not None and not club.is_algemeen:
        label = f"Wedstrijdleider van {club.naam}"
        opties.append((MemberRole.wedstrijdleider.value, label))
    opties.append((MemberRole.admin.value, "admin"))
    return opties
