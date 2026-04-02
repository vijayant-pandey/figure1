import logging
from sqlalchemy import func, distinct
from figure1.common.models.db.a_analytics_model import CaseAnalytics
from figure1.common.models.db.c_case_model import Content
from figure1.common.models.db.c_case_model import Case
from figure1.common.models.db.c_case_model import CaseAuthor
from figure1.common.models.db.m_comment_flag import CommentFlag
from figure1.common.models.db.c_comment_model import Comment
from figure1.common.models.db.c_comment_model import CommentReport
from figure1.common.models.db.c_mention_model import Mention
from figure1.common.models.db.user_models import UserSpecialtyTreeV2
from figure1.common.models.db.user_models import User
from figure1.common.models.db.user_models import UserProfile
from figure1.common.types import CommentModel
from figure1.common.types import CommentState
from figure1.common.types import PublicCommentStates
from .user import UserDocument
from ..types.comment import CommentModeratorReviewStatus

logger = logging.getLogger(__name__)


class CommentAnalytics:
    def __init__(self):
        self.approved_comment_count = 0
        self.approved_comment_count_by_content_uuid = {}

    def _write_analytics(self, session, case_uuid):
        ca = session.query(CaseAnalytics).get(case_uuid)
        if not ca:
            ca = CaseAnalytics()
            ca.case_uuid = case_uuid
            ca.total_comments = self.approved_comment_count
        else:
            ca.total_comments = self.approved_comment_count
        session.add(ca)

    def get_case_from_content(self, session, content_uuid):
        c = session.query(Content).filter(Content.content_uuid == content_uuid).first()
        return str(c.case_uuid)

    def _get_case_content_uuids(self, session, case_uuid):
        for content in session.query(Content).filter(Content.case_uuid == case_uuid).all():
            yield str(content.content_uuid)

    def get_comment_count_by_case(self, session, case_uuid):
        for content in self._get_case_content_uuids(session=session, case_uuid=case_uuid):
            count = self.count_by_content_uuid(session=session, content_uuid=content)
            self.approved_comment_count += count
            self.approved_comment_count_by_content_uuid[content] = count
        self._write_analytics(session=session, case_uuid=case_uuid)

    def count_by_content_uuid(self, session, content_uuid):
        return session.query(func.count(Comment.comment_uuid)) \
            .filter(Comment.content_uuid == content_uuid,
                    Comment.replyable.is_(True),
                    Comment.deleted_at.is_(None)).scalar()


