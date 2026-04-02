"""Add unsupported case state

Revision ID: aaa205e85de0
Revises: ab476aa5bda6
Create Date: 2021-05-10 17:41:41.914581

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'aaa205e85de0'
down_revision = 'ab476aa5bda6'
branch_labels = None
depends_on = None


def upgrade():
    enum_name = 'casestate'
    new_values = ['APPROVED', 'ARCHIVED', 'DELETED', 'DRAFT', 'EDIT_SUGGESTED', 'FLAGGED', 'FLAGGED_TAGGER', 'UNSUPPORTED', 'PENDING_APPROVAL', 'PENDING_NLP', 'PENDING_TAGGING', 'REJECTED', 'REPORTED', 'SC_APPROVED', 'SC_ARCHIVED', 'SC_DRAFT', 'SC_REVIEW']

    new_enum = sa.Enum(*new_values, name=enum_name)
    enum_name_tmp = enum_name + "_tmp"
    op.execute(f'ALTER TYPE {enum_name} RENAME TO {enum_name_tmp}')
    new_enum.create(op.get_bind())
    op.execute(f'ALTER TABLE c_case ALTER COLUMN state TYPE {enum_name} USING state::text::{enum_name}')
    op.execute(f'ALTER TABLE h_case_history ALTER COLUMN case_state TYPE {enum_name} USING case_state::text::{enum_name}')
    op.execute(f'DROP TYPE {enum_name_tmp}')

    op.add_column('c_legacy_case', sa.Column('is_grand_rounds', sa.Boolean(), nullable=True))
    op.add_column('c_legacy_case', sa.Column('is_image_series', sa.Boolean(), nullable=True))
    op.add_column('c_legacy_case', sa.Column('is_cm_cme', sa.Boolean(), nullable=True))
    op.add_column('c_legacy_case', sa.Column('external_link', sa.Text(), nullable=True))
    op.add_column('c_legacy_case', sa.Column('external_link_text', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('c_legacy_case', 'external_link_text')
    op.drop_column('c_legacy_case', 'external_link')
    op.drop_column('c_legacy_case', 'is_cm_cme')
    op.drop_column('c_legacy_case', 'is_image_series')
    op.drop_column('c_legacy_case', 'is_grand_rounds')

    enum_name = 'casestate'
    new_values = ['APPROVED', 'ARCHIVED', 'DELETED', 'DRAFT', 'EDIT_SUGGESTED', 'FLAGGED', 'FLAGGED_TAGGER', 'PC_APPROVED', 'PC_ARCHIVED', 'PC_DRAFT', 'PC_REVIEW', 'PENDING_APPROVAL', 'PENDING_NLP', 'PENDING_TAGGING', 'REJECTED', 'REPORTED', 'SC_APPROVED', 'SC_ARCHIVED', 'SC_DRAFT', 'SC_REVIEW']

    new_enum = sa.Enum(*new_values, name=enum_name)
    enum_name_tmp = enum_name + "_tmp"
    op.execute(f'ALTER TYPE {enum_name} RENAME TO {enum_name_tmp}')
    new_enum.create(op.get_bind())
    op.execute(f"UPDATE c_case SET state='ARCHIVED' WHERE state='UNSUPPORTED'")
    op.execute(f'ALTER TABLE c_case ALTER COLUMN state TYPE {enum_name} USING state::text::{enum_name}')
    op.execute(f"UPDATE h_case_history SET case_state='ARCHIVED' WHERE case_state='UNSUPPORTED'")
    op.execute(f'ALTER TABLE h_case_history ALTER COLUMN case_state TYPE {enum_name} USING case_state::text::{enum_name}')
    op.execute(f'DROP TYPE {enum_name_tmp}')
