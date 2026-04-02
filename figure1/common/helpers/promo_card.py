from figure1.common.helpers import CaseDetail
from figure1.common.models.db import CampaignCase, Campaign
from figure1.common.types import PromoCardModel


class PromoCardDetail:
    @staticmethod
    def firestore_detail(case_uuid, session):
        """
        Gets the firestore dict for a promo card
        :param case_uuid:
        :param session:
        :return: Dict[str, Any]
        """
        case_detail = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        campaign_case = session.query(CampaignCase).get(case_uuid)
        campaign = session.query(Campaign).get(campaign_case.campaign_uuid)
        content_items = case_detail.get('contentItems')
        if not content_items:
            raise ValueError("Missing content for promo card")
        else:
            content = content_items[0]

        features = content.get('features')
        case_detail.update({
            **content,
            **features,
            "mobile": {
                "buttonLink": content.get('buttonUrl'),
                "showCard": features.get('showInMobile', False),
            },
            "web": {
                "buttonLink": content.get('buttonUrl'),
                "showCard": features.get('showInWeb', False),
            },
            "startDate": str(campaign_case.start_date) if campaign_case and campaign_case.start_date else None,
            "endDate": str(campaign_case.end_date) if campaign_case and campaign_case.end_date else None,
            "priority": campaign.campaign_priority + campaign_case.tactic_priority
        })
        pc = PromoCardModel.parse_obj(case_detail)
        return pc.dict()
