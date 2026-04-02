"""Add Promo Card values

Revision ID: aa835b78b8ad
Revises: 0211f8580453
Create Date: 2021-08-12 19:19:46.943621

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'aa835b78b8ad'
down_revision = '0211f8580453'
branch_labels = None
depends_on = None


def upgrade():
    op.sync_enum_values('public', 'casetype', ['CLINICAL_MOMENTS', 'CME', 'QUIZ', 'QUIZ_SERIES', 'STATIC'], ['CLINICAL_MOMENTS', 'CME', 'PROMO_CARD', 'QUIZ', 'QUIZ_SERIES', 'STATIC'])
    op.sync_enum_values('public', 'contenttype', ['CME_HUB_CARD', 'CONCLUSION', 'CONTENT', 'COVER', 'FEED_CARD', 'QUIZ', 'QUIZ_SERIES', 'QUIZ_SUMMARY'], ['CME_HUB_CARD', 'CONCLUSION', 'CONTENT', 'COVER', 'FEED_CARD', 'PROMO_CARD', 'QUIZ', 'QUIZ_SERIES', 'QUIZ_SUMMARY'])

    op.add_column('c_features', sa.Column('dismiss_button', sa.Boolean(), nullable=True))
    op.execute("UPDATE c_features SET dismiss_button=false")
    op.alter_column('c_features', 'dismiss_button', nullable=False)

    op.add_column('c_features', sa.Column('dismiss_on_click', sa.Boolean(), nullable=True))
    op.execute("UPDATE c_features SET dismiss_on_click=false")
    op.alter_column('c_features', 'dismiss_on_click', nullable=False)

    op.add_column('c_features', sa.Column('show_in_mobile', sa.Boolean(), nullable=True))
    op.execute("UPDATE c_features SET show_in_mobile=true")
    op.alter_column('c_features', 'show_in_mobile', nullable=False)

    op.add_column('c_features', sa.Column('show_in_web', sa.Boolean(), nullable=True))
    op.execute("UPDATE c_features SET show_in_web=true")
    op.alter_column('c_features', 'show_in_web', nullable=False)


def downgrade():
    op.drop_column('c_features', 'show_in_web')
    op.drop_column('c_features', 'show_in_mobile')
    op.drop_column('c_features', 'dismiss_on_click')
    op.drop_column('c_features', 'dismiss_button')

    op.sync_enum_values('public', 'contenttype', ['CME_HUB_CARD', 'CONCLUSION', 'CONTENT', 'COVER', 'FEED_CARD', 'PROMO_CARD', 'QUIZ', 'QUIZ_SERIES', 'QUIZ_SUMMARY'], ['CME_HUB_CARD', 'CONCLUSION', 'CONTENT', 'COVER', 'FEED_CARD', 'QUIZ', 'QUIZ_SERIES', 'QUIZ_SUMMARY'])
    op.sync_enum_values('public', 'casetype', ['CLINICAL_MOMENTS', 'CME', 'PROMO_CARD', 'QUIZ', 'QUIZ_SERIES', 'STATIC'], ['CLINICAL_MOMENTS', 'CME', 'QUIZ', 'QUIZ_SERIES', 'STATIC'])
