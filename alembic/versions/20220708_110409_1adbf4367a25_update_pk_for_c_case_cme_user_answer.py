"""Update PK for c_case_cme_user_answer

Revision ID: 1adbf4367a25
Revises: b33f16bd23b6
Create Date: 2022-07-08 11:04:09.851405

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1adbf4367a25'
down_revision = 'b33f16bd23b6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('c_case_cme_user_answer', sa.Column('case_user_answer_uuid',
                                                      postgresql.UUID(as_uuid=True),
                                                      nullable=False,
                                                      server_default=text('uuid_generate_v4()')))
    op.execute("ALTER TABLE c_case_cme_user_answer DROP CONSTRAINT pk_c_case_cme_user_answer")
    op.execute("DROP INDEX IF EXISTS pk_c_case_cme_user_answer")
    op.execute("ALTER TABLE c_case_cme_user_answer ADD PRIMARY KEY (case_user_answer_uuid)")
    op.execute("ALTER TABLE c_case_cme_user_answer RENAME CONSTRAINT c_case_cme_user_answer_pkey TO pk_c_case_cme_user_answer")



def downgrade():
    op.execute("ALTER TABLE c_case_cme_user_answer DROP CONSTRAINT pk_c_case_cme_user_answer")
    op.execute("DROP INDEX IF EXISTS pk_c_case_cme_user_answer")
    op.execute("ALTER TABLE c_case_cme_user_answer ADD PRIMARY KEY (case_uuid, question_uuid)")
    op.execute("ALTER TABLE c_case_cme_user_answer RENAME CONSTRAINT c_case_cme_user_answer_pkey TO pk_c_case_cme_user_answer")
    op.drop_column('c_case_cme_user_answer', 'case_user_answer_uuid')
