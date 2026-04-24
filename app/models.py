import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class MemberRole(str, enum.Enum):
    lid = "lid"
    wedstrijdleider = "wedstrijdleider"
    admin = "admin"


class EveningType(str, enum.Enum):
    clubavond = "clubavond"
    jeugdtraining = "jeugdtraining"
    eten_voor_jeugdtraining = "eten voor jeugdtraining"
    speciaal = "speciaal"
    # legacy values kept for existing data
    regulier = "regulier"
    training = "training"


class PartnershipScope(str, enum.Enum):
    all = "all"
    training_only = "training_only"


class RegistrationType(str, enum.Enum):
    vast = "vast"
    los = "los"
    training = "training"


class RegistrationStatus(str, enum.Enum):
    aangemeld = "aangemeld"
    afgemeld = "afgemeld"
    beschikbaar_solo = "beschikbaar_solo"
    invaller = "invaller"
    combipaar = "combipaar"


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    voornaam = Column(String, nullable=False)
    achternaam = Column(String, nullable=False)
    lidnummer = Column(String, unique=True, nullable=False, index=True)
    training_eligible = Column(Boolean, default=False, nullable=False)
    role = Column(String, default=MemberRole.lid, nullable=False)
    oauth_sub = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, nullable=True, index=True)
    wachtwoord_hash = Column(String, nullable=True)

    invitations = relationship("Invitation", back_populates="member")
    registrations_as_person1 = relationship(
        "Registration",
        foreign_keys="Registration.person1_id",
        back_populates="person1",
    )
    registrations_as_person2 = relationship(
        "Registration",
        foreign_keys="Registration.person2_id",
        back_populates="person2",
    )


class AccountRequestStatus(str, enum.Enum):
    wachtend = "wachtend"
    goedgekeurd = "goedgekeurd"
    afgewezen = "afgewezen"


class AccountRequest(Base):
    __tablename__ = "account_requests"

    id = Column(Integer, primary_key=True, index=True)
    voornaam = Column(String, nullable=False)
    achternaam = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    lidnummer = Column(String, nullable=False)
    wachtwoord_hash = Column(String, nullable=True)
    status = Column(String, default=AccountRequestStatus.wachtend, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    beoordeeld_op = Column(DateTime, nullable=True)


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)
    gebruikt_op = Column(DateTime, nullable=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=True)
    account_request_id = Column(Integer, ForeignKey("account_requests.id"), nullable=True)

    member = relationship("Member", back_populates="invitations")
    account_request = relationship("AccountRequest")


class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, index=True)
    naam = Column(String, nullable=False)
    start_datum = Column(Date, nullable=False)
    eind_datum = Column(Date, nullable=False)
    actief = Column(Boolean, default=False, nullable=False)

    club_evenings = relationship("ClubEvening", back_populates="season")


class ClubEvening(Base):
    __tablename__ = "club_evenings"

    id = Column(Integer, primary_key=True, index=True)
    naam = Column(String, nullable=True, default="")
    datum = Column(Date, nullable=False)
    type = Column(String, nullable=False, default=EveningType.clubavond)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)

    season = relationship("Season", back_populates="club_evenings")
    registrations = relationship("Registration", back_populates="evening")


class FixedPartnership(Base):
    __tablename__ = "fixed_partnerships"

    id = Column(Integer, primary_key=True, index=True)
    person1_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    person2_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    start_datum = Column(Date, nullable=False)
    eind_datum = Column(Date, nullable=True)
    scope = Column(String, default=PartnershipScope.all, nullable=False)

    person1 = relationship("Member", foreign_keys=[person1_id])
    person2 = relationship("Member", foreign_keys=[person2_id])


class EmailRoleAssignment(Base):
    __tablename__ = "email_role_assignments"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False, default=MemberRole.lid)
    aangemaakt_op = Column(DateTime, server_default=func.now(), nullable=False)


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    evening_id = Column(Integer, ForeignKey("club_evenings.id"), nullable=False)
    person1_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    person2_id = Column(Integer, ForeignKey("members.id"), nullable=True)
    type = Column(String, nullable=False)
    status = Column(String, default=RegistrationStatus.aangemeld, nullable=False)
    substitute_name = Column(Text, nullable=True)
    available_person_id = Column(Integer, ForeignKey("members.id"), nullable=True)
    combo_partner_reg_id = Column(
        Integer, ForeignKey("registrations.id"), nullable=True
    )
    aangemeld_op = Column(DateTime, server_default=func.now(), nullable=False)
    gewijzigd_op = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    evening = relationship("ClubEvening", back_populates="registrations")
    person1 = relationship(
        "Member",
        foreign_keys=[person1_id],
        back_populates="registrations_as_person1",
    )
    person2 = relationship(
        "Member",
        foreign_keys=[person2_id],
        back_populates="registrations_as_person2",
    )
    available_person = relationship("Member", foreign_keys=[available_person_id])
    combo_partner_reg = relationship(
        "Registration",
        foreign_keys=[combo_partner_reg_id],
        remote_side="Registration.id",
    )
