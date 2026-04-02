import logging
from datetime import timezone, datetime
from typing import Dict, Any, Optional
from celery import group
from celery.canvas import Signature

from sqlalchemy.orm import Session

from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers import CaseManagement
from figure1.common.models.db import User, Content, CampaignCase, Campaign, Case, CampaignPreviewUser
from figure1.common.types import CaseState, \
    Locale, \
    ContentType, \
    FeedCardType, \
    CaseType, \
    ContentSection, \
    FirebaseAction
from figure1.common.utils import cme_certificate_templates_path
from figure1.common.utils.s3_utils import move_s3_file
from figure1.core import managed_session
from figure1.exceptions import CampaignNotFound, \
    InvalidCampaignDates, \
    InvalidFeedCardType, \
    InvalidContentType, \
    TacticUpdateError
from figure1.exceptions.campaign import InvalidSection, InvalidPostTest, InvalidPassingScore
from figure1.pro.topics.domain import follow_topic, unfollow_campaign_preview
from .tasks import sync_promo_card_task, sync_campaign_cases_task


def _parse_date(date):
    if not date:
        return None
    try:
        return datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError as e:
        logging.error(f"Failed to parse date {date}: {e}")
        raise InvalidCampaignDates(msg=f"Failed to parse date {date}")


def _parse_int(value, field_name):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise TacticUpdateError(msg=f"Invalid {field_name}: {value}")


def _parse_float(value, field_name):
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        raise TacticUpdateError(msg=f"Invalid {field_name}: {value}")


def _parse_feed_card_type(feed_card_type):
    if not feed_card_type or feed_card_type.upper() not in [f.name for f in FeedCardType]:
        raise InvalidFeedCardType(msg=f'Invalid feed_card_type: {feed_card_type}', return_code=422)
    return FeedCardType[feed_card_type.upper()]


def _parse_content_type(content_type):
    if not content_type or content_type.upper() not in [t.name for t in ContentType]:
        raise InvalidContentType(msg=f'Invalid content_type: {content_type}', return_code=422)
    return ContentType[content_type.upper()]


def _parse_content_section(section):
    if not section:
        return None
    elif section.upper() not in [s.name for s in ContentSection]:
        raise InvalidSection(msg=f'Invalid section: {section}', return_code=422)
    return ContentSection[section.upper()]


def _get_default_tactic_features(is_sponsored: bool):
    return [
        ("comment_tabs_enabled", False),
        ("report_enabled", False),
        ("show_labels", False),
        ("show_views", not is_sponsored),
        ("similar_cases_enabled", False),
    ]


def _validate_passing_score(passing_score, data):
    """
    Ensures the passing score is a valid value between 0 and the number of post test questions
    :raises InvalidPassingScore
    """
    slides = data.get('slides')
    question_count = sum(1 for s in slides if s.get('section', "").upper() == ContentSection.POST_TEST.name)

    if passing_score < 0 or passing_score > question_count:
        raise InvalidPassingScore(
            msg=f'Invalid passing score: {passing_score}, must be between 0 and the number of post test questions',
            return_code=422)


def _validate_post_test_question(content_data):
    """
    Ensures each post test question has questions options and an answer
    :raises InvalidPostTest
    """
    if 'question_options' not in content_data:
        raise InvalidPostTest(msg=f'Invalid post test question: missing options', return_code=422)

    for qo in content_data['question_options']:
        if qo.get('is_answer'):
            return

    raise InvalidPostTest(msg=f'Invalid post test question:  an option must be marked as the answer', return_code=422)


