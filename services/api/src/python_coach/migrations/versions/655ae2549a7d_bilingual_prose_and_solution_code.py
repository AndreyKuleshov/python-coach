"""bilingual prose and solution_code

Moves learner-facing prose (lesson title/body_md, exercise title/statement_md)
out of the base tables into per-locale side tables, and adds an optional hidden
`solution_code` column on `exercise`. Existing single-locale rows are migrated
into 'en' translation rows (then mirrored to 'ru' via fallback) so an already
seeded DB is not silently emptied.

Revision ID: 655ae2549a7d
Revises: 115ed2b5049d
Create Date: 2026-06-16 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = '655ae2549a7d'
down_revision: str | None = '115ed2b5049d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New optional hidden reference solution (never exposed by the API).
    op.add_column('exercise', sa.Column('solution_code', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    op.create_table(
        'lesson_translation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lesson_id', sa.Integer(), nullable=False),
        sa.Column('locale', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('body_md', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['lesson_id'], ['lesson.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lesson_id', 'locale', name='uq_lesson_translation_locale'),
    )
    op.create_index(op.f('ix_lesson_translation_lesson_id'), 'lesson_translation', ['lesson_id'], unique=False)
    op.create_index(op.f('ix_lesson_translation_locale'), 'lesson_translation', ['locale'], unique=False)

    op.create_table(
        'exercise_translation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exercise_id', sa.Integer(), nullable=False),
        sa.Column('locale', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('statement_md', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercise.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exercise_id', 'locale', name='uq_exercise_translation_locale'),
    )
    op.create_index(op.f('ix_exercise_translation_exercise_id'), 'exercise_translation', ['exercise_id'], unique=False)
    op.create_index(op.f('ix_exercise_translation_locale'), 'exercise_translation', ['locale'], unique=False)

    # Migrate existing single-locale prose into en + ru translation rows so a
    # previously seeded DB keeps its content (ru mirrors en until re-authored).
    for locale in ('en', 'ru'):
        op.execute(
            sa.text(
                "INSERT INTO lesson_translation (lesson_id, locale, title, body_md) "
                "SELECT id, :loc, title, body_md FROM lesson"
            ).bindparams(loc=locale)
        )
        op.execute(
            sa.text(
                "INSERT INTO exercise_translation (exercise_id, locale, title, statement_md) "
                "SELECT id, :loc, title, statement_md FROM exercise"
            ).bindparams(loc=locale)
        )

    op.drop_column('lesson', 'title')
    op.drop_column('lesson', 'body_md')
    op.drop_column('exercise', 'title')
    op.drop_column('exercise', 'statement_md')


def downgrade() -> None:
    op.add_column('lesson', sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.add_column('lesson', sa.Column('body_md', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.add_column('exercise', sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.add_column('exercise', sa.Column('statement_md', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))

    # Restore prose from the 'en' translation (best-effort) before dropping tables.
    op.execute(sa.text(
        "UPDATE lesson SET title = lt.title, body_md = lt.body_md "
        "FROM lesson_translation lt WHERE lt.lesson_id = lesson.id AND lt.locale = 'en'"
    ))
    op.execute(sa.text(
        "UPDATE exercise SET title = et.title, statement_md = et.statement_md "
        "FROM exercise_translation et WHERE et.exercise_id = exercise.id AND et.locale = 'en'"
    ))

    op.drop_index(op.f('ix_exercise_translation_locale'), table_name='exercise_translation')
    op.drop_index(op.f('ix_exercise_translation_exercise_id'), table_name='exercise_translation')
    op.drop_table('exercise_translation')
    op.drop_index(op.f('ix_lesson_translation_locale'), table_name='lesson_translation')
    op.drop_index(op.f('ix_lesson_translation_lesson_id'), table_name='lesson_translation')
    op.drop_table('lesson_translation')
    op.drop_column('exercise', 'solution_code')
