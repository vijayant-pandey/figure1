"""Update legacy_user_queue with comm_prefs_propagated_at


Revision ID: 9327b9ff4847
Revises: 4eb5e5437580
Create Date: 2021-06-22 15:40:06.191449

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9327b9ff4847'
down_revision = '4eb5e5437580'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('q_legacy_user_queue', sa.Column('comm_prefs_propagated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('q_legacy_user_queue', 'comm_prefs_propagated_at')
