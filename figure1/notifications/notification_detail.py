import logging
from typing import Union
from uuid import UUID

from google.cloud.firestore_v1.client import Client
from sqlalchemy.orm import Session

from figure1.common.helpers import CaseDetail
from figure1.common.helpers import FeedCard
from figure1.common.helpers import GroupManagement
from figure1.common.helpers import UserDocument
from figure1.common.models.db import Case
from figure1.common.models.db import Comment
from figure1.common.models.db import UserNotification
from figure1.common.models.firebase.user_drafts_db import FirebaseUserDraftsDB
from figure1.common.types import UserNotificationType
from figure1.exceptions import DraftNotFound
from figure1.exceptions import NotificationNotFound
from .activities.models import CaseDeletedNotificationModel
from .activities.models import CaseRejectedNotificationModel
from .activities.models import CommentDeletedNotificationModel
from .activities.models import NotificationCaseMediaModel
from .activities.models import NotificationModel
from .activities.models import NotificationModelBase

__all__ = ['NotificationDetail']


logger = logging.getLogger(__name__)


class NotificationDetail:

    @staticmethod
    def _populate_case_rejection(model: Union[CaseDeletedNotificationModel, CaseRejectedNotificationModel],
                                 case_uuid: str,
                                 firebase_db: Client,
                                 session: Session):
        c = Case.get_case(case_uuid=case_uuid, session=session, raise_exception=True)
        if c.rejection_reason:
            model.rejectionReason = c.rejection_reason.name
            model.rejectionReasonMessage = c.rejection_reason.message
            model.rejectionRevisionAllowed = c.rejection_reason.allow_revision
            model.caseClassification = c.case_classification
            if model.rejectionRevisionAllowed:
                user_uid = model.targetUser.get('userUid')
                try:
                    model.draftUid = FirebaseUserDraftsDB.get_draft_uid(fs_client=firebase_db,
                                                                        user_uid=user_uid,
                                                                        case_uuid=case_uuid)
                except DraftNotFound:
                    logger.warning("Could not find draft for case %s, user %s", case_uuid, user_uid)

    @staticmethod
    def _populate_case_media(model: NotificationModelBase):
        if model.case.get('media'):
            url = model.case.get('media')[0].get('url')
            model.caseMedia = NotificationCaseMediaModel(caseMediaUrl=url)
        else:
            model.caseMedia = NotificationCaseMediaModel()

    @staticmethod
    def _populate_comment_data(model: CommentDeletedNotificationModel, comment: Comment):
        model.comment = comment.as_object().dict(exclude_none=True)

    @staticmethod
    def _populate_comment_rejection(model: CommentDeletedNotificationModel, comment: Comment):
        if comment.rejection_reason:
            model.rejectionReason = comment.rejection_reason.name
            model.rejectionReasonMessage = comment.rejection_reason.message

    @staticmethod
    def get_notification_detail(notification_uuid: UUID,
                                firebase_db: Client,
                                session: Session):
        n = session.query(UserNotification).get(notification_uuid)
        if not n:
            raise NotificationNotFound(notification_uuid=notification_uuid)

        model = NotificationModel[n.notification_type.name].value.from_orm(n)

        if n.user_uuid:
            model.targetUser = UserDocument.get_compact_user_data(user_uuid=n.user_uuid, session=session)

        if n.source_uuid:
            model.sourceUser = UserDocument.get_compact_user_data(user_uuid=n.source_uuid, session=session)

        if n.case_uuid:
            case_detail = CaseDetail.elasticsearch_case_detail(case_uuid=n.case_uuid, session=session)
            model.case = FeedCard.feed_card(feed_item={'_source': case_detail})
            NotificationDetail._populate_case_media(model)
            if n.notification_type in [UserNotificationType.CASE_DELETE, UserNotificationType.REJECT]:
                NotificationDetail._populate_case_rejection(model=model,
                                                            case_uuid=n.case_uuid,
                                                            firebase_db=firebase_db,
                                                            session=session)
        if n.comment_uuid:
            comment = Comment.get_comment(comment_uuid=n.comment_uuid, session=session)
            NotificationDetail._populate_comment_data(model=model, comment=comment)
            if n.notification_type is UserNotificationType.COMMENT_DELETE:
                NotificationDetail._populate_comment_rejection(model=model, comment=comment)

        if n.group_uuid:
            model.sourceGroup = GroupManagement.get_group(group_uuid=n.group_uuid, session=session) \
                .dict(exclude={"groupMembers", "groupFilters"})
        model.populate_template()

        # Deprecated properties
        model.type = model.notificationType
        model.activityType = model.notificationType

        return model.dict(exclude_none=True)
