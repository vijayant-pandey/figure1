"""Add GroupFeed table

Revision ID: 5d4092dc5525
Revises: 0d5d43500318
Create Date: 2022-01-07 16:15:25.696892

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5d4092dc5525'
down_revision = '0d5d43500318'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('f_group_feed',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('feed_type_uuid', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_uuid', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('specialty_uuids', sa.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('filter_query', sa.JSON(), nullable=True),
        sa.Column('sort_fields', sa.JSON(), nullable=True),
        sa.Column('expire_query', sa.JSON(), nullable=True),
        sa.Column('state_filter', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('hidden', sa.Boolean(), nullable=False),
        sa.Column('language', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['group_uuid'], ['g_groups.group_uuid'], name=op.f('fk_f_group_feed_group_uuid_g_groups')),
        sa.PrimaryKeyConstraint('feed_type_uuid', name=op.f('pk_f_group_feed'))
    )
    op.create_index(op.f('ix_f_group_feed_created_at'), 'f_group_feed', ['created_at'], unique=False)
    op.create_index(op.f('ix_f_group_feed_deleted_at'), 'f_group_feed', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_f_group_feed_label'), 'f_group_feed', ['label'], unique=True)
    op.create_index(op.f('ix_f_group_feed_updated_at'), 'f_group_feed', ['updated_at'], unique=False)
    op.sync_enum_values('public', 'feedkind', ['EVERYTHING', 'MADE_FOR_YOU', 'PREVIEW', 'SEARCH', 'TOPIC'], ['EVERYTHING', 'GROUP', 'MADE_FOR_YOU', 'SEARCH', 'TOPIC'])


def downgrade():
    op.drop_index(op.f('ix_f_group_feed_updated_at'), table_name='f_group_feed')
    op.drop_index(op.f('ix_f_group_feed_label'), table_name='f_group_feed')
    op.drop_index(op.f('ix_f_group_feed_deleted_at'), table_name='f_group_feed')
    op.drop_index(op.f('ix_f_group_feed_created_at'), table_name='f_group_feed')
    op.drop_table('f_group_feed')
