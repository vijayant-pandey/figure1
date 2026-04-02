"""Add onboarding state

Revision ID: 3df6de4b7338
Revises: 4c16469e4fdf
Create Date: 2021-11-15 14:46:07.065233

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3df6de4b7338'
down_revision = '4c16469e4fdf'
branch_labels = None
depends_on = None


def upgrade():
    postgresql.ENUM.create(postgresql.ENUM('COUNTRY', 'USA_INFORMATION', 'INFORMATION', 'VERIFICATION', 'USERNAME', 'COMPLETED', name='onboardingstate'), bind=op.get_bind())
    op.add_column('u_user_state', sa.Column('onboarding_state', postgresql.ENUM(name='onboardingstate'), nullable=True))


def downgrade():
    op.drop_column('u_user_state', 'onboarding_state')
    postgresql.ENUM.drop(postgresql.ENUM(name='onboardingstate'), bind=op.get_bind())
