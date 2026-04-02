import logging
from pydantic.types import UUID as UUID_Type
from sqlalchemy.orm import Session
from figure1.common.elasticsearch import add_or_update_campaign
from figure1.core import managed_session
from figure1.common.firebase import do_firebase_sync
from figure1.common.models.db import User, Campaign, CampaignPreviewUser, CampaignCase, Case
from figure1.common.types import CaseState
from figure1.exceptions import TopicFeedNotFound, UserNotFound
from figure1.pro.topics.domain import create_topic, update_topic, unfollow_campaign_preview, follow_topic


def _validate(moderator_uid, session: Session) -> UUID_Type:
    return User.get_user_uuid_by_uid(user_uid=moderator_uid, session=session, raise_exception=True)


@managed_session
def update_campaign(moderator_uid, data, session: Session, campaign_uuid=None):
    """
    Returns a dictionary on success, or raises an exception
    :raises CampaignException
    :param moderator_uid:
    :param data:
    :param session:
    :param campaign_uuid:
    :return: {}
    """
    moderator_uuid = _validate(moderator_uid=moderator_uid, session=session)

    name = data.get('name')
    client_name = data.get('client_name')
    campaign_priority = data.get('campaign_priority')
    target_country_uuids = data.get('target_country_uuids')
    target_specialty_uuids = data.get('target_specialty_uuids')
    target_languages = data.get('target_languages')
    preview_user_uids = data.get('preview_user_uids')
    is_sponsored = data.get('is_sponsored')

    c = Campaign.create_or_update(campaign_uuid=campaign_uuid,
                                  name=name,
                                  client_name=client_name,
                                  campaign_priority=campaign_priority,
                                  author_uuid=moderator_uuid,
                                  is_sponsored=is_sponsored,
                                  session=session)
    if target_country_uuids:
        Campaign.update_target_countries(campaign_uuid=c.campaign_uuid,
                                         country_uuids=target_country_uuids,
                                         session=session)
    if target_specialty_uuids:
        Campaign.update_target_specialties(campaign_uuid=c.campaign_uuid,
                                           tree_uuids=target_specialty_uuids,
                                           session=session)
    if target_languages:
        Campaign.update_target_languages(campaign_uuid=c.campaign_uuid,
                                         languages=target_languages,
                                         session=session)
    if 'target_verification' in data:
        Campaign.update_target_verification(campaign_uuid=c.campaign_uuid,
                                            verification=data.get('target_verification'),
                                            session=session)
    if preview_user_uids:
        # If a campaign uuid is passed, we know that the campaign exists, but if no preview user ids were passed
        # previously, a topic may not exist. So we try to update, but catch and create a topic if one doesn't exist
        # IF a duplicate campaign name is passed in here the database transaction will raise here since topic name/kind
        # cannot be duplicated.

        t = {'feedTypeUuid': None}
        if campaign_uuid:
            try:
                t = update_topic(label=str(c.campaign_uuid),
                                 name=name,
                                 hidden=True,
                                 display_order=1000,
                                 sort_fields=[],
                                 expire_query={},
                                 specialtyUuids=[],
                                 state_filter='SC_REVIEW',
                                 session=session,
                                 filter_query={
                                     "nested": {
                                         "path": "campaignSettings",
                                         "query": {
                                             "term": {
                                                 "campaignSettings.campaignUuid": str(c.campaign_uuid)
                                             }
                                         }
                                     }
                                 })
            except TopicFeedNotFound:
                t = create_topic(label=str(c.campaign_uuid),
                                 name=name,
                                 sort_fields=[],
                                 expire_query={},
                                 specialtyUuids=[],
                                 state_filter='SC_REVIEW',
                                 session=session,
                                 filter_query={
                                     "nested": {
                                         "path": "campaignSettings",
                                         "query": {
                                             "term": {
                                                 "campaignSettings.campaignUuid": str(c.campaign_uuid)
                                             }
                                         }
                                     }
                                 })
        else:
            t = create_topic(label=str(c.campaign_uuid),
                             name=name,
                             sort_fields=[],
                             expire_query={},
                             specialtyUuids=[],
                             state_filter='SC_REVIEW',
                             session=session,
                             filter_query={
                                 "nested": {
                                     "path": "campaignSettings",
                                     "query": {
                                         "term": {
                                             "campaignSettings.campaignUuid": str(c.campaign_uuid)
                                         }
                                     }
                                 }
                             })

        # If anyone is set as a preview user is not included in the preview user list, delete and remove the feed
        # from firestore for their user.
        session.flush()
        for pu, u in CampaignPreviewUser.get(campaign_uuid=c.campaign_uuid, session=session):
            if u.user_uid not in preview_user_uids:
                CampaignPreviewUser.delete(campaign_uuid=c.campaign_uuid, user_uuid=u.user_uuid, session=session)
                unfollow_campaign_preview(user_uid=u.user_uid, feed_type_uuid=pu.topic_uuid, session=session)

        review_tactics = list(CampaignCase.get_tactics_by_state(campaign_uuid=campaign_uuid,
                                                                state=CaseState.SC_REVIEW,
                                                                session=session))
        for preview_user in preview_user_uids:
            try:
                preview_user_object = User.get_user_by_uid(user_uid=preview_user, session=session, raise_exception=True)
            except UserNotFound:
                logging.error("User not found")
            else:
                CampaignPreviewUser.create(campaign_uuid=campaign_uuid,
                                           user_uuid=preview_user_object.user_uuid,
                                           topic_uuid=t.get('feedTypeUuid'),
                                           session=session)
                if review_tactics:
                    follow_topic(user_uid=preview_user,
                                 feed_type_uuid=str(t.get('feedTypeUuid')),
                                 session=session)
        session.flush()

    add_or_update_campaign(campaign_uuid=str(c.campaign_uuid), session=session)

    return {
        'success': 'Campaign updated' if campaign_uuid else 'Campaign created',
        'campaign_uuid': str(c.campaign_uuid)
    }