def _upsert_case_from_data(moderator_uid, data, case_uuid, session: Session, case_type: CaseType) -> Case:
    moderator_uuid = User.get_user_uuid_by_uid(user_uid=moderator_uid, session=session, raise_exception=True)
    author_uuid = User.get_user_uuid_by_uid(user_uid=data.get('author_uid'), session=session, raise_exception=True)

    campaign_uuid = data.get('campaign_uuid')
    if not campaign_uuid or not session.query(Campaign).get(campaign_uuid):
        raise CampaignNotFound(campaign_uuid=data.get('campaign_uuid'))

    case_args = {
        "state": CaseState.SC_DRAFT,
        "author_uuid": author_uuid,
        "language": Locale.EN_US.code,
        "is_paging_case": False,
        "case_type": case_type,
        "cme1_credits": _parse_float(value=data.get('cme1_credits'), field_name="cme1_credits"),
        "passing_score": _parse_int(value=data.get('passing_score'), field_name="passing_score"),
    }

    if case_args.get("passing_score"):
        _validate_passing_score(passing_score=case_args['passing_score'], data=data)

    if not case_uuid:
        case = CaseManagement.create_case(session=session, **case_args)

    else:
        case = CaseManagement.update_case(case_uuid=case_uuid,
                                          session=session,
                                          **case_args)
        if author_uuid:
            CaseManagement.replace_case_author(case_uuid=case_uuid, author_uuid=author_uuid, session=session)

    CampaignCase.create_or_update(campaign_uuid=campaign_uuid,
                                  case_uuid=case.case_uuid,
                                  name=data.get('settings', {}).get('name'),
                                  moderator_uuid=moderator_uuid,
                                  tactic_priority=data.get('settings', {}).get('tactic_priority'),
                                  start_date=data.get('settings', {}).get('start_date'),
                                  end_date=data.get('settings', {}).get('end_date'),
                                  session=session)

    # Move certificate into path which includes case_uuid
    for c in data.get('certificates', []):
        if not c.get('filename'):
            continue
        old_path = c.get('path')
        new_path = '/'.join([cme_certificate_templates_path, str(case.case_uuid), c.get('filename')])
        if old_path != new_path:
            cert_moved = move_s3_file(old_path=old_path, new_path=new_path)
            if cert_moved:
                c['path'] = new_path

    CaseManagement.update_cme_certificates(case_uuid=case.case_uuid,
                                           certificates=data.get('certificates', []),
                                           session=session)
    return case


def _upsert_content(content_uuid, case_uuid, data: dict, content_args: dict, session: Session) -> Content:
    sponsored_data = data.get('sponsored_content', {})
    is_sponsored = True if (sponsored_data.get('disclosure_text') or
                            sponsored_data.get('sponsored_text')) else False

    for feature, value in _get_default_tactic_features(is_sponsored):
        if feature not in content_args:
            content_args.update({feature: value})

    if not content_uuid:
        content = CaseManagement.create_content(case_uuid=case_uuid,
                                                session=session,
                                                **content_args)

    else:
        content = CaseManagement.update_content(content_uuid=content_uuid,
                                                session=session,
                                                **content_args)

    return content


def _delete_unused_content(case_uuid, new_content_count: int, session: Session):
    q = session.query(Content) \
        .filter(Content.case_uuid == case_uuid, Content.deleted_at.is_(None)) \
        .order_by(Content.display_order)
    for i, c in enumerate(q.all()):
        if i >= new_content_count:
            CaseManagement.delete_content(content=c,
                                          session=session,
                                          destructive=False)


