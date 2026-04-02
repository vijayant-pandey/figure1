import copy
import logging

from jinja2 import Environment

from figure1.common.elasticsearch import add_or_update_campaign, \
    add_or_update_case, \
    delete_case as delete_case_from_es
from figure1.common.helpers import UserDocument
from figure1.common.types import MobileAppRoutes, WebAppRoutes
from figure1.common.helpers.promo_card import PromoCardDetail
from figure1.common.models.db import CampaignPreviewUser, CampaignCase, User
from figure1.core import FirebaseTaskBase, celery_app
from figure1.feeds import SponsoredContent, SponsoredContentTargets

env = Environment()
logger = logging.getLogger('figure1.admin.campaign')


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.sync_promo_card')
def sync_promo_card_task(self: FirebaseTaskBase, *args, **kwargs):
    """
    Case uuid
    :param self:
    :param case_uuid: This paramater is required, the case_uuid of the promo card to operate on
    :param user_uid: Syncs to this user uid only
    :param preview_users: Boolean value.  If True, then sync to preview users
    :param targeted_users: Boolean value.  If True, then sync to targeted users
    :return:
    """
    if 'case_uuid' not in kwargs:
        return "Case uuid is required"

    sync_promo_card(session=self.session,
                    batch=self.batch,
                    fs=self.fs_client,
                    **kwargs)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.sync_targeted_promo_cards')
def sync_targeted_promo_cards_task(self: FirebaseTaskBase, *args, **kwargs):
    if 'user_uuid' not in kwargs:
        return 'User uuid is required'

    sync_targeted_promo_cards(session=self.session,
                              batch=self.batch,
                              fs=self.fs_client,
                              **kwargs)


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.campaign.sync')
def sync_campaign_cases_task(self, *args, **kwargs):
    """
    Can take either case_uuid or campaign_uuid or both and syncs them to elasticsearch
    :param self:
    :param args:
    :param kwargs:
    :return:
    """
    sync_campaign_cases(session=self.session, **kwargs)


def sync_campaign_cases(case_uuid,
                        campaign_uuid,
                        session,
                        delete_case=False):
    if case_uuid:
        if delete_case:
            delete_case_from_es(case_uuid=case_uuid)
        else:
            add_or_update_case(case_uuid=str(case_uuid), session=session)

    if campaign_uuid:
        add_or_update_campaign(campaign_uuid=str(campaign_uuid), session=session)


def populate_template(promo_card_dict, user_uuid=None, case_uuid=None):
    """
    Populates the template for buttonLink in promo cards
    :param promo_card_dict:
    :param user_uuid:
    :param case_uuid:
    :return:
    """
    promo_card = copy.deepcopy(promo_card_dict)
    for k, v in promo_card_dict.items():
        if k == 'mobile' and isinstance(v, dict):
            app = MobileAppRoutes(userUuid=user_uuid, caseUuid=case_uuid)
            if v.get("buttonLink"):
                tmpl = env.from_string(v.get("buttonLink"))
                promo_card[k]['buttonLink'] = tmpl.render(app.dict())
        if k == 'web' and isinstance(v, dict):
            app = WebAppRoutes(userUuid=user_uuid, caseUuid=case_uuid)
            if v.get("buttonLink"):
                tmpl = env.from_string(v.get("buttonLink"))
                promo_card[k]['buttonLink'] = tmpl.render(app.dict())
    return promo_card


def sync_promo_card(case_uuid: str,
                    session,
                    fs,
                    user_uid: str = None,
                    preview_users: bool = False,
                    targeted_users: bool = False,
                    batch=None):
    """
    Syncs a promo card to users.  Supports three options for specifying users:

    If user_uid is not None, the promo card is only synced to that user
    Otherwise, if preview_users is True, the promo card is synced to all preview users of the campaign
    Finally, if targeted_users is True, the promo card is synced to all targeted users of the campaign

    Normally called through sync_promo_card_task which supplies batch, fs, and session.

    :param session:
    :param fs:
    :param batch:
    :param case_uuid:
    :param user_uid:
    :param preview_users:
    :param targeted_users:
    :return:
    """
    if fs and not batch:
        batch = fs.batch()

    if not fs:
        logger.error("No configured firestore client passed")
        return None

    def _get_fs_doc(uid: str):
        return fs.collection('usersDB') \
            .document(uid) \
            .collection('promoCards') \
            .document(case_uuid)

    count = 0

    campaign = session.query(CampaignCase).get(case_uuid)
    pc = PromoCardDetail.firestore_detail(case_uuid=case_uuid, session=session)

    if user_uid:
        u = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
        user_uuid = str(u.user_uuid)
        pc = populate_template(pc, user_uuid=user_uuid, case_uuid=case_uuid)
        doc = _get_fs_doc(uid=u.user_uid)
        batch.set(doc, pc)
    elif preview_users:
        for _, u in CampaignPreviewUser.get(campaign_uuid=campaign.campaign_uuid, session=session):
            doc = _get_fs_doc(uid=u.user_uid)
            user_uuid = str(u.user_uuid)
            pc_populated = populate_template(pc, user_uuid=user_uuid, case_uuid=case_uuid)
            batch.set(doc, pc_populated)
            count += 1
            if not count % 500:
                batch.commit()
    elif targeted_users:
        target = SponsoredContentTargets(caseUuid=case_uuid)
        for target_user_uid in target.get_user_uids():
            doc = _get_fs_doc(uid=target_user_uid[1])
            pc_populated = populate_template(pc, user_uuid=target_user_uid[0], case_uuid=case_uuid)
            batch.set(doc, pc_populated, merge=True)
            count += 1
            if not count % 500:
                batch.commit()
    else:
        raise ValueError("No users specified for promo card sync")

    if count:
        logger.info("Synced promo card %s to %d users", case_uuid, count)
    batch.commit()


def sync_targeted_promo_cards(user_uuid: str, session, fs, batch=None):
    """
    Syncs all approved, targeted promo cards for a user.
    :param session:
    :param batch:
    :param fs:
    :param user_uuid:
    :return:
    """

    if not fs:
        logger.error("No configured firestore client passed")
        return None

    if not batch:
        batch = fs.batch()

    count = 0

    u = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    if not u.user_uid:
        logger.error("User must have a uid to sync promo cards")
        return

    # Required to initialize targeting data
    UserDocument.get_user_target_data(user_uid=u.user_uid, session=session)

    sp = SponsoredContent(user_uuid=user_uuid)
    for case_uuid in sp.get_promo_card_ids():
        pc = PromoCardDetail.firestore_detail(case_uuid=case_uuid, session=session)
        populated_pc = populate_template(promo_card_dict=pc, user_uuid=str(user_uuid), case_uuid=str(case_uuid))
        doc = fs.collection('usersDB') \
            .document(u.user_uid) \
            .collection('promoCards') \
            .document(case_uuid)
        batch.set(doc, populated_pc)
        count += 1
        if not count % 500:
            batch.commit()

    logger.debug("Synced %d promo cards to user %s", count, user_uuid)
    batch.commit()
