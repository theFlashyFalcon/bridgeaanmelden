"""Beheer-routes (/beheer), opgesplitst per domein."""
from fastapi import APIRouter

from app.routes.admin import aanmeldingen, accounts, avonden, clubs_beheer

router = APIRouter()
router.include_router(avonden.router)
router.include_router(aanmeldingen.router)
router.include_router(accounts.router)
router.include_router(clubs_beheer.router)