@managed_session
def review_campaign_tactic(case_uuid: str, user_uid: str, session: Session) -> Signature:
    """
    Updates case and tactic model to set state to SC_REVIEW
    :param case_uuid:
    :param user_uid:
    :param session:
    :return: None
    :raises CampaignException, TacticUpdateError
    """
    case = Case.get_case(case_uuid=case_uuid)

    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    campaign_uuid = CampaignCase.review(session=session, case_uuid=case_uuid, user_uuid=user_uuid)
    for pu, u in CampaignPreviewUser.get(campaign_uuid=campaign_uuid, session=session):
        follow_topic(user_uid=u.user_uid,
                     feed_type_uuid=str(pu.topic_uuid),
                     session=session)

    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=campaign_uuid)
    if case.case_type == CaseType.PROMO_CARD:
        task.link(sync_promo_card_task.si(case_uuid=case_uuid, preview_users=True))
    task.link(do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2", merge=False))
    return task


@managed_session
def publish_campaign_tactic(case_uuid: str, user_uid: str, session: Session) -> Signature:
    """
    Publish campaign tactic this sets the states required to immediately deploy the tactic.

    When there are no cases left in review, then remove the campaign preview feed.
    :param case_uuid:
    :param user_uid:
    :param session:
    :return:
    """
    case = Case.get_case(case_uuid=case_uuid)
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    campaign_uuid = CampaignCase.publish(session=session, case_uuid=case_uuid, user_uuid=user_uuid)
    if not len(list(CampaignCase.get_tactics_by_state(campaign_uuid=campaign_uuid,
                                                      state=CaseState.SC_REVIEW,
                                                      session=session))):
        for pu, u in CampaignPreviewUser.get(campaign_uuid=campaign_uuid, session=session):
            unfollow_campaign_preview(user_uid=u.user_uid,
                                      feed_type_uuid=str(pu.topic_uuid),
                                      session=session)
    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=campaign_uuid)
    if case.case_type == CaseType.PROMO_CARD:
        task.link(sync_promo_card_task.si(case_uuid=case_uuid, targeted_users=True))
    task.link(do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2", merge=False))
    return task


@managed_session
def archive_campaign_tactic(case_uuid: str, user_uid: str, session: Session) -> Signature:
    """
    Set a campaign tactic to archived state
    :param case_uuid:
    :param user_uid:
    :param session:
    :return:
    """
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    campaign_uuid = CampaignCase.archive(case_uuid=case_uuid, session=session)
    task_list = []
    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=campaign_uuid)
    task_list.append(task)
    for aa in CampaignCase.attributed_authors(session=session, case_uuid=case_uuid):
        task_list.append(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(aa)))
    return group(task_list)


@managed_session
def unarchive_campaign_tactic(case_uuid: str, user_uid: str, session: Session) -> Signature:
    """
    Set a campaign tactic to archived stated
    :param case_uuid:
    :param user_uid:
    :param session:
    :return:
    """
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    campaign_uuid = CampaignCase.unarchive(case_uuid=case_uuid, session=session)
    return sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=campaign_uuid)


@managed_session
def set_campaign_tactic_active_range(case_uuid: str,
                                     user_uid: str,
                                     start_date,
                                     end_date,
                                     session: Session) -> Signature:
    User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    campaign_uuid = CampaignCase.set_active_range(session=session,
                                                  case_uuid=case_uuid,
                                                  start_date=_parse_date(start_date),
                                                  end_date=_parse_date(end_date))
    return sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=campaign_uuid)


@managed_session
def delete_tactic(case_uuid: str, user_uid: str, session: Session) -> Signature:
    campaign_uuid = None
    User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    cc = session.query(CampaignCase).get(case_uuid)
    if cc:
        campaign_uuid = cc.campaign_uuid
        cc.mark_deleted()
        session.flush()

    CaseManagement.delete_case(case_uuid=case_uuid, session=session)
    session.commit()
    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=campaign_uuid, delete_case=True)
    task.link(do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2"))
    return task


@managed_session
def create_update_static_case(moderator_uid: str,
                              data: Dict[str, Any],
                              session: Session,
                              case_uuid: Optional[str]):
    """
    Creates or updates a static case and sets the state to DRAFT.

    If case_uuid is None, a new case is created.  Otherwise updates the given case_uuid.
    :param moderator_uid:
    :param data:
    :param session:
    :param case_uuid:
    :return:
    """
    new_case = case_uuid is None
    case = _upsert_case_from_data(moderator_uid=moderator_uid,
                                  data=data,
                                  session=session,
                                  case_uuid=case_uuid,
                                  case_type=CaseType.STATIC)
    case_uuid = case.case_uuid

    content_args = {
        "is_feed_card": True,
        "display_order": 0,
        "content_type": ContentType.CONTENT,
        **data.get('sponsored_content', {}),
        **data.get('external_link', {}),
        **data.get('features', {}),
        **data.get('feed_card', {}),
        **data.get('isi', {}),
        **data.get('settings', {})
    }
    for param in ['title', 'caption', 'media', 'references']:
        if param in data:
            content_args[param] = data[param]
    content_args['feed_card_type'] = _parse_feed_card_type(content_args.get('feed_card_type'))

    content = session.query(Content).filter(Content.case_uuid == case_uuid).one_or_none()
    content = _upsert_content(content_uuid=content.content_uuid if content else None,
                              data=data,
                              content_args=content_args,
                              case_uuid=case_uuid,
                              session=session)
    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=data.get('campaign_uuid'))

    return {
        'task': task,
        'success': 'Case created' if new_case else 'Case updated',
        'case_uuid': str(case_uuid),
        'content_uuid': str(content.content_uuid)
    }


