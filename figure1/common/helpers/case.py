import logging

from pydantic import ValidationError
from sqlalchemy import func

from figure1.common.models.db.c_campaign_model import CampaignCase
from figure1.common.models.db.c_case_model import Case
from figure1.common.models.db.c_case_model import Content
from figure1.common.models.db.c_case_reaction_model import CaseReaction
from figure1.common.models.db.c_legacy_case_model import LegacyCase
from figure1.common.models.db.c_media_model import Media
from figure1.common.models.db.c_mention_model import Mention
from figure1.common.models.db.c_question_model import QuestionOption
from figure1.common.models.db.c_question_model import QuestionVote
from figure1.common.models.db.e_promotion_model import Promotion
from figure1.common.models.db.e_promotion_model import PromotionCases
from figure1.common.models.db.m_case_edit import CaseEdit
from figure1.common.models.db.m_case_edit import CaseMediaEdit
from figure1.common.models.db.m_case_note import CaseNote
from figure1.common.models.db.user_models import UserSavedCase
from figure1.common.models.db.reference_data_models.r_specialty_model import SpecialtyV2
from figure1.common.models.db.c_case_specialty_model import CaseSpecialtyV2
from figure1.common.types import CaseClassification
from figure1.common.types import CaseType
from figure1.common.types import CommentState
from figure1.common.types import ContentExtensionModel
from figure1.common.types import ContentModel
from figure1.common.types import ContentType
from figure1.common.types import ContentUpdatesModel
from figure1.configuration import app_settings
from figure1.exceptions import CaseNotFound
from .comment import CommentSync
from .user import UserDocument

logger = logging.getLogger(__name__)


