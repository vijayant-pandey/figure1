"""Add comment state

Revision ID: a2d65d4e4ad5
Revises: c0462c65cf9c
Create Date: 2021-05-31 18:43:03.319838

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a2d65d4e4ad5'
down_revision = 'c0462c65cf9c'
branch_labels = None
depends_on = None


def upgrade():
    op.sync_enum_values('public', 'commentstate', ['ALERTED', 'APPROVED', 'DELETED', 'FLAGGED', 'PENDING_APPROVAL', 'REJECTED', 'REPORTED'], ['ALERTED', 'APPROVED', 'DELETED', 'FLAGGED', 'PENDING_APPROVAL', 'PENDING_APPROVAL_FLAGGED', 'REJECTED', 'REPORTED'])


def downgrade():
    op.sync_enum_values('public', 'commentstate', ['ALERTED', 'APPROVED', 'DELETED', 'FLAGGED', 'PENDING_APPROVAL', 'PENDING_APPROVAL_FLAGGED', 'REJECTED', 'REPORTED'], ['ALERTED', 'APPROVED', 'DELETED', 'FLAGGED', 'PENDING_APPROVAL', 'REJECTED', 'REPORTED'])
