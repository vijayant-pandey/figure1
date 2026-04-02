"""Update case rejection reasons

Revision ID: 6c74440afacc
Revises: 5a04857f6c23
Create Date: 2021-06-04 02:40:09.373488

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6c74440afacc'
down_revision = '5a04857f6c23'
branch_labels = None
depends_on = None


def upgrade():
    op.sync_enum_values('public', 'rejectionreason', ['IDENTIFYING_INFO', 'INAPPROPRIATE_CONTENT', 'INSUFFICIENT_CAPTION', 'NON_CLINICAL_PHOTOS', 'TINEYE', 'UNDERAGE_NUDITY'], ['DELETE_NO_EMAIL', 'INAPPROPRIATE_CONTENT', 'INAPPROPRIATE_PAGING', 'NEED_CLINICAL_INFO', 'NON_CLINICAL_PHOTOS', 'NOT_DIRECT_CARE', 'SELFIE', 'SUSPECTED_HOMEWORK', 'TINEYE', 'UNDERAGE_NUDITY', 'UNSUPPORTED_LANGUAGE'])


def downgrade():
    op.sync_enum_values('public', 'rejectionreason', ['DELETE_NO_EMAIL', 'INAPPROPRIATE_CONTENT', 'INAPPROPRIATE_PAGING', 'NEED_CLINICAL_INFO', 'NON_CLINICAL_PHOTOS', 'NOT_DIRECT_CARE', 'SELFIE', 'SUSPECTED_HOMEWORK', 'TINEYE', 'UNDERAGE_NUDITY', 'UNSUPPORTED_LANGUAGE'], ['IDENTIFYING_INFO', 'INAPPROPRIATE_CONTENT', 'INSUFFICIENT_CAPTION', 'NON_CLINICAL_PHOTOS', 'TINEYE', 'UNDERAGE_NUDITY'])