class CaseDetail:
    @staticmethod
    def _case(case_uuid, session=None) -> Case:
        case = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
        if not case:
            raise CaseNotFound(case_uuid=case_uuid, msg="Failed to find case")
        return case

    @staticmethod
    def _case_reactions(case_uuid, session):
        return CaseReaction.get_case_reactions(case_uuid=case_uuid, session=session)

    @staticmethod
    def _count_case_reactions(case_uuid, session):
        return CaseReaction.get_reaction_counts(case_uuid=case_uuid, session=session)

    @staticmethod
    def _case_saved(case_uuid, session):
        return session.query(UserSavedCase) \
            .filter(UserSavedCase.case_uuid == case_uuid, UserSavedCase.deleted_at.is_(None)) \
            .all()

    @staticmethod
    def _legacy_case(case_uuid, session):
        return session.query(LegacyCase).get(case_uuid)

    @staticmethod
    def case_actions(case_uuid, session):
        """
        Should return a dict keyed by user_uuid, with the optional keys of saved: True and reactions with an array of
        reactions on this case. The reactions array will only ever have one element since you can only have one
        reaaction per case.

        :param case_uuid:
        :param session:
        :return:
        """
        user_data = {}
        reactions = CaseDetail._case_reactions(case_uuid=case_uuid, session=session)
        for k in reactions:
            for user_reaction in reactions[k]:
                user_data.update({user_reaction: {'reactions': [k]}})
        for case in CaseDetail._case_saved(case_uuid=case_uuid, session=session):
            user_uuid = str(case.user_uuid)
            if user_uuid in user_data:
                user_data[user_uuid].update({'saved': True})
            else:
                user_data.update({user_uuid: {'saved': True}})
        return user_data

    @staticmethod
    def firestore_case_detail(case_uuid, session):
        case_data, case = CaseDetail._case_detail(case_uuid=case_uuid, session=session)
        case_data.update({'allReactions': CaseDetail._count_case_reactions(case_uuid=case_uuid, session=session)})
        total_comment_count = 0
        content_items = []
        has_feed_card = any([c.is_feed_card for c in case.content])

        for i, content in enumerate(case.content):
            try:
                content_data = CaseDetail._content_detail(content_item=content, session=session)
            except ValidationError:
                logger.exception("Content item %s failed to validate", content.content_uuid)
                continue

            content_translation_map = {content_translation['language']: content_translation
                                       for content_translation
                                       in content_data.get("translations")}

            for content_update in content_data.get("updates"):
                content_update['translations'] = {content_update_translation['language']: content_update_translation
                                                  for content_update_translation
                                                  in content_update['translations']}

            content_data.update({
                'caseType': case_data.get('caseType'),
                'campaignUuid': case_data.get('campaignUuid'),
                'isSponsored': case_data.get('isSponsored'),
                'translations': content_translation_map
            })
            content_items.append(content_data)
            if content.is_feed_card or (has_feed_card is False and i == 0):
                case_data.update({'feedCardType': content_data.get('feedCardType'),
                                  'feedCardMedia': content_data.get('feedCardMedia')},
                                 **content_data)
                del case_data['displayOrder']
                del case_data['contentUuid']
                del case_data['updates']
                del case_data['isFeedCard']
            total_comment_count += content_data['commentCount']

        case_data['commentCount'] = total_comment_count
        case_data['contentItems'] = [*content_items]
        return case_data

    @staticmethod
    def elasticsearch_case_detail(case_uuid, session):
        case_data, case = CaseDetail._case_detail(case_uuid=case_uuid, session=session, is_anonymous=False)
        total_comment_count = 0
        content_items = []
        all_comments = []
        legacy_case = CaseDetail._legacy_case(case_uuid=case_uuid, session=session)
        has_feed_card = any([c.is_feed_card for c in case.content])
        case_data['hasAcceptedAnswer'] = False

        for i, content in enumerate(case.content):
            try:
                content_data = CaseDetail._content_detail(content, session=session)
            except ValidationError as ve:
                logger.exception("Content item %s failed to validate", content.content_uuid)
                continue
            content_items.append(content_data)
            if content.is_feed_card or (has_feed_card is False and i == 0):
                case_data.update({
                    'caption': content_data.get('caption'),
                    'title': content_data.get('title'),
                    'media': content_data.get('media'),
                    'commentCount': content_data.get('commentCount', 0),
                    'feedCardType': content_data.get('feedCardType'),
                    'feedCardMedia': content_data.get('feedCardMedia')
                })
            if content.accepted_answer is not None and content.accepted_answer.state is CommentState.APPROVED:
                case_data['hasAcceptedAnswer'] = True
            comments = [x for x in content.comments if x.state == 'APPROVED']
            all_comments.extend(comments)
            comment_count = content_data.get("commentCount", 0)
            total_comment_count += comment_count

        case_data['commentCount'] = total_comment_count
        case_data['comments'] = [x.as_dict() for x in all_comments]
        case_data['contentItems'] = [*content_items]
        case_data['legacyCaseId'] = legacy_case.legacy_id if legacy_case else None

        return case_data

    @staticmethod
    def elasticsearch_moderation_case_detail(session, case_uuid=None):
        es_update = {}
        case_note_filters = []
        case_edit_filters = [CaseEdit.deleted_at.is_(None), CaseEdit.edit_applied.is_(False)]
        case_media_edit_filters = [CaseMediaEdit.deleted_at.is_(None), CaseMediaEdit.edit_applied.is_(False)]
        promotion_filters = []
        campaign_case_filters = []
        if case_uuid:
            for content_id in session.query(Content).filter(Content.case_uuid == case_uuid).all():
                content_id: Content
                case_edit_filters.append(CaseEdit.content_uuid == content_id.content_uuid)
                if content_id.media:
                    for media_id in content_id.media:
                        case_media_edit_filters.append(CaseMediaEdit.media_uuid == media_id.media_uuid)

            case_note_filters.append(CaseNote.case_uuid == case_uuid)
            promotion_filters.append(PromotionCases.case_id == case_uuid)
            campaign_case_filters.append(CampaignCase.case_uuid == case_uuid)
        for note in session.query(CaseNote).filter(*case_note_filters).all():
            n = note.as_firestore_dict(session=session)
            note_case_uuid = n['caseUuid']
            if not es_update.get(note_case_uuid, {}):
                es_update.update({note_case_uuid: {}})
            if not es_update.get(note_case_uuid, {}).get('moderationNotes'):
                es_update.update({note_case_uuid: {'moderationNotes': []}})
            es_update[note_case_uuid]['moderationNotes'].append({
                **n,
            })
        for ce in session.query(CaseEdit, Content) \
                .join(Content, CaseEdit.content_uuid == Content.content_uuid) \
                .filter(*case_edit_filters) \
                .all():
            case_edit = ce[0].as_firestore_dict(session=session)
            content_edit_case_uuid = str(ce[1].case_uuid)
            if not es_update.get(content_edit_case_uuid, {}):
                es_update.update({content_edit_case_uuid: {}})
            if not es_update.get(content_edit_case_uuid, {}).get('moderationEdit'):
                es_update[content_edit_case_uuid].update({'moderationEdit': []})
            es_update[content_edit_case_uuid]['moderationEdit'].append({
                **case_edit,
                'editType': 'content',
            })
        for me in session.query(CaseMediaEdit, Media) \
                .join(Media, Media.media_uuid == CaseMediaEdit.media_uuid) \
                .filter(*case_media_edit_filters) \
                .all():
            me_dict = me[0].as_firestore_dict(session=session)
            if not case_uuid:
                case_uuid_result = session.query(Content.case_uuid) \
                    .filter(Content.content_uuid == me[1].content_uuid).one()
                if case_uuid_result:
                    media_edit_case_uuid = str(case_uuid_result.case_uuid)
            else:
                media_edit_case_uuid = case_uuid
            if not es_update.get(media_edit_case_uuid, {}):
                es_update.update({media_edit_case_uuid: {}})
            if not es_update.get(media_edit_case_uuid, {}).get('moderationEdit'):
                es_update[media_edit_case_uuid].update({'moderationEdit': []})
            es_update[media_edit_case_uuid]['moderationEdit'].append({
                **me_dict,
                'editType': 'media',
            })
        for p in session.query(PromotionCases, Promotion) \
                .join(Promotion, Promotion.promotion_uuid == PromotionCases.promotion_uuid) \
                .filter(*promotion_filters) \
                .all():
            case_uuid = str(p[0].case_id)
            if not es_update.get(case_uuid, {}):
                es_update.update({case_uuid: {}})
            if not es_update.get(case_uuid, {}).get('promotions'):
                es_update[case_uuid].update({'promotions': []})
            es_update[case_uuid]['promotions'].append({
                **p[0].as_dict(),
                **p[1].as_dict()
            })

        return es_update

    @staticmethod
    def _case_detail(case_uuid, session, is_anonymous=True):
        case = CaseDetail._case(case_uuid=case_uuid, session=session)
        case_specialties = [x.as_object() for x in case.specialties]
        case_data = dict(createdAt=str(case.created_at),
                         updatedAt=str(case.updated_at),
                         caseState=case.state.name,
                         caseType=case.case_type.name.lower(),
                         specialtyUuids=[x.specialtyUuid for x in case_specialties],
                         specialtyNames=[x.specialtyName for x in case_specialties],
                         caseUuid=str(case_uuid),
                         labels=[x.as_dict()['kind'] for x in case.labels],
                         userSaved=[x.as_dict()['userUuid'] for x in case.user_saved_case],
                         isPagingCase=case.is_paging_case,
                         unverifiedViewCount=0,
                         cme1Credits=case.cme1_credits,
                         passingScore=case.passing_score,
                         groupUuid=str(case.group_uuid) if case.group_uuid else None,
                         certificates=[x.as_dict() for x in case.cme_certificates],
                         language=case.language,
                         requestHelp=case.request_help,
                         hasDiagnosis=case.has_diagnosis,
                         diagnoses=[ContentUpdatesModel.from_orm(each).dict() for each in case.diagnoses],
                         isCaseCme=case.is_case_cme,
                         isAnonymous=case.is_anonymous,
                         caseClassification=case.case_classification.value if case.case_classification
                         else CaseClassification.MEDICAL.value)

        if case.campaign:
            case_data.update({'isSponsored': case.campaign.is_sponsored,
                              'campaignUuid': str(case.campaign.campaign_uuid)})

        if case.mesh_terms:
            case_data.update({'meshTerms': case.mesh_terms.approved_terms})
        # For backwards compatibility
        authors = []
        for ca in case.authors:
            if is_anonymous is False:
                author_data = UserDocument.get_compact_user_data(session=session,
                                                                 is_anonymous=is_anonymous,
                                                                 user_uuid=str(ca.user_uuid))
            else:
                author_data = UserDocument.get_compact_user_data(session=session,
                                                                 is_anonymous=case.is_anonymous,
                                                                 user_uuid=str(ca.user_uuid))
            authors.append(author_data)
            case_data.update({'author_profession_label': author_data.get('name', 'Not Available')})
            case_data.update({'author_username': author_data.get('username')})
            case_data.update({'author_uid': author_data.get('userUid')})
            case_data.update({'authorUid': author_data.get('userUid')})

        case_data.update({'authors': authors})
        if case.published_at:
            case_data.update({'publishedAt': str(case.published_at)})
        else:
            case_data.update({'publishedAt': str(case.created_at)})

        if case.case_type == CaseType.CME:
            case_data['shareLink'] = f"{app_settings.app_url}/cme/{case_uuid}"
        elif case.case_type == CaseType.CLINICAL_MOMENTS:
            case_data['shareLink'] = f"{app_settings.app_url}/clinical-moments/{case_uuid}"
        else:
            case_data['shareLink'] = f"{app_settings.app_url}/cases/{case_uuid}"
        return case_data, case

    @staticmethod
    def _content_detail(content_item, session):
        try:
            content_model = ContentModel.from_orm(content_item)
            if not content_model.commentCount:
                content_model.commentCount = 0
        except ValidationError as ve:
            logger.critical("Failed to parse content uuid - raised error %s", ve.json())
            raise
        content_data = content_model.dict()
        if content_item.extension:
            extension = ContentExtensionModel.from_orm(content_item.extension)
            content_data.update(extension.dict())
        if content_item.content_type == ContentType.QUIZ or content_item.content_type == ContentType.QUIZ_SERIES:
            question_options = session.query(QuestionOption) \
                .filter(QuestionOption.content_uuid == content_model.contentUuid, QuestionOption.deleted_at.is_(None)) \
                .all()
        else:
            question_options = []

        if content_item.is_feed_card:
            feed_card_media = Media.get_feed_card_media(content_uuid=content_model.contentUuid, session=session)
            if feed_card_media:
                fcm = feed_card_media.as_object().dict()
                content_data.update({'feedCardMedia': fcm})

        option_data = []
        for qo in question_options:
            qo_dict = qo.as_dict()
            del qo_dict['contentUuid']
            votes = session.query(func.count(QuestionVote.user_uuid)) \
                .filter(QuestionVote.question_option_uuid == qo.question_option_uuid,
                        QuestionVote.deleted_at.is_(None)) \
                .scalar()
            qo_dict['votes'] = votes
            option_data.append(qo_dict)
        content_data.update({
            'questionOptions': option_data
        })

        if content_item.accepted_answer:
            answer = content_item.accepted_answer.as_object()
            content_data.update({
                'acceptedAnswer': CommentSync.get_comment_dict_from_object(comment_object=answer, session=session)
            })

        # Fetch and add mentions for this content's caption/description
        try:
            from uuid import UUID

            content_uuid = content_model.contentUuid
            if isinstance(content_uuid, str):
                content_uuid = UUID(content_uuid)

            logger.debug(f"Querying mentions for content {content_uuid}")
            mentions = session.query(Mention).filter(
                Mention.content_uuid == content_uuid,
                Mention.comment_uuid.is_(None)  # Only get mentions for case description, not comments
            ).all()

            logger.info(f"Found {len(mentions)} mentions for content {content_uuid}")

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

                content_data['mentions'] = mentions_list
                logger.info(f"Added {len(mentions_list)} mentions to content {content_uuid}")
            else:
                logger.debug(f"No mentions found for content {content_uuid}")
        except Exception as e:
            logger.exception(f"Error fetching mentions for content {content_model.contentUuid}: {e}")
            # Don't fail sync if mentions fetch fails
            pass

        return content_data

    @staticmethod
    def get_case_specialty_names(case_uuid, session=None):
        """
        It returns a List of specialty names given case_uuid
        :param case_uuid:
        :param session:
        :return:
        """
        result = []

        for s in session.query(SpecialtyV2)\
                .join(CaseSpecialtyV2, CaseSpecialtyV2.specialty_uuid == SpecialtyV2.specialty_uuid)\
                .filter(CaseSpecialtyV2.case_uuid == case_uuid).all():
            result.append(s.name)

        return result
