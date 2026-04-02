from sqlalchemy import Column, INTEGER
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateTime


class CaseAnalytics(Base, HasCreateUpdateTime):
    """
    Case analytics tracks some basic case stats so we don't have to manually generate them everytime we refresh.
    Not using an FK is intentional since we do not want to directly tie anything here to the rest of the data model.

    case_uuid is the case identifier
    trend_score can be 0 or a positive integer, it is updated to reflect the popularity of a case
    total_comments are all of the comments on a case, since a given case can include multiple content items,
                   it includes all of the comments on all of the content items
    unverified_views are counted when a case has been served. The user may or may not have looked at it.
    """
    __tablename__ = 'a_case_analytics'
    case_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    trend_score = Column(INTEGER, default=0, nullable=True)
    total_comments = Column(INTEGER, default=0, nullable=True)
    unverified_views = Column(INTEGER, default=0, nullable=True)

    @staticmethod
    def add_unverified_view(case_uuid, session, skip_commit=False):
        ca = session.query(CaseAnalytics).get(case_uuid)
        if not ca:
            ca = CaseAnalytics()
            ca.case_uuid = case_uuid
            session.add(ca)
            session.flush()

        ca.unverified_views = CaseAnalytics.unverified_views + 1

        if skip_commit:
            return ca
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return ca


class CampaignAnalytics(Base, HasCreateUpdateTime):
    """
    Campaign Analytics tracks per target group at the most granular. Tactics and campaigns can be aggregated on top.

    target_uuid is a specialty_tree uuid - it represents the target group that is hit for a specific view.
    tactic_uuid is a case_uuid that is created as part of a campaign
    campaign_uuid is a unique identifier for a campaign
    verified_views are taken from mixpanel on a scheduled basis, there is only an increment here if a user has actually
    looked at the tactic.
    unverified_views are counted when a tactic has been served. The user may or may not have looked at it.
    """
    __tablename__ = 'a_campaign_analytics'
    target_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    tactic_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    campaign_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    verified_views = Column(INTEGER, default=0, nullable=True)
    unverified_views = Column(INTEGER, default=0, nullable=True)
