import uuid
from datetime import datetime, timezone
from typing import TypedDict, Optional, Iterable
from pydantic.types import UUID as UUID_Type
from sqlalchemy import Column, Text, ForeignKey, DateTime, Enum, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session, backref
from . import User, Case, CaseAuthor, Country
from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.types import CampaignState, CaseState
from figure1.exceptions import TacticUpdateError, \
    CampaignException, \
    TacticNotFound, \
    TacticDeleted, \
    TacticInvalidDates


class CampaignDict(TypedDict):
    campaignUuid: str
    name: str
    clientName: str
    state: str
    authorUuid: str
    archivedAt: Optional[datetime]
    archivedByUuid: Optional[str]
    lastUpdate: str
    createdAt: str
    updatedAt: str
    campaignPriority: int
    targetVerification: bool
    isSponsored: bool


class CampaignCaseDict(TypedDict):
    campaignUuid: str
    caseUuid: str
    moderatorUuid: str
    startDate: str
    endDate: str
    name: str
    tacticPriority: int


class Campaign(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_campaign"
    campaign_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(Text)
    client_name = Column(Text)
    state = Column(Enum(CampaignState), nullable=False, index=True)
    author_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    archived_at = Column(DateTime(timezone=True), default=None)
    last_update = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))
    archived_by_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    campaign_priority = Column(Integer, default=1, nullable=False)
    is_sponsored = Column(Boolean, default=True, nullable=True)
    target_verification = Column(Boolean)
    target_countries = relationship("CampaignTargetCountry", backref="campaign")
    target_specialties = relationship("CampaignTargetSpecialtyTree", backref="campaign")
    target_languages = relationship("CampaignTargetLanguage", backref="campaign")
    preview_users = relationship("CampaignPreviewUser", backref="campaign")
    cases = relationship("Case", secondary='c_campaign_case', backref=backref("campaign", uselist=False))

    def as_dict(self) -> CampaignDict:
        return {
            'campaignUuid': str(self.campaign_uuid),
            'name': self.name,
            'clientName': self.client_name,
            'state': self.state.name.lower(),
            'authorUuid': str(self.author_uuid),
            'archivedAt': self.archived_at,
            'archivedByUuid': str(self.archived_by_uuid) if self.archived_by_uuid else None,
            'lastUpdate': str(self.last_update),
            'createdAt': str(self.created_at),
            'updatedAt': str(self.updated_at),
            'campaignPriority': self.campaign_priority,
            'targetVerification': self.target_verification,
            'isSponsored': self.is_sponsored,

        }

    @staticmethod
    def create_or_update(session: Session,
                         campaign_uuid=None,
                         name=None,
                         client_name=None,
                         author_uuid=None,
                         is_sponsored=None,
                         campaign_priority: int = None,
                         ):
        if campaign_uuid:
            campaign = session.query(Campaign).get(campaign_uuid)
            if campaign and is_sponsored is not None:
                campaign.is_sponsored = is_sponsored
            if not campaign:
                raise CampaignException(msg=f'Campaign with uuid {campaign_uuid} does not exist')
        else:
            campaign = Campaign()
            campaign.campaign_uuid = uuid.uuid4()
            campaign.state = CampaignState.DRAFT

        if name:
            campaign.name = name
        if client_name:
            campaign.client_name = client_name
        if author_uuid:
            campaign.author_uuid = author_uuid
        if is_sponsored is not None:
            campaign.is_sponsored = is_sponsored
        if campaign_priority is not None:
            campaign.campaign_priority = campaign_priority
        else:
            if campaign.campaign_priority is None:
                campaign.campaign_priority = 0
        session.add(campaign)
        return campaign

    @staticmethod
    def archive_campaign(campaign_uuid,
                         user_uuid,
                         session: Session):
        """
        Archives a campaign and all tactics associated - the campaign must be in ACTIVE state to be archived
        :raises CampaignException:
        :param campaign_uuid:
        :param user_uuid:
        :param session:
        :return: {}
        """
        campaign = session.query(Campaign).get(campaign_uuid)
        if not campaign:
            raise CampaignException(msg=f'Campaign with uuid {campaign_uuid} not found')

        if campaign.state is not CampaignState.ACTIVE:
            raise CampaignException(msg=f'Campaigns can only be archived from ACTIVE state')
        campaign.state = CampaignState.ARCHIVED
        campaign.archived_at = datetime.now(timezone.utc)
        campaign.archived_by_uuid = user_uuid
        campaign.last_update = user_uuid
        session.add(campaign)

    @staticmethod
    def unarchive_campaign(campaign_uuid, user_uuid, session: Session):
        """
        Unarchives a campaign - only valid if the campaign state is ARCHIVED, this sets all campaign cases to SC_DRAFT
        :raises CampaignException:
        :param campaign_uuid:
        :param user_uuid:
        :param session:
        :return:
        """
        campaign = session.query(Campaign).get(campaign_uuid)
        if not campaign:
            raise CampaignException(msg=f'Campaign with uuid {campaign_uuid} not found')

        if campaign.state is not CampaignState.ARCHIVED:
            raise CampaignException(msg=f'Campaign with uuid {campaign_uuid} is not archived')

        CampaignCase.unarchive_campaign_cases(campaign_uuid=campaign_uuid, session=session)
        campaign.state = CampaignState.DRAFT
        campaign.last_update = user_uuid
        session.add(campaign)

    @staticmethod
    def activate_campaign(campaign_uuid: UUID_Type, user_uuid: UUID_Type, session: Session):
        """
        Sets a campaign state to ACTIVE, this is only a valid action if the current state is DRAFT
        :raises CampaignException:
        :param campaign_uuid:
        :param user_uuid:
        :param session:
        :return:
        """
        campaign = session.query(Campaign).get(campaign_uuid)
        if campaign.state is CampaignState.ARCHIVED:
            raise CampaignException(msg='Cannot activate archived campaign, must be unarchived first', return_code=500)
        if campaign.state is not CampaignState.DRAFT:
            raise CampaignException(msg=f'Campaign must be in DRAFT state to be activated')
        campaign.state = CampaignState.ACTIVE
        campaign.last_update = user_uuid
        session.add(campaign)

    @staticmethod
    def update_target_countries(campaign_uuid, country_uuids, session):
        for tc in session.query(CampaignTargetCountry) \
                .filter(CampaignTargetCountry.campaign_uuid == campaign_uuid,
                        CampaignTargetCountry.deleted_at.is_(None)) \
                .all():
            if str(tc.country_uuid) not in country_uuids:
                tc.mark_deleted()

        for country_uuid in country_uuids:
            CampaignTargetCountry.create(campaign_uuid=campaign_uuid,
                                         country_uuid=country_uuid,
                                         session=session,
                                         skip_commit=True)

    @staticmethod
    def update_target_specialties(campaign_uuid, tree_uuids, session):
        for ts in session.query(CampaignTargetSpecialtyTree) \
                .filter(CampaignTargetSpecialtyTree.campaign_uuid == campaign_uuid,
                        CampaignTargetSpecialtyTree.deleted_at.is_(None)) \
                .all():
            if str(ts.tree_uuid) not in tree_uuids:
                ts.mark_deleted()

        for tree_uuid in tree_uuids:
            if tree_uuid:
                CampaignTargetSpecialtyTree.create(campaign_uuid=campaign_uuid,
                                                   tree_uuid=tree_uuid,
                                                   session=session)

    @staticmethod
    def update_target_languages(campaign_uuid, languages, session):
        for tl in session.query(CampaignTargetLanguage) \
                .filter(CampaignTargetLanguage.campaign_uuid == campaign_uuid,
                        CampaignTargetLanguage.deleted_at.is_(None)) \
                .all():
            if tl.language not in languages:
                tl.mark_deleted()

        for language in languages:
            CampaignTargetLanguage.create(campaign_uuid=campaign_uuid,
                                          language=language,
                                          session=session,
                                          skip_commit=True)

    @staticmethod
    def update_target_verification(campaign_uuid, verification, session):
        c = session.query(Campaign).get(campaign_uuid)
        if c:
            c.target_verification = verification


