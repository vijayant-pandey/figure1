Alembic tips

# Creating an enum
REF: https://docs.sqlalchemy.org/en/14/dialects/postgresql.html#sqlalchemy.dialects.postgresql.ENUM.create

    postgresql.ENUM.create(postgresql.ENUM('CommentRepliesLikes', 'Paging', 'Follow', 'SavedCase', 'WeeklySummary', name='activitynotificationcategories'), bind=op.get_bind())
    op.add_column('r_communication_groups', sa.Column('communication_group_category', postgresql.ENUM(name='activitynotificationcategories'), nullable=True))

To downgrade:

    op.drop_column('r_communication_groups', 'communication_group_category')
    postgresql.ENUM.drop(postgresql.ENUM(name='activitynotificationcategories'), bind=op.get_bind())