@managed_session
def create_update_quiz(moderator_uid: str,
                       data: Dict[str, Any],
                       session: Session,
                       case_uuid: Optional[str]):
    """
    Creates or updates a quiz (or poll) and sets the state to DRAFT.

    If case_uuid is None, a new quiz is created.  Otherwise updates the given case_uuid.
    :param moderator_uid:
    :param data:
    :param session:
    :param case_uuid:
    :return:
    """
    new_case = case_uuid is None
    case = _upsert_case_from_data(moderator_uid=moderator_uid,
                                  data=data,
                                  session=session,
                                  case_uuid=case_uuid,
                                  case_type=CaseType.QUIZ)
    case_uuid = case.case_uuid

    content_args = {
        "is_feed_card": True,
        "display_order": 0,
        "content_type": ContentType.QUIZ,
        **data.get('sponsored_content', {}),
        **data.get('external_link', {}),
        **data.get('features', {}),
        **data.get('feed_card', {}),
        **data.get('isi', {}),
        **data.get('settings', {})
    }
    for param in ['title', 'caption', 'question_answer_details', 'question_options', 'media', 'references']:
        if param in data:
            content_args[param] = data[param]
    content_args['feed_card_type'] = _parse_feed_card_type(content_args.get('feed_card_type'))

    content = session.query(Content).filter(Content.case_uuid == case_uuid).one_or_none()
    content = _upsert_content(content_uuid=content.content_uuid if content else None,
                              data=data,
                              content_args=content_args,
                              case_uuid=case_uuid,
                              session=session)
    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=data.get('campaign_uuid'))
    return {
        'task': task,
        'success': 'Case created' if new_case else 'Case updated',
        'case_uuid': str(case_uuid),
        'content_uuid': str(content.content_uuid)
    }


@managed_session
def create_update_quiz_series(moderator_uid: str,
                              data: Dict[str, Any],
                              session: Session,
                              case_uuid: Optional[str]):
    """
    Creates or updates a quiz series (or poll series) and sets the state to DRAFT

    If case_uuid is None, a new quiz series is created.  Otherwise updates the given case_uuid.
    :param moderator_uid:
    :param data:
    :param session:
    :param case_uuid:
    :return:
    """
    new_case = case_uuid is None
    case = _upsert_case_from_data(moderator_uid=moderator_uid,
                                  data=data,
                                  session=session,
                                  case_uuid=case_uuid,
                                  case_type=CaseType.QUIZ_SERIES)
    case_uuid = case.case_uuid

    all_content = data.get('questions')
    all_content.append(data.get('conclusion'))

    content_uuids = []
    for i, content_data in enumerate(all_content):
        content_args = {
            "is_feed_card": i == 0,
            "display_order": i,
            "content_type": ContentType.QUIZ_SERIES if (i < len(all_content) - 1) else ContentType.QUIZ_SUMMARY,
            **content_data.get('external_link', {}),
            **content_data.get('isi', {}),
            **data.get('sponsored_content', {}),
            **data.get('features', {}),
            **data.get('settings', {})
        }
        for param in ['title', 'caption', 'question_answer_details', 'question_options', 'media', 'references']:
            if param in content_data:
                content_args[param] = content_data[param]
        if content_args['is_feed_card']:
            content_args.update(**data.get('feed_card', {}))
            content_args['feed_card_type'] = _parse_feed_card_type(content_args.get('feed_card_type'))
        if 'heading' in data:
            content_args['heading'] = data['heading']

        content = session.query(Content) \
            .filter(Content.case_uuid == case_uuid, Content.display_order == i) \
            .one_or_none()
        content = _upsert_content(content_uuid=content.content_uuid if content else None,
                                  data=data,
                                  content_args=content_args,
                                  case_uuid=case_uuid,
                                  session=session)

        content_uuids.append(str(content.content_uuid))
    _delete_unused_content(case_uuid=case_uuid, new_content_count=len(all_content), session=session)

    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=data.get('campaign_uuid'))
    return {
        'task': task,
        'success': 'Case created' if new_case else 'Case updated',
        'case_uuid': str(case_uuid),
        'content_uuids': content_uuids
    }


