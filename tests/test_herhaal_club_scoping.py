"""
Regressietest: een "voor onbepaalde tijd" herhaalaanmelding (/aanmelden/{id}/herhaal
met alles=on zonder einddatum, en de afgeleide RecurringRegistration) mag alleen
gelden voor evenementen van dezelfde club als waar de aanmelding is gestart —
niet voor andere clubs waar het lid ook lid van is.
"""
from datetime import date, timedelta

from tests.conftest import make_member, make_season


def make_club(db_session, naam="BC Test"):
    from app.models import Club
    club = Club(naam=naam)
    db_session.add(club)
    db_session.commit()
    db_session.refresh(club)
    return club


def make_member_club(db_session, member_id, club_id, role="lid"):
    from app.models import MemberClub
    mc = MemberClub(member_id=member_id, club_id=club_id, role=role)
    db_session.add(mc)
    db_session.commit()
    return mc


def make_evening(db_session, season_id, club_id=None, ev_type="clubavond", datum=None):
    from app.models import ClubEvening
    if datum is None:
        datum = date.today() + timedelta(days=7)
    ev = ClubEvening(datum=datum, type=ev_type, season_id=season_id, club_id=club_id)
    db_session.add(ev)
    db_session.commit()
    db_session.refresh(ev)
    return ev


def _no_csrf(app):
    from app.csrf import require_csrf
    app.dependency_overrides[require_csrf] = lambda: None


def _set_auth(app, member):
    from app.auth import get_current_user, require_auth
    _no_csrf(app)
    app.dependency_overrides[require_auth] = lambda: member
    app.dependency_overrides[get_current_user] = lambda: member


async def test_herhaal_alles_registreert_niet_op_andere_club(client, db_session):
    from app.main import app
    from app.models import RecurringRegistration, Registration

    club_a = make_club(db_session, naam="Club A")
    club_b = make_club(db_session, naam="Club B")
    lid = make_member(db_session, lidnummer="SCOPE001")
    make_member_club(db_session, lid.id, club_a.id)
    make_member_club(db_session, lid.id, club_b.id)
    season = make_season(db_session)

    bron = make_evening(db_session, season.id, club_id=club_a.id,
                         datum=date.today() + timedelta(days=7))
    ander_in_a = make_evening(db_session, season.id, club_id=club_a.id,
                               datum=date.today() + timedelta(days=14))
    ander_in_b = make_evening(db_session, season.id, club_id=club_b.id,
                               datum=date.today() + timedelta(days=10))

    _set_auth(app, lid)
    response = await client.post(f"/aanmelden/{bron.id}/herhaal", data={"alles": "on"})
    assert response.status_code == 302
    assert "bulk_ok=2" in response.headers["location"]

    regs = db_session.query(Registration).filter(Registration.person1_id == lid.id).all()
    assert {r.evening_id for r in regs} == {bron.id, ander_in_a.id}
    assert ander_in_b.id not in {r.evening_id for r in regs}

    rr = db_session.query(RecurringRegistration).filter(
        RecurringRegistration.member_id == lid.id,
        RecurringRegistration.actief == True,  # noqa: E712
    ).first()
    assert rr is not None
    assert rr.club_id == club_a.id


async def test_apply_recurring_registrations_respecteert_club_id(db_session):
    """Directe unit-test van _apply_recurring_registrations: een herhaalaanmelding
    met een club_id mag niet worden toegepast op een nieuwe avond van een andere club."""
    from app.models import RecurringRegistration, Registration
    from app.routes.admin.avonden import _apply_recurring_registrations

    club_a = make_club(db_session, naam="Club A")
    club_b = make_club(db_session, naam="Club B")
    lid = make_member(db_session, lidnummer="SCOPE002")
    make_member_club(db_session, lid.id, club_a.id)
    make_member_club(db_session, lid.id, club_b.id)
    season = make_season(db_session)

    db_session.add(RecurringRegistration(
        member_id=lid.id, event_type="clubavond", interval=1,
        referentie_datum=date.today(), club_id=club_a.id,
    ))
    db_session.commit()

    nieuwe_avond_b = make_evening(db_session, season.id, club_id=club_b.id,
                                   datum=date.today() + timedelta(days=21))
    _apply_recurring_registrations(db_session, nieuwe_avond_b)
    db_session.commit()
    assert db_session.query(Registration).filter(
        Registration.person1_id == lid.id, Registration.evening_id == nieuwe_avond_b.id
    ).count() == 0

    nieuwe_avond_a = make_evening(db_session, season.id, club_id=club_a.id,
                                   datum=date.today() + timedelta(days=28))
    _apply_recurring_registrations(db_session, nieuwe_avond_a)
    db_session.commit()
    assert db_session.query(Registration).filter(
        Registration.person1_id == lid.id, Registration.evening_id == nieuwe_avond_a.id
    ).count() == 1


async def test_legacy_recurring_registration_zonder_club_id_blijft_breed_gelden(db_session):
    """Backwards compatible: bestaande herhaalaanmeldingen van vóór deze fix
    (club_id is NULL) blijven voor alle clubs van het lid gelden."""
    from app.models import RecurringRegistration, Registration
    from app.routes.admin.avonden import _apply_recurring_registrations

    club_a = make_club(db_session, naam="Club A")
    club_b = make_club(db_session, naam="Club B")
    lid = make_member(db_session, lidnummer="SCOPE003")
    make_member_club(db_session, lid.id, club_a.id)
    make_member_club(db_session, lid.id, club_b.id)
    season = make_season(db_session)

    db_session.add(RecurringRegistration(
        member_id=lid.id, event_type="clubavond", interval=1,
        referentie_datum=date.today(), club_id=None,
    ))
    db_session.commit()

    nieuwe_avond_b = make_evening(db_session, season.id, club_id=club_b.id,
                                   datum=date.today() + timedelta(days=21))
    _apply_recurring_registrations(db_session, nieuwe_avond_b)
    db_session.commit()
    assert db_session.query(Registration).filter(
        Registration.person1_id == lid.id, Registration.evening_id == nieuwe_avond_b.id
    ).count() == 1