@managed_session
def activate_campaign(moderator_uid, campaign_uuid, session: Session):
    """
    Returns a dictionary on success, or raises an exception
    :raises CampaignException
    :param moderator_uid:
    :param campaign_uuid:
    :param session:
    :return: {}
    """
    moderator_uuid = _validate(moderator_uid=moderator_uid, session=session)
    Campaign.activate_campaign(campaign_uuid=campaign_uuid, user_uuid=moderator_uuid, session=session)
    add_or_update_campaign(campaign_uuid=campaign_uuid, session=session)
    return {"success": f"Campaign {campaign_uuid} activated"}


@managed_session
def archive_campaign(moderator_uid, campaign_uuid, session: Session):
    """
    Returns a dictionary on success or raises an exception

    When archiving a campaign, all tactics are set to archived and the preview users have the feed for this campaign
    removed.
    :raises CampaignException:
    :param moderator_uid:
    :param campaign_uuid:
    :param session:
    :return: {}
    """
    moderator_uuid = _validate(moderator_uid=moderator_uid, session=session)
    Campaign.archive_campaign(campaign_uuid=campaign_uuid, user_uuid=moderator_uuid, session=session)
    for pu, u in CampaignPreviewUser.get(campaign_uuid=campaign_uuid, session=session):
        unfollow_campaign_preview(user_uid=u.user_uid, feed_type_uuid=pu.topic_uuid, session=session)

    for case_uuid in CampaignCase.archive_campaign_cases(campaign_uuid=campaign_uuid, session=session):
        for aa in CampaignCase.attributed_authors(session=session, case_uuid=case_uuid):
            do_firebase_sync.delay(firebasemodel='FirebaseUsersProfileDB', uuid=str(aa))
    add_or_update_campaign(campaign_uuid=campaign_uuid, session=session)
    return {"success": f"Campaign {campaign_uuid} archived"}


@managed_session
def unarchive_campaign(moderator_uid, campaign_uuid, session: Session):
    moderator_uuid = _validate(moderator_uid=moderator_uid, session=session)
    Campaign.unarchive_campaign(campaign_uuid=campaign_uuid, user_uuid=moderator_uuid, session=session)
    add_or_update_campaign(campaign_uuid=campaign_uuid, session=session)
    return {"success": f"Campaign {campaign_uuid} unarchived"}
