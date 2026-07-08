"""
Schemasynchronisatie bij het opstarten.

De SQLAlchemy-modellen (app/models.py) zijn de bron van waarheid: ontbrekende
tabellen en kolommen worden hier automatisch aangevuld via Alembic
batch-operaties (SQLite-compatibel). Dit vervangt de eerdere hardgecodeerde
lijst ALTER TABLE-statements in main.py. De map alembic/versions blijft
beschikbaar voor handmatige (data)migraties.
"""
import enum
import logging
from typing import Optional

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect as sa_inspect

from app.database import Base

logger = logging.getLogger(__name__)


def sync_schema(engine) -> None:
    """Maak ontbrekende tabellen aan en vul ontbrekende kolommen aan vanuit de modellen."""
    Base.metadata.create_all(bind=engine)

    insp = sa_inspect(engine)
    for table in Base.metadata.sorted_tables:
        bestaande = {c["name"] for c in insp.get_columns(table.name)}
        ontbrekend = [col for col in table.columns if col.name not in bestaande]
        if not ontbrekend:
            continue
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            # Kolommen worden zonder FK/unique-constraints toegevoegd:
            # SQLite ondersteunt die niet via ALTER TABLE ADD COLUMN.
            with op.batch_alter_table(table.name) as batch_op:
                for col in ontbrekend:
                    default = _constante_default(col)
                    nullable = col.nullable
                    if not nullable and default is None:
                        logger.warning(
                            "%s.%s: NOT NULL zonder constante default — toegevoegd als nullable",
                            table.name, col.name,
                        )
                        nullable = True
                    batch_op.add_column(
                        sa.Column(col.name, col.type, nullable=nullable, server_default=default)
                    )
        logger.info("%s: kolommen toegevoegd: %s", table.name, [c.name for c in ontbrekend])

    _fix_bericht_nullability(engine)


def _constante_default(col: sa.Column) -> Optional[str]:
    """String-literal voor de kolomdefault, of None als er geen constante default is."""
    if col.server_default is not None:
        arg = getattr(col.server_default, "arg", None)
        return arg if isinstance(arg, str) else None
    d = col.default
    if d is not None and getattr(d, "is_scalar", False):
        val = d.arg
        if isinstance(val, enum.Enum):
            val = val.value
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, (int, float, str)):
            return str(val)
    return None


def _fix_bericht_nullability(engine) -> None:
    """Legacy-fix: berichten.ontvanger_id en berichten.tekst waren ooit NOT NULL."""
    try:
        insp = sa_inspect(engine)
        if "berichten" not in insp.get_table_names():
            return
        cols = {c["name"]: c for c in insp.get_columns("berichten")}
        fix_ontvanger = not cols.get("ontvanger_id", {}).get("nullable", True)
        fix_tekst = not cols.get("tekst", {}).get("nullable", True)
        if not fix_ontvanger and not fix_tekst:
            return

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            with op.batch_alter_table("berichten", recreate="auto") as batch_op:
                if fix_ontvanger:
                    batch_op.alter_column("ontvanger_id", existing_type=sa.Integer(), nullable=True)
                if fix_tekst:
                    batch_op.alter_column("tekst", existing_type=sa.Text(), nullable=True)
        logger.info("berichten: ontvanger_id/tekst nullable gemaakt via batch migratie")
    except Exception as e:
        logger.warning("Fix nullable kolommen mislukt: %s", e)
