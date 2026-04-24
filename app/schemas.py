from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models import (
    EveningType,
    MemberRole,
    PartnershipScope,
    RegistrationStatus,
    RegistrationType,
)


# ── Member ────────────────────────────────────────────────────────────────────

class MemberBase(BaseModel):
    voornaam: str
    achternaam: str
    lidnummer: str
    training_eligible: bool = False
    role: MemberRole = MemberRole.lid


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    voornaam: Optional[str] = None
    achternaam: Optional[str] = None
    training_eligible: Optional[bool] = None
    role: Optional[MemberRole] = None


class MemberRead(MemberBase):
    id: int

    model_config = {"from_attributes": True}


# ── Invitation ────────────────────────────────────────────────────────────────

class InvitationCreate(BaseModel):
    email: EmailStr


class InvitationRead(BaseModel):
    id: int
    email: str
    aangemaakt_op: datetime
    gebruikt_op: Optional[datetime]
    member_id: Optional[int]

    model_config = {"from_attributes": True}


# ── Season ────────────────────────────────────────────────────────────────────

class SeasonCreate(BaseModel):
    naam: str
    start_datum: date
    eind_datum: date


class SeasonRead(SeasonCreate):
    id: int
    actief: bool

    model_config = {"from_attributes": True}


# ── ClubEvening ───────────────────────────────────────────────────────────────

class ClubEveningCreate(BaseModel):
    datum: date
    type: EveningType = EveningType.regulier
    season_id: int


class ClubEveningRead(ClubEveningCreate):
    id: int

    model_config = {"from_attributes": True}


# ── FixedPartnership ──────────────────────────────────────────────────────────

class FixedPartnershipCreate(BaseModel):
    person1_id: int
    person2_id: int
    start_datum: date
    eind_datum: Optional[date] = None
    scope: PartnershipScope = PartnershipScope.all


class FixedPartnershipRead(FixedPartnershipCreate):
    id: int

    model_config = {"from_attributes": True}


# ── Registration ──────────────────────────────────────────────────────────────

class RegistrationCreate(BaseModel):
    evening_id: int
    person1_id: int
    person2_id: Optional[int] = None
    type: RegistrationType


class RegistrationUpdate(BaseModel):
    status: Optional[RegistrationStatus] = None
    substitute_name: Optional[str] = None
    available_person_id: Optional[int] = None
    combo_partner_reg_id: Optional[int] = None


class RegistrationRead(BaseModel):
    id: int
    evening_id: int
    person1_id: int
    person2_id: Optional[int]
    type: RegistrationType
    status: RegistrationStatus
    substitute_name: Optional[str]
    available_person_id: Optional[int]
    combo_partner_reg_id: Optional[int]
    aangemeld_op: datetime
    gewijzigd_op: datetime

    model_config = {"from_attributes": True}
