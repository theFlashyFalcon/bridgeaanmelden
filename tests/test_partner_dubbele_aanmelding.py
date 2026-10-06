"""
Regressietests voor een gemeld bug: een lid dat als partner is opgegeven zag
niet dat hij al aangemeld was, en kon zichzelf (met partner) nog eens
aanmelden. Dit leidde tot een dubbel paar voor dezelfde avond.

De aanmelding koppelt nu de partner aan diens echte lid-account (person2_id)
als die naam in de ledenlijst/leden-tabel bekend is, zodat het systeem weet
dat beide personen al aangemeld zijn.
"""
from datetime import date, timedelta

from tests.conftest import make_member, make_season


def make_evening(db_session, season_id, datum=None, ev_type="clubavond"):
    from app.models import ClubEvening

    if datum is None:
        datum = date.today() + timedelta(days=7)
    evening = ClubEvening(datum=datum, type=ev_type, season_id=season_id)
    db_session.add(evening)
    db_session.commit()
    db_session.refresh(evening)
    return evening


def _set_auth(app, member=None):
    """Override auth-dependencies op de FastAPI-app voor de duur van één test."""
    from app.auth import get_current_user, require_auth
    from app.csrf import require_csrf

    app.dependency_overrides[require_csrf] = lambda: None
    if member is not None:
        app.dependency_overrides[require_auth] = lambda: member
        app.dependency_overrides[get_current_user] = lambda: member


async def test_partner_wordt_gekoppeld_aan_lid_account(client, db_session):
    """Aanmelden met een partner die ook een lid-account heeft, koppelt person2_id."""
    from app.main import app
    from app.models import Registration

    a = make_member(db_session, voornaam="Anna", achternaam="Jansen", lidnummer="PD01")
    b = make_member(db_session, voornaam="Jan", achternaam="de Vries", lidnummer="PD02")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)

    _set_auth(app, member=a)
    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "Jan", "partner_achternaam": "de Vries", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    reg = db_session.query(Registration).filter(Registration.person1_id == a.id).first()
    assert reg is not None
    assert reg.person2_id == b.id


async def test_partner_kan_zichzelf_niet_dubbel_aanmelden(client, db_session):
    """De partner die al is opgegeven kan zichzelf niet nog eens (met partner) aanmelden."""
    from app.main import app
    from app.models import Registration

    a = make_member(db_session, voornaam="Anna", achternaam="Jansen", lidnummer="PD03")
    b = make_member(db_session, voornaam="Jan", achternaam="de Vries", lidnummer="PD04")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)

    # Anna meldt zich aan met Jan als partner.
    _set_auth(app, member=a)
    await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "Jan", "partner_achternaam": "de Vries", "_csrf_token": "x"},
    )

    # Jan probeert zichzelf (en Anna) ook nog eens aan te melden.
    _set_auth(app, member=b)
    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "Anna", "partner_achternaam": "Jansen", "_csrf_token": "x"},
    )
    assert response.status_code == 302
    assert "fout=al_aangemeld_partner" in response.headers["location"]

    # Er is nog maar één registratie voor deze avond, geen dubbel paar.
    regs = db_session.query(Registration).filter(Registration.evening_id == evening.id).all()
    assert len(regs) == 1
    assert regs[0].person1_id == a.id
    assert regs[0].person2_id == b.id


async def test_partner_ziet_al_aangemeld_op_aanmeldpagina(client, db_session):
    """GET /aanmelden/{id} toont de partner dat hij al aangemeld is."""
    from app.main import app

    a = make_member(db_session, voornaam="Anna", achternaam="Jansen", lidnummer="PD05")
    b = make_member(db_session, voornaam="Jan", achternaam="de Vries", lidnummer="PD06")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)

    _set_auth(app, member=a)
    await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "Jan", "partner_achternaam": "de Vries", "_csrf_token": "x"},
    )

    _set_auth(app, member=b)
    response = await client.get(f"/aanmelden/{evening.id}")
    assert response.status_code == 200
    assert "Anna Jansen" in response.text
    assert "nog niet aangemeld" not in response.text.lower()


async def test_partner_kan_gezamenlijke_aanmelding_zelf_afmelden(client, db_session):
    """De opgegeven partner kan de gedeelde aanmelding zelf annuleren."""
    from app.main import app
    from app.models import Registration, RegistrationStatus

    a = make_member(db_session, voornaam="Anna", achternaam="Jansen", lidnummer="PD07")
    b = make_member(db_session, voornaam="Jan", achternaam="de Vries", lidnummer="PD08")
    season = make_season(db_session)
    evening = make_evening(db_session, season.id)

    _set_auth(app, member=a)
    await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "Jan", "partner_achternaam": "de Vries", "_csrf_token": "x"},
    )

    _set_auth(app, member=b)
    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"action": "afmelden", "_csrf_token": "x"},
    )
    assert response.status_code == 302

    reg = db_session.query(Registration).filter(Registration.evening_id == evening.id).first()
    assert reg.status == RegistrationStatus.afgemeld

    # Na het afmelden kan Jan zichzelf weer gewoon (opnieuw) aanmelden.
    response = await client.post(
        f"/aanmelden/{evening.id}",
        data={"partner_voornaam": "", "partner_achternaam": "", "_csrf_token": "x"},
    )
    assert response.status_code == 302
    assert "fout=al_aangemeld_partner" not in response.headers["location"]