@managed_session
def create_update_clinical_moments(moderator_uid: str,
                                   data: Dict[str, Any],
                                   session: Session,
                                   case_uuid: Optional[str]):
    """
    Creates or updates a clinical moments and sets the state to DRAFT.

    If case_uuid is None, a new clinical moments is created.  Otherwise updates the given case_uuid.
    :param moderator_uid:
    :param data:
    :param session:
    :param case_uuid:
    :return:
    """
    new_case = case_uuid is None
    case = _upsert_case_from_data(moderator_uid=moderator_uid,
                                  data=data,
                                  session=session,
                                  case_uuid=case_uuid,
                                  case_type=CaseType.CLINICAL_MOMENTS)
    case_uuid = case.case_uuid

    slides = data.get('slides', [])

    is_first_slide = True
    content_uuids = []
    for i, content_data in enumerate(slides):
        content_type = _parse_content_type(content_data.get('content_type'))
        content_args = {
            "is_feed_card": content_type == ContentType.FEED_CARD,
            "display_order": i,
            "content_type": content_type,
            **content_data.get('external_link', {}),
            **content_data.get('isi', {}),
            **data.get('sponsored_content', {}),
            **data.get('features', {}),
            **data.get('settings', {})
        }
        for param in ['title', 'caption', 'question_answer_details', 'question_options', 'media', 'feed_card_label',
                      'feed_card_media', 'feed_card_title', 'colour', 'button_text', 'heading', 'feed_card_type',
                      'references']:
            if param in content_data:
                content_args[param] = content_data[param]
        if content_args['is_feed_card']:
            content_args['feed_card_type'] = FeedCardType.HIGHLIGHT
            content_args['title'] = content_args.get('feed_card_title')
        else:
            content_args['section'] = ContentSection.ACTIVITY

        # Disable comments for all content except first non-feed card content
        if not is_first_slide:
            content_args['comments_enabled'] = False
        if not content_args['is_feed_card'] and is_first_slide:
            is_first_slide = False

        content = session.query(Content) \
            .filter(Content.case_uuid == case_uuid, Content.display_order == i) \
            .one_or_none()
        content = _upsert_content(content_uuid=content.content_uuid if content else None,
                                  data=data,
                                  content_args=content_args,
                                  case_uuid=case_uuid,
                                  session=session)

        content_uuids.append(str(content.content_uuid))
    _delete_unused_content(case_uuid=case_uuid, new_content_count=len(slides), session=session)

    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=data.get('campaign_uuid'))
    return {
        'task': task,
        'success': 'Case created' if new_case else 'Case updated',
        'case_uuid': str(case_uuid),
        'content_uuids': content_uuids
    }