class CampaignTargetCountry(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_campaign_target_country"
    campaign_uuid = Column(UUID(as_uuid=True), ForeignKey(Campaign.campaign_uuid), primary_key=True)
    country_uuid = Column(UUID(as_uuid=True), ForeignKey(Country.country_uuid), primary_key=True)

    country = relationship("Country", uselist=False)

    @staticmethod
    def create(campaign_uuid, country_uuid, session, skip_commit=False):
        c = session.query(CampaignTargetCountry) \
            .filter(CampaignTargetCountry.campaign_uuid == campaign_uuid,
                    CampaignTargetCountry.country_uuid == country_uuid) \
            .one_or_none()
        if c:
            c.deleted_at = None
        else:
            c = CampaignTargetCountry()
            c.campaign_uuid = campaign_uuid
            c.country_uuid = country_uuid
            session.add(c)

        if skip_commit:
            return c

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return c

    def as_dict(self):
        return {
            'campaignUuid': str(self.campaign_uuid),
            'countryUuid': str(self.country_uuid),
        }


class CampaignTargetSpecialtyTree(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_campaign_target_specialty"
    campaign_uuid = Column(UUID(as_uuid=True), ForeignKey(Campaign.campaign_uuid), primary_key=True)
    tree_uuid = Column(UUID(as_uuid=True), primary_key=True)
    tree = relationship("SpecialtyTreeV2",
                        viewonly=True,
                        sync_backref=False,
                        primaryjoin="remote(SpecialtyTreeV2.specialty_uuid)=="
                                    "foreign(CampaignTargetSpecialtyTree.tree_uuid)")

    @staticmethod
    def create(campaign_uuid, tree_uuid, session, skip_commit=False):
        c = session.query(CampaignTargetSpecialtyTree) \
            .filter(CampaignTargetSpecialtyTree.campaign_uuid == campaign_uuid,
                    CampaignTargetSpecialtyTree.tree_uuid == tree_uuid) \
            .one_or_none()
        if c:
            c.deleted_at = None
        else:
            c = CampaignTargetSpecialtyTree()
            c.campaign_uuid = campaign_uuid
            c.tree_uuid = tree_uuid
            session.add(c)
        session.flush()
        return c

    def as_dict(self):
        return {
            'campaignUuid': str(self.campaign_uuid),
            'treeUuid': str(self.tree_uuid),
        }


class CampaignTargetLanguage(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_campaign_target_language"
    campaign_uuid = Column(UUID(as_uuid=True), ForeignKey(Campaign.campaign_uuid), primary_key=True)
    language = Column(Text, nullable=False, primary_key=True)

    @staticmethod
    def create(campaign_uuid, language, session, skip_commit=False):
        c = session.query(CampaignTargetLanguage) \
            .filter(CampaignTargetLanguage.campaign_uuid == campaign_uuid,
                    CampaignTargetLanguage.language == language) \
            .one_or_none()
        if c:
            c.deleted_at = None
        else:
            c = CampaignTargetLanguage()
            c.campaign_uuid = campaign_uuid
            c.language = language
            session.add(c)

        if skip_commit:
            return c

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return c

    def as_dict(self):
        return {
            'campaignUuid': str(self.campaign_uuid),
            'language': self.language,
        }


class CampaignCase(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_campaign_case"
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), primary_key=True)
    campaign_uuid = Column(UUID(as_uuid=True), ForeignKey(Campaign.campaign_uuid), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    name = Column(Text)
    tactic_priority = Column(Integer, nullable=False, default=1)
    moderator_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))

    @staticmethod
    def create_or_update(campaign_uuid,
                         case_uuid,
                         name,
                         moderator_uuid,
                         session: Session,
                         tactic_priority: int = None,
                         start_date: datetime = None,
                         end_date: datetime = None):
        """
        Creates or updates a tactic in a campaign
        If a case is marked deleted, it cannot be updated and a CampaignException is thrown
        :raises CampaignException:
        :param campaign_uuid:
        :param case_uuid:
        :param name:
        :param moderator_uuid:
        :param session:
        :param tactic_priority:
        :param start_date:
        :param end_date:
        :return:
        """

        cc = session.query(CampaignCase) \
            .filter(CampaignCase.case_uuid == case_uuid) \
            .one_or_none()
        if cc:
            if cc.deleted_at:
                raise TacticDeleted(msg='Tactic has been marked deleted - cannot update',
                                    return_code=410,
                                    case_uuid=case_uuid,
                                    campaign_uuid=campaign_uuid)
        else:
            cc = CampaignCase()
            cc.campaign_uuid = campaign_uuid
            cc.case_uuid = case_uuid
        cc.moderator_uuid = moderator_uuid
        if name:
            cc.name = name
        if tactic_priority is not None:
            cc.tactic_priority = tactic_priority
        else:
            if cc.tactic_priority is None:
                cc.tactic_priority = 0
        session.add(cc)
        CampaignCase.set_active_range(session=session,
                                      case_uuid=case_uuid,
                                      start_date=start_date,
                                      end_date=end_date)

        return cc

    @staticmethod
    def _get_tactic(case_uuid, session: Session) -> 'CampaignCase':
        """
        Get the tactic from the campaign case table

        :raises TacticNotFound(404), TacticDeleted(410):
        :param case_uuid:
        :param session:
        :return: CampaignCase or None
        """

        campaign_case = session.query(CampaignCase).get(case_uuid)
        if not campaign_case:
            raise TacticNotFound(msg=f'Tactic not found', case_uuid=case_uuid, return_code=404)
        if campaign_case.deleted_at:
            raise TacticDeleted(msg='Tactic has been marked deleted - cannot update',
                                return_code=410,
                                case_uuid=case_uuid)

        return campaign_case

    @staticmethod
    def _get_tactic_from_case(case_uuid, session: Session) -> Case:
        """
        This is the same as _get_tactic, except it gets the case from the Case table
        :raises TacticNotFound(404):
        :param case_uuid: str
        :param session: Session
        :return: Case or None
        """
        case = session.query(Case).get(case_uuid)
        if not case:
            raise TacticNotFound(msg=f'Tactic not found in Case table', case_uuid=case_uuid, return_code=404)
        return case

    @staticmethod
    def _get_tactic_campaign(case_uuid, session: Session) -> Campaign:
        """
        Gets the campaign details for a case_uuid

        :raises CampaignException(500):
        :param case_uuid: str
        :param session: Session
        :return: Campaign
        """

        campaign_case = CampaignCase._get_tactic(case_uuid=case_uuid, session=session)
        campaign = session.query(Campaign).get(campaign_case.campaign_uuid)
        if not campaign:
            raise CampaignException(msg=f'No campaign associated with tactic {case_uuid}', return_code=500)
        return campaign

    @staticmethod
    def attributed_authors(session: Session, case_uuid) -> Iterable[Optional[str]]:
        """
        Returns an iterable of attributed authors by uuid

        :param session: Session
        :param case_uuid: str
        :return: Iterable[str]
        """
        for aa in session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case_uuid).all():
            yield str(aa.author_uuid)

    @staticmethod
    def get_tactics_by_state(campaign_uuid, state, session):
        for case_state in session.query(CampaignCase, Case) \
                .filter(CampaignCase.campaign_uuid == campaign_uuid, CampaignCase.deleted_at.is_(None)) \
                .join(Case, CampaignCase.case_uuid == Case.case_uuid) \
                .all():
            if case_state[1].state == state:
                yield case_state[1]

    @staticmethod
    def review(session: Session, case_uuid, user_uuid: UUID_Type):
        """
        States are SC_DRAFT -> SC_REVIEW -> SC_APPROVED
        The pre-state for this transition is SC_DRAFT
        :param session:
        :param case_uuid:
        :param user_uuid:
        :return: None
        """

        case = CampaignCase._get_tactic_from_case(case_uuid=case_uuid, session=session)

        if case.state is not CaseState.SC_DRAFT:
            raise TacticUpdateError(msg=f'Case must be in Draft state to be reviewed - state is {case.state}',
                                    return_code=500)
        case.state = CaseState.SC_REVIEW
        session.add(case)
        campaign_case = CampaignCase._get_tactic(case_uuid=case_uuid, session=session)
        return str(campaign_case.campaign_uuid)

    @staticmethod
    def publish(session: Session, case_uuid, user_uuid: UUID_Type):
        """
        Publish the tactic, this involves:
        - set the case state to SC_APPROVED
        - set the start_date to now if it is not set
        - set the campaign to active if it is not active.
        :raises TacticUpdateError(500):
        :param session:
        :param case_uuid:
        :param user_uuid:
        :return: None
        """

        campaign_case = CampaignCase._get_tactic(case_uuid=case_uuid, session=session)
        campaign = CampaignCase._get_tactic_campaign(case_uuid=case_uuid, session=session)
        CampaignCase.set_active_range(session=session,
                                      case_uuid=case_uuid,
                                      start_date=campaign_case.start_date,
                                      end_date=campaign_case.end_date)

        case = CampaignCase._get_tactic_from_case(case_uuid=case_uuid, session=session)
        if case.state is not CaseState.SC_REVIEW:
            raise TacticUpdateError(msg=f'Case must be in Review state to be published - state is {case.state}',
                                    return_code=500)
        case.state = CaseState.SC_APPROVED
        case.published_at = campaign_case.start_date
        session.add(case)
        if campaign.state is not CampaignState.ACTIVE:
            Campaign.activate_campaign(campaign_uuid=campaign.campaign_uuid, user_uuid=user_uuid, session=session)
        return str(campaign_case.campaign_uuid)

    @staticmethod
    def set_active_range(session: Session,
                         case_uuid,
                         start_date: Optional[datetime],
                         end_date: Optional[datetime]):
        """
        Sets the time frame for a tactic to be active in.
        If start_date is not set, the current date is assumed
        If end_date is not set, end_date is set to Null

        Raises TacticInvalidDates if the end_date is before the start_date
        :raises  TacticInvalidDates(500):
        :param session:
        :param case_uuid:
        :param start_date:
        :param end_date:
        :return: None
        """
        if start_date and end_date:
            if end_date < start_date:
                raise TacticInvalidDates(msg='Start date cannot be later than end date',
                                         return_code=500,
                                         case_uuid=case_uuid)

        campaign_case = CampaignCase._get_tactic(case_uuid=case_uuid, session=session)
        if start_date:
            campaign_case.start_date = start_date
        elif not start_date and not campaign_case.start_date:
            campaign_case.start_date = datetime.now(tz=timezone.utc)

        if end_date:
            campaign_case.end_date = end_date
        session.add(campaign_case)
        return str(campaign_case.campaign_uuid)

    @staticmethod
    def archive(case_uuid, session: Session):
        """
        Archive a given tactic, this can be done regardless of the state of the campaign.
        :param case_uuid:
        :param session:
        :return:
        """
        campaign_case = CampaignCase._get_tactic(case_uuid=case_uuid, session=session)
        if not campaign_case.end_date or campaign_case.end_date > datetime.now(tz=timezone.utc):
            campaign_case.end_date = datetime.now(tz=timezone.utc)

        session.add(campaign_case)
        case = CampaignCase._get_tactic_from_case(case_uuid=case_uuid, session=session)
        case.state = CaseState.SC_ARCHIVED
        session.add(case)
        return str(campaign_case.campaign_uuid)

    @staticmethod
    def unarchive(case_uuid, session: Session):
        """
        Sets an archived tactic back to draft state.
        :param case_uuid:
        :param session:
        :return:
        """
        case = CampaignCase._get_tactic_from_case(case_uuid=case_uuid, session=session)
        case.state = CaseState.SC_DRAFT
        session.add(case)
        campaign_case = CampaignCase._get_tactic(case_uuid=case_uuid, session=session)
        return str(campaign_case.campaign_uuid)

    @staticmethod
    def archive_campaign_cases(campaign_uuid, session: Session):
        """
        Given a campaign_uuid, this sets the state of all cases in the campaign to archived.
        :param campaign_uuid:
        :param session:
        :return:
        """

        for s in session.query(CampaignCase).filter(CampaignCase.campaign_uuid == campaign_uuid,
                                                    CampaignCase.deleted_at.is_(None)).all():
            CampaignCase.archive(case_uuid=s.case_uuid, session=session)
            session.flush()
            yield str(s.case_uuid)

    @staticmethod
    def unarchive_campaign_cases(campaign_uuid, session: Session):
        """
        Given a campaign_uuid, all cases associated to this campaign are set to DRAFT
        :param campaign_uuid:
        :param session:
        :return:
        """
        for s in session.query(CampaignCase).filter(CampaignCase.campaign_uuid == campaign_uuid,
                                                    CampaignCase.deleted_at.is_(None)).all():
            CampaignCase.unarchive(case_uuid=s.case_uuid, session=session)

    def as_dict(self) -> CampaignCaseDict:
        return {
            'campaignUuid': str(self.campaign_uuid),
            'caseUuid': str(self.case_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'startDate': str(self.start_date),
            'endDate': str(self.end_date),
            'name': self.name,
            'tacticPriority': self.tactic_priority
        }


class CampaignPreviewUser(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_campaign_preview_user"
    campaign_uuid = Column(UUID(as_uuid=True), ForeignKey(Campaign.campaign_uuid), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    topic_uuid = Column(UUID(as_uuid=True))

    @staticmethod
    def create(campaign_uuid,
               user_uuid,
               topic_uuid,
               session):
        pu = session.query(CampaignPreviewUser) \
            .filter(CampaignPreviewUser.campaign_uuid == campaign_uuid,
                    CampaignPreviewUser.user_uuid == user_uuid) \
            .one_or_none()
        if pu:
            pu.deleted_at = None
        else:
            pu = CampaignPreviewUser()
            pu.campaign_uuid = campaign_uuid
            pu.user_uuid = user_uuid

        if topic_uuid:
            pu.topic_uuid = topic_uuid

        session.add(pu)
        return pu

    @staticmethod
    def delete(campaign_uuid,
               user_uuid,
               session,
               skip_commit=False):
        pu = session.query(CampaignPreviewUser) \
            .filter(CampaignPreviewUser.campaign_uuid == campaign_uuid,
                    CampaignPreviewUser.user_uuid == user_uuid) \
            .one_or_none()
        if not pu:
            return

        pu.mark_deleted()
        session.add(pu)
        return pu

    @staticmethod
    def get(campaign_uuid, session):
        """
        Get all user objects that are able to preview a campaign.
        :raises UserNotFound: If there is no user record found for this user.
        :param campaign_uuid:
        :param session:
        :return: Iterable[(CampaignPreviewUser, User)]
        """
        for u in session.query(CampaignPreviewUser) \
                .filter(CampaignPreviewUser.campaign_uuid == campaign_uuid,
                        CampaignPreviewUser.deleted_at.is_(None)) \
                .all():
            user = User.get_user_by_uuid(user_uuid=u.user_uuid, session=session)
            if user:
                yield u, user
