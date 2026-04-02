"""Add columns for multiple verification photos


Revision ID: 4c16469e4fdf
Revises: 1d1ce55743d7
Create Date: 2021-11-10 14:07:37.429922

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4c16469e4fdf'
down_revision = '1d1ce55743d7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('u_user_verification', sa.Column('verification_photo2', sa.String(), nullable=True))
    op.add_column('u_user_verification', sa.Column('verification_photo3', sa.String(), nullable=True))
    op.add_column('u_user_verification', sa.Column('verification_photo4', sa.String(), nullable=True))


def downgrade():
    op.drop_column('u_user_verification', 'verification_photo2')
    op.drop_column('u_user_verification', 'verification_photo3')
    op.drop_column('u_user_verification', 'verification_photo4')
