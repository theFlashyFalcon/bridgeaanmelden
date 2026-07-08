"""Gedeelde hulpfuncties voor de beheer-routes."""
import os

from fastapi import Request


def _base_url(request: Request) -> str:
    configured = os.getenv("BASE_URL", "").rstrip("/")
    return configured or str(request.base_url).rstrip("/")