class CommentSync:
    """
    Class for generating comment shapes for firestore
    """

    @staticmethod
    def get_comments_by_content_uuid(content_uuid, session):
        logger.info("Starting comment sync by content uuid %s", content_uuid)
        for top_level in session.query(Comment) \
                .filter(Comment.content_uuid == content_uuid, func.nlevel(Comment.path) == 1).all():
            yield CommentSync.generate_tree_branch(top_level.comment_uuid, session)
        logger.info("Completed comment sync for content uuid %s", content_uuid)

    @staticmethod
    def generate_tree_branch(comment_uuid, session):
        logger.debug("START TREE GENERATION %s", comment_uuid)
        tree = {}

        def descend_to_children(comment_object, depth, is_parent_anonymous=False):
            if depth >= 100:
                raise Exception("Max recursion depth reached")

            if not comment_object.children:
                logger.debug("No children found")
                return {}

            if not comment_object.author:
                comment_object.author = UserDocument.get_compact_user_data(user_uuid=comment_object.authorUuid,
                                                                           session=session,
                                                                           is_anonymous=comment_object.isAnonymous)
            for c in comment_object.children:
                logger.debug("Comment object state is %s", comment_object.commentState)
                if c.commentState not in [x.lower() for x in PublicCommentStates.__members__]:
                    continue
                if comment_object.commentState == CommentState.APPROVED.value \
                        and not comment_object.isDeleted \
                        and not comment_object.author.get("isDeleted"):
                    if not is_parent_anonymous:
                        c.text = f"@{comment_object.author.get('username')} {c.text}"
                    if c.translations:
                        for t in c.translations:
                            if not is_parent_anonymous:
                                t.text = f"@{comment_object.author.get('username')} {t.text}"
                else:
                    logger.debug("Comment state %s does not match %s",
                                 comment_object.commentState,
                                 CommentState.APPROVED.value)
                if c.children:
                    descend_to_children(comment_object=c, depth=depth + 1, is_parent_anonymous=c.isAnonymous)

                logger.debug("Adding child comment %s", c.commentUuid)
                children.update({c.commentUuid: CommentSync.get_comment_dict_from_object(comment_object=c.copy(),
                                                                                         session=session)})

        logger.debug("Getting comment")
        comment = CommentSync.get_comment(comment_uuid=comment_uuid, session=session)
        logger.debug("Checking comment state")
        if comment.state not in [x.value for x in PublicCommentStates]:
            logger.debug("Non-public comment state, ending tree generation")
            return tree
        logger.debug("Convert comment to object")
        comment_to_object = comment.as_object()
        if comment_to_object.parentUuid == comment_to_object.commentUuid:
            logger.debug("Comment is parent")
            full_tree_object = comment.as_tree_object()
        else:
            logger.debug("Comment %s is not parent, get parent comment %s", comment_to_object.commentUuid,
                         comment_to_object.parentUuid)
            parent_object = CommentSync.get_comment(comment_uuid=comment_to_object.parentUuid, session=session)
            logger.debug("Get parent comment object")
            full_tree_object = parent_object.as_tree_object()

        logger.debug("Get parent comment dict")
        copy_full_tree_object = full_tree_object.copy()

        parent = CommentSync.get_comment_dict_from_object(comment_object=copy_full_tree_object, session=session)
        children = {}
        logger.debug("Getting all children")
        descend_to_children(comment_object=full_tree_object, depth=1, is_parent_anonymous=parent.get('isAnonymous'))
        logger.debug("Adding children to parent")
        parent.update({'children': {**children}})
        logger.debug("Updating tree with parent comment uuid")
        tree.update({parent.get('commentUuid'): {**parent}})
        logger.debug("END TREE GENERATION %s", comment_uuid)
        return tree

    @staticmethod
    def get_comment(comment_uuid, session=None):
        return session.query(Comment).get(comment_uuid)

    @staticmethod
    def get_comment_dict_from_object(comment_object: CommentModel, session):
        if comment_object.authorUuid:
            comment_author_detail = UserDocument.get_compact_user_data(user_uuid=comment_object.authorUuid,
                                                                       session=session,
                                                                       is_anonymous=comment_object.isAnonymous)
            comment_object.author = comment_author_detail
            comment_object.add_deprecated_fields(user_detail_dict=comment_author_detail)
            comment_object.isPhysician = comment_author_detail.get('professionName')

            # Fetch and add mentions for this comment
            try:
                from uuid import UUID

                # Convert string UUID to UUID object for query
                comment_uuid = comment_object.commentUuid
                if isinstance(comment_uuid, str):
                    comment_uuid = UUID(comment_uuid)

                logger.debug(f"Querying mentions for comment {comment_uuid}")
                mentions = session.query(Mention).filter(
                    Mention.comment_uuid == comment_uuid
                ).all()

                logger.info(f"Found {len(mentions)} mentions for comment {comment_uuid}")

                if mentions:
                    mentions_list = []
                    for mention in mentions:
                        mention_dict = {
                            'mentionUuid': str(mention.mention_uuid),
                            'mentionedUserUuid': str(mention.mentioned_user_uuid),
                            'mentioningUserUuid': str(mention.mentioning_user_uuid),
                            'position': mention.position,
                            'isRead': mention.is_read,
                            'createdAt': mention.created_at.isoformat() if mention.created_at else None
                        }

                        # Include mentioned user's basic info if available
                        if mention.mentioned_user:
                            # Build display name from first_name and last_name
                            display_name = None
                            if mention.mentioned_user.first_name or mention.mentioned_user.last_name:
                                parts = []
                                if mention.mentioned_user.first_name:
                                    parts.append(mention.mentioned_user.first_name)
                                if mention.mentioned_user.last_name:
                                    parts.append(mention.mentioned_user.last_name)
                                display_name = ' '.join(parts)

                            mention_dict['mentionedUser'] = {
                                'username': mention.mentioned_user.username,
                                'displayName': display_name,
                                'userUuid': str(mention.mentioned_user.user_uuid)
                            }

                        mentions_list.append(mention_dict)

                    comment_object.mentions = mentions_list
                    logger.info(f"Added {len(mentions_list)} mentions to comment {comment_object.commentUuid}")
                else:
                    logger.debug(f"No mentions found for comment {comment_uuid}")
            except Exception as e:
                logger.exception(f"Error fetching mentions for comment {comment_object.commentUuid}: {e}")
                # Don't fail sync if mentions fetch fails
                pass

            return comment_object.dict(exclude={'children'})
        else:
            return {}


