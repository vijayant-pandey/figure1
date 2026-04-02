"""Remove FeedKind.Preview

Revision ID: 74a29d99db3f
Revises: 05e77d2bc322
Create Date: 2021-12-09 12:00:46.454589

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '74a29d99db3f'
down_revision = '05e77d2bc322'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DELETE FROM f_feed_previews
        WHERE feed_type_uuid IN (SELECT feed_type_uuid FROM f_feed_type WHERE kind = 'PREVIEW')
    """)
    op.execute("DELETE FROM f_feed_type WHERE kind = 'PREVIEW'")


def downgrade():
    pass
