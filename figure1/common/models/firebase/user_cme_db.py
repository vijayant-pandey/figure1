import logging
from itertools import chain

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from figure1.common.types import CMETypes
from figure1.common.types import CmeCertificateStatus
from figure1.common.utils import check_s3_file_exists
from figure1.configuration import app_settings

from figure1.common.models.db import Case
from figure1.common.models.db import User
from figure1.common.models.db import CaseProgress
from figure1.common.models.db import CampaignPreviewUser
from figure1.common.models.db import CampaignCase
from figure1.common.models.db import CmeCertificateTemplate
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.models.db import UserSpecialtyTreeV2
from figure1.common.models.db import Media

from figure1.common.types import FirebaseAction
from figure1.common.types import CaseType
from figure1.common.types import CaseState
from figure1.common.types import CmeHubCardModel
from figure1.common.types import ContentType
from figure1.feeds import SponsoredContent

from figure1.common.utils import cme_certificate_path
from figure1.common.utils import generate_presigned_s3_get_object_url

from figure1.exceptions import S3Error

logger = logging.getLogger(__name__)


def _get_approved_cme_cases(case_uuid, user_uuid, progress_filter, session: Session):
    return session.query(Case) \
        .join(CaseProgress,
              and_(CaseProgress.case_uuid == case_uuid,
                   CaseProgress.user_uuid == user_uuid),
              full=True) \
        .filter(Case.deleted_at.is_(None),
                progress_filter,
                or_(Case.state == CaseState.APPROVED,
                    Case.state == CaseState.SC_APPROVED)) \
        .all()


def _get_preview_cme_cases(case_uuid, user_uuid, progress_filter, session: Session):
    return session.query(Case) \
        .join(CaseProgress,
              and_(CaseProgress.case_uuid == case_uuid,
                   CaseProgress.user_uuid == user_uuid),
              full=True) \
        .join(CampaignCase, CampaignCase.case_uuid == case_uuid) \
        .join(CampaignPreviewUser, and_(CampaignPreviewUser.user_uuid == user_uuid,
                                        CampaignPreviewUser.campaign_uuid == CampaignCase.campaign_uuid)) \
        .filter(Case.case_type == CaseType.CME,
                Case.deleted_at.is_(None),
                progress_filter,
                Case.state == CaseState.SC_REVIEW) \
        .all()


def _eligible_for_cert(case: Case, user: User, session: Session):
    template = session.query(CmeCertificateTemplate) \
        .join(SpecialtyTreeV2, SpecialtyTreeV2.profession_uuid == CmeCertificateTemplate.profession_uuid) \
        .join(UserSpecialtyTreeV2, UserSpecialtyTreeV2.tree_uuid == SpecialtyTreeV2.specialty_uuid) \
        .filter(UserSpecialtyTreeV2.user_uuid == user.user_uuid,
                UserSpecialtyTreeV2.is_primary.is_(True),
                CmeCertificateTemplate.case_uuid == case.case_uuid) \
        .one_or_none()

    return template is not None


def _get_certificate_download_url(case: Case, user: User):
    try:
        path = cme_certificate_path(case_uuid=case.case_uuid, user_uid=user.user_uid)
        if not check_s3_file_exists(path=path):
            return None
        return generate_presigned_s3_get_object_url(path=path)
    except S3Error as s3err:
        logger.exception("Caught error attempting to get certificate url")
        return None


class FirebaseUserCmeDB:
    root_collection = 'userCmeDB'

    @staticmethod
    def sync(firebase_db, uuid, action, session=None, columns=None):
        user = User.get_user_by_uuid(user_uuid=uuid, session=session, raise_exception=True)

        if action == FirebaseAction.DELETE:
            logging.error(f"Unsupported action for row={str(uuid)}, action={action}")
            return StopIteration

        available = FirebaseUserCmeCasesDB(completed_state=False, collection_name='available')
        for a in available.sync(firebase_db=firebase_db,
                                uuid=uuid,
                                action=action,
                                session=session):
            yield a

        completed = FirebaseUserCmeCasesDB(completed_state=True, collection_name='completed')
        for c in completed.sync(firebase_db=firebase_db,
                                uuid=uuid,
                                action=action,
                                session=session):
            yield c

        cme1_credits = session.query(func.sum(Case.cme1_credits)) \
            .join(CaseProgress, Case.case_uuid == CaseProgress.case_uuid) \
            .filter(CaseProgress.user_uuid == user.user_uuid, CaseProgress.completed_at.isnot(None)) \
            .scalar()
        if cme1_credits is None:
            cme1_credits = 0
        case_cme1_credits = session.query(func.sum(0.25)).select_from(Case) \
            .join(CaseProgress, Case.case_uuid == CaseProgress.case_uuid) \
            .filter(CaseProgress.user_uuid == user.user_uuid,
                    CaseProgress.completed_at.isnot(None),
                    Case.state == CaseState.APPROVED) \
            .scalar()
        cme1_credits += case_cme1_credits if case_cme1_credits else 0

        yield {
            "path": firebase_db.collection(FirebaseUserCmeDB.root_collection).document(user.user_uid).path,
            "action": FirebaseAction.SET,
            "data": {
                'cme1Credits': cme1_credits,
                'cme2Credits': 0,
                'userUuid': str(user.user_uuid),
                'userUid': user.user_uid
            }
        }