class CommentDetail:
    """
    get_ functions are used for bulk loading, others are used for individual comments. They are functionally
    identical, but the bulk functions work on the entire dataset and so don't take comment uuids.
    """

    @staticmethod
    def _comment_case_dict(content_uuid, session):
        """
        Pass in a comment ORM instance and get the case sub-section populated. If the content is deleted, an extra query
        is required to go and fetch the Case to determine if it is in a group.
        """
        content = session.query(Content).filter(Content.content_uuid == content_uuid).one()
        case = {
            'caption': content.caption,
            'title': content.title,
            'caseUuid': str(content.case_uuid),
            'caseAuthors': [],
            'isCaseAnonymous': None,
        }
        if content.case is not None:
            case_authors = CommentDetail._case_authors_for_comment(case_uuid=content.case_uuid, session=session)
            if content.case.group_uuid:
                case.update({'groupUuid': str(content.case.group_uuid)})
            case.update({'isCaseAnonymous': content.case.is_anonymous})
            case.update({'caseAuthors': case_authors})

        if content.deleted_at:
            case.update({'deletedAt': str(content.deleted_at)})

        if len(content.media) >= 1:
            case.update({'mediaThumbnailUrl': content.media[0].url})

        return case

    @staticmethod
    def get_comment_authors(session):
        total_author_count = 0
        total_comment_count = 0
        comment_authors = session.query(
            distinct(Comment.author_uuid).label('author_uuid')
        ).subquery()
        for author in session.query(User) \
                .join(comment_authors, comment_authors.c.author_uuid == User.user_uuid) \
                .yield_per(1000) \
                .all():
            profile = author.user_profile
            author_specialty = session.query(UserSpecialtyTreeV2) \
                .filter(UserSpecialtyTreeV2.user_uuid == author.user_uuid).first()
            total_author_count += 1
            for comment in session.query(Comment) \
                    .filter(Comment.author_uuid == author.user_uuid) \
                    .yield_per(1000) \
                    .all():
                total_comment_count += 1
                yield {
                    'commentUuid': str(comment.comment_uuid),
                    'authorUuid': str(author.user_uuid),
                    'authorUsername': author.username,
                    'authorProfessionName': author_specialty.tree.case_comment_display_label
                    if author_specialty else None,
                    'authorAvatar': profile.avatar if profile else None,
                }

            if not total_author_count % 10000:
                logging.info(f"Updated {total_author_count} authors of {total_comment_count} comments")

    @staticmethod
    def get_comment_content(session):
        total_comments = 0
        total_content_items = 0
        for content in session.query(Content).all():
            count = 0
            total_content_items += 1
            case_dict = CommentDetail._comment_case_dict(content_uuid=content.content_uuid, session=session)
            case_authors = case_dict.pop('caseAuthors')
            is_case_anonymous = case_dict.pop('isCaseAnonymous')
            for comment in session.query(Comment).filter(Comment.content_uuid == content.content_uuid).all():
                if comment:
                    count += 1
                    try:
                        yield {
                            'commentUuid': str(comment.comment_uuid),
                            'isCaseAnonymous': is_case_anonymous,
                            'isCaseAuthor': True if str(comment.author_uuid) in case_authors else False,
                            'case': case_dict
                        }
                    except AttributeError:
                        logger.exception("Error in getting data for comment_uuid %s", comment.comment_uuid)
            total_comments += count
            if not total_content_items % 10000:
                logging.info(f"Total comments processed {total_comments} - Total content items {total_content_items}")

    @staticmethod
    def get_comment_flags(session):
        for distinct_comment in session.query(CommentFlag.comment_uuid).distinct().all():
            flagged_comments = []
            for comment in session.query(CommentFlag, User) \
                    .filter(CommentFlag.comment_uuid == distinct_comment.comment_uuid,
                            CommentFlag.deleted_at.is_(None)) \
                    .join(User, User.user_uuid == CommentFlag.moderator_uuid) \
                    .all():
                flag = comment[0]
                moderator = comment[1]
                flagged_comments.append({
                    'moderatorUuid': str(moderator.user_uuid),
                    'moderatorUsername': moderator.username,
                    'moderatorName': moderator.first_name,
                    'flaggedAt': flag.created_at,
                })
            yield {'commentUuid': str(distinct_comment.comment_uuid),
                   "flags": flagged_comments}

    @staticmethod
    def get_comment_reports(session):
        for distinct_comment in session.query(CommentReport.comment_uuid).distinct().all():
            reported_comments = []
            for comment in session.query(CommentReport, User) \
                    .filter(CommentReport.comment_uuid == distinct_comment.comment_uuid,
                            CommentReport.deleted_at.is_(None)) \
                    .join(User, User.user_uuid == CommentReport.user_uuid) \
                    .all():
                report = comment[0]
                user = comment[1]
                reported_comments.append({
                    'reporterUuid': str(user.user_uuid),
                    'reporterUsername': user.username,
                    'reportedAt': report.created_at,
                    'text': report.text,
                    'reportReason': report.report_reason.name.lower()
                })
            yield {'commentUuid': str(distinct_comment.comment_uuid),
                   "reports": reported_comments}

    @staticmethod
    def _author_for_comment(comment_uuid, session):
        author = session.query(User, UserProfile) \
            .filter(Comment.comment_uuid == comment_uuid) \
            .join(Comment, Comment.author_uuid == User.user_uuid) \
            .join(UserProfile, UserProfile.user_uuid == User.user_uuid, full=True) \
            .one_or_none()
        author_specialty = UserSpecialtyTreeV2.get_primary(user_uuid=author[0].user_uuid, session=session)

        return {
            'authorUuid': str(author[0].user_uuid),
            'authorUsername': author[0].username,
            'authorProfessionName': author_specialty.caseCommentDisplayName
            if author_specialty else None,
            'authorAvatar': author[1].avatar if author[1] else None,
        }

    @staticmethod
    def _case_authors_for_comment(case_uuid, session):
        return [str(each.author_uuid) for each in
                session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case_uuid).all()]

    @staticmethod
    def _moderation_flagged_info(comment_uuid, session):
        res = session.query(CommentFlag, User) \
            .filter(CommentFlag.comment_uuid == comment_uuid,
                    CommentFlag.deleted_at.is_(None)) \
            .join(User, User.user_uuid == CommentFlag.moderator_uuid) \
            .all()
        if not res:
            return {}

        data = []
        for r in res:
            flag = r[0]
            moderator = r[1]
            data.append({
                'moderatorUuid': str(moderator.user_uuid),
                'moderatorUsername': moderator.username,
                'moderatorName': moderator.first_name,
                'flaggedAt': flag.created_at,
            })
        return {"flags": data}

    @staticmethod
    def _moderation_reported_info(comment_uuid, session):
        res = session.query(CommentReport, User) \
            .filter(CommentReport.comment_uuid == comment_uuid,
                    CommentReport.deleted_at.is_(None)) \
            .join(User, User.user_uuid == CommentReport.user_uuid) \
            .all()
        if not res:
            return {}

        data = []
        for r in res:
            report = r[0]
            user = r[1]
            data.append({
                'reporterUuid': str(user.user_uuid),
                'reporterUsername': user.username,
                'reportedAt': report.created_at,
                'text': report.text,
                'reportReason': report.report_reason.name.lower()
            })
        return {"reports": data}

    @staticmethod
    def elasticsearch_comment(comment_uuid, session):
        comment_data = CommentDetail._comment_detail(comment_uuid=comment_uuid, session=session)
        if not comment_data:
            return None

        comment_data.update(CommentDetail._moderation_flagged_info(comment_uuid=comment_uuid, session=session))
        comment_data.update(CommentDetail._moderation_reported_info(comment_uuid=comment_uuid, session=session))
        return comment_data

    @staticmethod
    def _comment_detail(comment_uuid, session):
        comment: Comment = CommentSync.get_comment(comment_uuid=comment_uuid, session=session)
        case_dict = CommentDetail._comment_case_dict(content_uuid=comment.content.content_uuid, session=session)
        case_authors = case_dict.pop('caseAuthors')
        is_case_anonymous = case_dict.pop('isCaseAnonymous')
        is_reviewed = comment.moderator_reviewed

        author = CommentDetail._author_for_comment(comment_uuid=comment_uuid, session=session)
        comment_data = comment.as_dict()

        comment_data.update({'isCaseAnonymous': is_case_anonymous,
                             'isCaseAuthor': True if str(comment.author_uuid) in case_authors else False,
                             'case': case_dict,
                             'moderatorReviewStatus': CommentModeratorReviewStatus.REVIEWED.value if is_reviewed
                             else CommentModeratorReviewStatus.PENDING_REVIEW.value})

        if author:
            comment_data.update({
                **author
            })
        return comment_data
