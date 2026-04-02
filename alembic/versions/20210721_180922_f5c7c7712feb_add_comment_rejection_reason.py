"""Add comment rejection_reason

Revision ID: f5c7c7712feb
Revises: 483290660ba8
Create Date: 2021-07-20 18:09:22.445700

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f5c7c7712feb'
down_revision = '483290660ba8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(f"UPDATE a_activity_record SET activity_type='CASE_DELETE' WHERE activity_type='DELETE'")
    op.execute('ALTER TYPE rejectionreason RENAME TO caserejectionreason')

    comment_rejection_reason = sa.Enum('DISRESPECTFUL_PATIENT', 'PRIVACY_ISSUE', 'PERSONAL_QUESTION_COMMENT', 'DISRESPECTFUL_USER', 'UNSUPPORTED', 'PROMOTIONAL', 'UNPROFESSIONAL', 'UNSUPPORTED_LANGUAGE', 'TREATMENT_REFERENCE', 'OFF_TOPIC', 'NO_EMAIL', name='commentrejectionreason')
    comment_rejection_reason.create(op.get_bind())
    op.add_column('c_comment', sa.Column('rejection_reason', comment_rejection_reason, nullable=True))

    op.add_column('a_activity_record', sa.Column('comment_uuid', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(op.f('fk_a_activity_record_comment_uuid_c_comment'), 'a_activity_record', 'c_comment', ['comment_uuid'], ['comment_uuid'])


def downgrade():
    op.drop_constraint(op.f('fk_a_activity_record_comment_uuid_c_comment'), 'a_activity_record', type_='foreignkey')
    op.drop_column('a_activity_record', 'comment_uuid')

    op.drop_column('c_comment', 'rejection_reason')
    postgresql.ENUM(name='commentrejectionreason').drop(op.get_bind())

    op.execute('ALTER TYPE caserejectionreason RENAME TO rejectionreason')
