"""Update legacy case

Revision ID: fe72a4a557a0
Revises: e8327692d1b2
Create Date: 2021-05-11 19:33:15.897660

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fe72a4a557a0'
down_revision = ('af29ffc38051', 'aaa205e85de0')
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('c_legacy_case', sa.Column('is_quiz', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('c_legacy_case', 'is_quiz')