class FirebaseUserCmeCasesDB:
    collection_name: str
    completed_state: bool

    def __init__(self, collection_name, completed_state):
        self.collection_name = collection_name
        self.completed_state = completed_state

    def sync(self, firebase_db, uuid, action, session=None, columns=None):
        user = User.get_user_by_uuid(user_uuid=uuid, session=session, raise_exception=True)

        if action == FirebaseAction.DELETE:
            logging.error(f"Unsupported action for row={uuid}, action={action}")
            return StopIteration

        collection = firebase_db.collection(FirebaseUserCmeDB.root_collection) \
            .document(user.user_uid) \
            .collection(self.collection_name)

        if self.completed_state is False:
            yield {
                "path": collection,
                "action": FirebaseAction.DELETE_COLLECTION
            }

        if self.completed_state:
            progress_filter = CaseProgress.completed_at.isnot(None)
        else:
            progress_filter = and_(CaseProgress.completed_at.is_(None), Case.case_type == CaseType.CME)

        sp = SponsoredContent(user_uuid=str(user.user_uuid))
        targeted_cases = list(sp.get_cme_ids())

        approved_cases = _get_approved_cme_cases(case_uuid=Case.case_uuid,
                                                 user_uuid=user.user_uuid,
                                                 progress_filter=progress_filter,
                                                 session=session)
        preview_cases = _get_preview_cme_cases(case_uuid=Case.case_uuid,
                                               user_uuid=user.user_uuid,
                                               progress_filter=progress_filter,
                                               session=session)

        for c in chain(approved_cases, preview_cases):
            case_uuid = str(c.case_uuid)
            cme_model = CmeHubCardModel(caseUuid=case_uuid)
            case_progress = session.query(CaseProgress) \
                .filter(CaseProgress.case_uuid == case_uuid,
                        CaseProgress.user_uuid == user.user_uuid).one_or_none()
            if c.state is not CaseState.APPROVED:
                campaign_case = session.query(CampaignCase).get(case_uuid)
                targeted = str(case_uuid) in targeted_cases
                if campaign_case:
                    cme_model.startAt = str(campaign_case.start_date) if campaign_case.start_date else None
                    cme_model.endAt = str(campaign_case.end_date) if campaign_case.end_date else None
                    cme_model.totalSlides = sum(1 for case in c.content if case.content_type != ContentType.FEED_CARD)
                if case_progress:
                    cme_model.currentSlide = case_progress.content_position
                    cme_model.completedAt = str(case_progress.completed_at) if case_progress.completed_at else None
                cme_model.credits = c.cme1_credits
                cme_model.isEligible = targeted and _eligible_for_cert(case=c, user=user, session=session)
                cme_model.shareLink = f"{app_settings.app_url}/cme/{case_uuid}"
                cme_model.cmeType = CMETypes.ACTIVITY
                if cme_model.isEligible and cme_model.completedAt is not None:
                    cme_model.certificateDownloadUrl = _get_certificate_download_url(case=c, user=user)
                for content_item in c.content:
                    if content_item.content_type == ContentType.CME_HUB_CARD:
                        cme_model.media = Media.get_thumbnail_media(content_uuid=content_item.content_uuid,
                                                                    session=session)
                        cme_model.title = content_item.title
                        cme_model.heading = content_item.extension.heading

            elif case_progress is not None:
                cme_model.startAt = None
                cme_model.endAt = None
                cme_model.credits = 0.25
                cme_model.totalSlides = 0
                cme_model.currentSlide = 0
                cme_model.isEligible = True
                cme_model.title = c.content[0].title if c.content[0].title else c.content[0].caption
                cme_model.certificateDownloadUrl = _get_certificate_download_url(case=c, user=user)
                cme_model.shareLink = f"{app_settings.app_url}/case/{case_uuid}"
                cme_model.completedAt = str(case_progress.completed_at)
                cme_model.cmeType = CMETypes.CASE
                if c.feed_card:
                    cme_model.media = Media.get_thumbnail_media(content_uuid=c.feed_card.content_uuid,
                                                                session=session)

            else:
                logger.error("Case progress is none is case state is %s, case_type is %s", c.state, c.case_type)
                continue

            if not cme_model.isEligible:
                cme_model.certificateStatus = CmeCertificateStatus.INELIGIBLE
            elif not cme_model.certificateDownloadUrl:
                cme_model.certificateStatus = CmeCertificateStatus.GENERATING
            else:
                cme_model.certificateStatus = CmeCertificateStatus.COMPLETED

            logger.info("Syncing cme case uuid %s to firestore cme db for user %s", case_uuid, user.user_uid)
            yield {
                "path": collection.document(str(c.case_uuid)).path,
                "action": FirebaseAction.SET,
                "data": cme_model.dict()
            }
