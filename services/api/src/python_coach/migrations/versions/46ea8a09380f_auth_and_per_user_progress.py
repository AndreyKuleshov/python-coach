"""auth and per-user progress

Adds the `user` table (email login + Argon2 hash + email-confirmed flag) and
makes progress/submissions per-account by adding a non-null `user_id` FK to
both. Progress uniqueness moves from (exercise_id) to (user_id, exercise_id).

Existing progress/submission rows are throwaway pre-auth test data with no
owning user, so this migration CLEARS them before adding the non-null FK
(documented in README). Lessons/exercises/tests are untouched.

Revision ID: 46ea8a09380f
Revises: 655ae2549a7d
Create Date: 2026-06-16 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = '46ea8a09380f'
down_revision: str | None = '655ae2549a7d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('password_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_email_confirmed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)

    # Pre-auth progress/submission rows have no owning user; clear them before
    # adding the non-null user_id FK (throwaway test data — see README).
    op.execute(sa.text('DELETE FROM progress'))
    op.execute(sa.text('DELETE FROM submission'))

    # submission.user_id
    op.add_column('submission', sa.Column('user_id', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_submission_user_id'), 'submission', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_submission_user_id', 'submission', 'user', ['user_id'], ['id'], ondelete='CASCADE'
    )

    # progress.user_id + new (user_id, exercise_id) uniqueness
    op.add_column('progress', sa.Column('user_id', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_progress_user_id'), 'progress', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_progress_user_id', 'progress', 'user', ['user_id'], ['id'], ondelete='CASCADE'
    )
    # Drop the old single-column unique index; exercise_id is now non-unique.
    op.drop_index(op.f('ix_progress_exercise_id'), table_name='progress')
    op.create_index(op.f('ix_progress_exercise_id'), 'progress', ['exercise_id'], unique=False)
    op.create_unique_constraint(
        'uq_progress_user_exercise', 'progress', ['user_id', 'exercise_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_progress_user_exercise', 'progress', type_='unique')
    op.drop_index(op.f('ix_progress_exercise_id'), table_name='progress')
    op.create_index(op.f('ix_progress_exercise_id'), 'progress', ['exercise_id'], unique=True)
    op.drop_constraint('fk_progress_user_id', 'progress', type_='foreignkey')
    op.drop_index(op.f('ix_progress_user_id'), table_name='progress')
    op.drop_column('progress', 'user_id')

    op.drop_constraint('fk_submission_user_id', 'submission', type_='foreignkey')
    op.drop_index(op.f('ix_submission_user_id'), table_name='submission')
    op.drop_column('submission', 'user_id')

    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