@managed_session
def create_update_cme(moderator_uid: str,
                      data: Dict[str, Any],
                      session: Session,
                      case_uuid: Optional[str]):
    """
    Creates or updates a CME case and sets the state to DRAFT.

    If case_uuid is None, a new CME is created.  Otherwise updates the given case_uuid.

    :param moderator_uid:
    :param data:
    :param session:
    :param case_uuid:
    :return:
    """
    new_case = case_uuid is None
    case = _upsert_case_from_data(moderator_uid=moderator_uid,
                                  data=data,
                                  session=session,
                                  case_uuid=case_uuid,
                                  case_type=CaseType.CME)
    case_uuid = case.case_uuid

    slides = data.get('slides', [])
    content_uuids = []
    for i, content_data in enumerate(slides):
        content_type = _parse_content_type(content_data.get('content_type'))
        section = _parse_content_section(content_data.get('section'))
        content_args = {
            "is_feed_card": content_type == ContentType.FEED_CARD,
            "display_order": i,
            "content_type": content_type,
            "section": section,
            **content_data.get('external_link', {}),
            **content_data.get('isi', {}),
            **data.get('sponsored_content', {}),
            **data.get('features', {}),
            **data.get('settings', {})
        }
        for param in ['title', 'caption', 'question_answer_details', 'question_options', 'media', 'feed_card_label',
                      'feed_card_media', 'feed_card_title', 'colour', 'button_text', 'heading', 'feed_card_type',
                      'references']:
            if param in content_data:
                content_args[param] = content_data[param]
        if content_args['is_feed_card']:
            content_args['feed_card_type'] = _parse_feed_card_type(content_args.get('feed_card_type'))

        if section == ContentSection.POST_TEST:
            _validate_post_test_question(content_data=content_data)

        content = session.query(Content) \
            .filter(Content.case_uuid == case_uuid, Content.display_order == i) \
            .one_or_none()
        content = _upsert_content(content_uuid=content.content_uuid if content else None,
                                  data=data,
                                  content_args=content_args,
                                  case_uuid=case_uuid,
                                  session=session)

        content_uuids.append(str(content.content_uuid))
    _delete_unused_content(case_uuid=case_uuid, new_content_count=len(slides), session=session)

    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=data.get('campaign_uuid'))
    return {
        'task': task,
        'success': 'Case created' if new_case else 'Case updated',
        'case_uuid': str(case_uuid),
        'content_uuids': content_uuids
    }


@managed_session
def create_promo_card(moderator_uid: str,
                      data: Dict[str, Any],
                      session: Session,
                      case_uuid: Optional[str]):
    """
    Creates or updates a promo card and sets the state to DRAFT.

    If case_uuid is None, a new promo card is created.  Otherwise updates the given case_uuid.
    :param moderator_uid:
    :param data:
    :param session:
    :param case_uuid:
    :return:
    """
    new_case = case_uuid is None
    if 'author_uid' not in data:
        data['author_uid'] = moderator_uid

    case = _upsert_case_from_data(moderator_uid=moderator_uid,
                                  data=data,
                                  session=session,
                                  case_uuid=case_uuid,
                                  case_type=CaseType.PROMO_CARD)
    case_uuid = case.case_uuid
    content_args = {
        "is_feed_card": False,
        "display_order": 0,
        "content_type": ContentType.PROMO_CARD,
        **data.get('features', {}),
        **data.get('settings', {}),
        **data
    }

    content = session.query(Content).filter(Content.case_uuid == case_uuid).one_or_none()
    content = _upsert_content(content_uuid=content.content_uuid if content else None,
                              data=data,
                              content_args=content_args,
                              case_uuid=case_uuid,
                              session=session)
    task = sync_campaign_cases_task.si(case_uuid=case_uuid, campaign_uuid=data.get('campaign_uuid'))
    task.link(do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2", action=FirebaseAction.DELETE))
    return {
        'task': task,
        'success': 'Promo card created' if new_case else 'Promo card updated',
        'case_uuid': str(case_uuid),
        'content_uuid': str(content.content_uuid)
    }
