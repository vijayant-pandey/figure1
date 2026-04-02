import logging
from figure1.common.models.db import Campaign, CampaignCase, Content, UserProfile, User
from figure1.common.types import SpecialtyTreeModel
from figure1.exceptions import CampaignNotFound
from figure1.common.types import CampaignTactic
from typing import List, Optional

logger = logging.getLogger(__name__)


class CampaignDetail:
    @staticmethod
    def elasticsearch_campaign(campaign_uuid, session):
        campaign_data = CampaignDetail._campaign_detail(campaign_uuid=campaign_uuid, session=session)
        if not campaign_data:
            return None
        return campaign_data

    @staticmethod
    def tactic_details(case_uuid, session) -> CampaignTactic:
        return CampaignDetail._campaign_tactic_detail(case_uuid=case_uuid, session=session)

    @staticmethod
    def _get_campaign(session, campaign_uuid):
        campaign = session.query(Campaign).get(campaign_uuid)
        if campaign and campaign.deleted_at is None:
            return campaign
        raise CampaignNotFound

    @staticmethod
    def _get_target_countries(session, campaign_uuid):
        campaign = CampaignDetail._get_campaign(session=session, campaign_uuid=campaign_uuid)
        for tc in campaign.target_countries:
            if tc.deleted_at is None:
                yield {
                    'countryUuid': str(tc.country_uuid),
                    'countryName': tc.country.name if tc.country else None,
                    'path': str(tc.country.path) if tc.country else None,
                    'depth': len(tc.country.path) if tc.country else None,
                }

    @staticmethod
    def _get_target_specialties(session, campaign_uuid) -> Optional[List[SpecialtyTreeModel]]:
        campaign = CampaignDetail._get_campaign(session=session, campaign_uuid=campaign_uuid)
        for ts in campaign.target_specialties:
            if ts.deleted_at is None:
                yield str(ts.tree_uuid)

    @staticmethod
    def _campaign_tactic_detail(case_uuid, session) -> CampaignTactic:
        tactic_data = {}
        campaign_case = session.query(CampaignCase).get(case_uuid)
        campaign = session.query(Campaign).get(campaign_case.campaign_uuid)
        tactic_data.update({
            'campaignUuid': str(campaign.campaign_uuid),
            'campaignState': campaign.state.name,
            'campaignPriority': campaign.campaign_priority,
            'tacticPriority': campaign_case.tactic_priority,
            'tacticName': campaign_case.name,
            'verificationTarget': True,
            'languageTargets': 'EN',
            'countryTargets': [],
            'treeTargets': [],
        })
        if campaign_case.start_date:
            tactic_data.update({'startDate': str(campaign_case.start_date)})
        if campaign_case.end_date:
            tactic_data.update({'endDate': str(campaign_case.end_date)})
        logger.debug("Getting target countries")
        for target_country in CampaignDetail._get_target_countries(session=session,
                                                                   campaign_uuid=campaign.campaign_uuid):
            tactic_data['countryTargets'].append(target_country['countryUuid'])
        logger.debug("Getting target specialties")
        for target_specialty in CampaignDetail._get_target_specialties(session=session,
                                                                       campaign_uuid=campaign.campaign_uuid):
            tactic_data['treeTargets'].append(target_specialty)
        logger.debug("Parsing and returning tactic object %s", tactic_data)
        return CampaignTactic.parse_obj(tactic_data)

    @staticmethod
    def _campaign_detail(campaign_uuid, session):
        c = session.query(Campaign, UserProfile) \
            .filter(Campaign.campaign_uuid == campaign_uuid) \
            .join(UserProfile, UserProfile.user_uuid == Campaign.author_uuid, full=True) \
            .one_or_none()
        if not c:
            return None
        campaign_data = c[0].as_dict()
        cases = []
        for case in c[0].cases:
            cc = session.query(CampaignCase) \
                .filter(CampaignCase.campaign_uuid == campaign_uuid,
                        CampaignCase.case_uuid == case.case_uuid,
                        CampaignCase.deleted_at.is_(None)) \
                .one_or_none()
            if cc:
                content_uuids = session.query(Content.content_uuid) \
                    .filter(Content.case_uuid == cc.case_uuid) \
                    .order_by(Content.display_order) \
                    .all()

                tactic = {
                    'caseUuid': str(case.case_uuid),
                    'tacticPriority': cc.tactic_priority,
                    'caseState': case.state.name,
                    'name': str(cc.name),
                    'contentUuids': [str(x) for x, in content_uuids],
                }
                if cc.start_date:
                    tactic.update({
                        'startDate': str(cc.start_date)
                    })
                if cc.end_date:
                    tactic.update({
                        'endDate': str(cc.end_date),
                    })
                cases.append(tactic)

        target_languages = []
        for tl in c[0].target_languages:
            if tl.deleted_at is None:
                target_languages.append({
                    'language': tl.language
                })

        target_specialties = []
        for ts in CampaignDetail._get_target_specialties(session=session, campaign_uuid=campaign_uuid):
            target_specialties.append({'treeUuid': ts})

        preview_users = []
        for pu in c[0].preview_users:
            if pu.deleted_at is None:
                u = User.get_user_by_uuid(user_uuid=pu.user_uuid, session=session, raise_exception=False)
                if u:
                    preview_users.append({
                        'userUid': u.user_uid,
                        'userUuid': u.user_uuid,
                        'username': u.username,
                    })

        campaign_data.update({
            'cases': cases,
            'targetCountries': list(CampaignDetail._get_target_countries(session=session,
                                                                         campaign_uuid=campaign_uuid)),
            'targetSpecialties': target_specialties,
            'targetLanguages': target_languages,
            'previewUsers': preview_users,
        })

        archived_by_name = None
        if c[0].archived_by_uuid:
            md = session.query(UserProfile) \
                .filter(UserProfile.user_uuid == c[0].archived_by_uuid) \
                .one_or_none()
            archived_by_name = md.display_name if md else None

        campaign_data.update({
            'authorName': c[1].display_name if c[1] else None,
            'archivedByName': archived_by_name
        })

        return campaign_data
