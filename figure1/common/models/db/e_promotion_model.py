import uuid
import logging

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy import Column, String, Date, ARRAY, ForeignKey
from figure1.core import managed_session, Base, HasCreateUpdateTime
from sqlalchemy.orm import relationship


class PromotionChannels(Base, HasCreateUpdateTime):
    __tablename__ = "e_promotion_channels"
    channel_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    channel_name = Column(String(1000), nullable=False)

    def as_dict(self):
        return {
            'channel_uuid': str(self.channel_uuid),
            'channel_name': self.channel_name
        }


class Promotion(Base, HasCreateUpdateTime):
    __tablename__ = "e_promotion"

    promotion_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    promotion_name = Column(String(1024), nullable=True)
    promotion_tags = Column(ARRAY(String(1024)), default=[], nullable=True)
    channel_uuid = Column(UUID(as_uuid=True), ForeignKey(PromotionChannels.channel_uuid), nullable=False)
    promotion_publish_date = Column(Date, nullable=True)
    promotion_notes = Column(String(10000), nullable=True)
    channels = relationship("PromotionChannels")

    def as_dict(self):
        return {
            'promotion_uuid': str(self.promotion_uuid),
            'promotion_name': self.promotion_name,
            'promotion_tags': self.promotion_tags,
            'channel_uuid': str(self.channel_uuid),
            'promotion_publish_date': self.promotion_publish_date,
            'promotion_notes': self.promotion_notes
        }


class PromotionCases(Base, HasCreateUpdateTime):
    __tablename__ = "e_promotion_cases"
    case_id = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    case_alternate_caption = Column(String(10000), nullable=True)
    case_alternate_title = Column(String(10000), nullable=True)
    case_alternate_description = Column(String(10000), nullable=True)
    case_notes = Column(String(10000), nullable=True)
    promotion_uuid = Column(UUID(as_uuid=True), ForeignKey(Promotion.promotion_uuid), nullable=False, primary_key=True)

    def as_dict(self):
        return {
            'case_id': str(self.case_id),
            'case_alternate_caption': self.case_alternate_caption,
            'case_alternate_title': self.case_alternate_title,
            'case_alternate_description': self.case_alternate_description,
            'case_notes': self.case_notes,
            'promotion_uuid': str(self.promotion_uuid)
        }


class PromotionMethods:
    logger = logging.getLogger(__name__)

    @managed_session
    def create_or_update_promotion(self, channel_uuid,
                                   session=None,
                                   promotion_name=None,
                                   promotion_tags=[],
                                   promotion_publish_date=None,
                                   promotion_notes=None,
                                   promotion_uuid=None):
        chan = session.query(PromotionChannels).filter(PromotionChannels.channel_uuid == channel_uuid).one_or_none()
        if not chan:
            self.logger.error("Channel UUID does not exist")
        chan = chan.as_dict()
        if promotion_uuid:
            p = session.query(Promotion).filter(Promotion.promotion_uuid == promotion_uuid).one()
        else:
            p = Promotion()
            p.promotion_uuid = uuid.uuid4()
        p.channel_uuid = channel_uuid
        p.promotion_name = promotion_name
        p.promotion_tags = promotion_tags
        p.promotion_publish_date = promotion_publish_date
        p.promotion_notes = promotion_notes

        try:
            session.add(p)
            session.commit()
        except InvalidRequestError as ie:
            # TODO something better than this on failure
            return False
        promo_dict = p.as_dict()
        promo_dict['channel_name'] = chan['channel_name']
        return promo_dict

    @managed_session
    def add_or_update_case(self, case_id, promotion_uuid,
                           session=None,
                           case_alternate_caption=None,
                           case_alternate_title=None,
                           case_alternate_description=None,
                           case_notes=None):

        c = session.query(PromotionCases) \
            .filter(PromotionCases.promotion_uuid == promotion_uuid, PromotionCases.case_id == case_id) \
            .one_or_none()
        if not c:
            c = PromotionCases()
            c.promotion_uuid = promotion_uuid
            c.case_id = case_id
        c.case_alternate_caption = case_alternate_caption
        c.case_alternate_title = case_alternate_title
        c.case_alternate_description = case_alternate_description
        c.case_notes = case_notes
        try:
            session.add(c)
            session.commit()
        except InvalidRequestError as ie:
            # TODO something better than this on failure
            return False
        return c.as_dict()

    @managed_session
    def get_or_add_channel(self, channel, session=None):
        pr_chan = session.query(PromotionChannels).filter(PromotionChannels.channel_name == channel).one_or_none()
        if not pr_chan:
            pr_chan = PromotionChannels()
            pr_chan.channel_name = channel
            pr_chan.channel_uuid = uuid.uuid4()
        try:
            session.add(pr_chan)
            session.commit()
        except InvalidRequestError as ie:
            # TODO something better than this on failure
            return False
        return pr_chan.as_dict()

    @managed_session
    def get_all_channels(self, session=None):
        chan_list = []
        for chan in session.query(PromotionChannels).all():
            chan_list.append(chan.as_dict())
        return chan_list

    @managed_session
    def get_promotions_by_case(self, case_id, session=None):
        pr_list = []
        for pr in session.query(Promotion) \
                .join(PromotionCases, Promotion.promotion_uuid == PromotionCases.promotion_uuid) \
                .filter(PromotionCases.case_id == case_id) \
                .all():
            pr = pr.as_dict()
            if not pr:
                return pr_list
            pr_list.append(self.get_promotion(promotion_uuid=pr['promotion_uuid']))
        return pr_list

    @managed_session
    def get_all_cases(self, session=None):
        case_list = []
        for case in session.query(PromotionCases.case_id).distinct(PromotionCases.case_id).all():
            case_list.append(str(case[0]))
        return case_list

    @managed_session
    def get_promotion(self, promotion_uuid, session=None):
        prom = session.query(Promotion).filter(Promotion.promotion_uuid == promotion_uuid).one_or_none()
        if not prom:
            return {}
        prom = prom.as_dict()
        channel = session.query(PromotionChannels) \
            .filter(PromotionChannels.channel_uuid == prom['channel_uuid']) \
            .one_or_none() \
            .as_dict()
        prom['channel_name'] = channel['channel_name']
        prom['cases'] = []
        for c in session.query(PromotionCases).filter(PromotionCases.promotion_uuid == promotion_uuid).all():
            prom['cases'].append(c.as_dict())
        return prom

    @managed_session
    def get_all_promotions(self, session=None):
        for pr in session.query(Promotion). \
                join(Promotion.channels).all():
            pr = pr.as_dict()
            chan = session.query(PromotionChannels).filter(
                PromotionChannels.channel_uuid == pr['channel_uuid']).one().as_dict()
            pr['channel_name'] = chan['channel_name']
            pr['cases'] = []
            for cs in session.query(PromotionCases).filter(PromotionCases.promotion_uuid == pr['promotion_uuid']).all():
                pr['cases'].append(cs.as_dict())
            yield pr

    @managed_session
    def _delete_case(self, case_id, promotion_uuid, session=None):
        session.query(PromotionCases) \
            .filter(PromotionCases.case_id == case_id) \
            .filter(PromotionCases.promotion_uuid == promotion_uuid) \
            .delete()
        session.commit()

    @managed_session
    def _delete_promotion(self, promotion_uuid, session=None):
        session.query(Promotion).filter(Promotion.promotion_uuid == promotion_uuid).delete()

    @managed_session
    def delete_case(self, case_id, promotion_uuid, session=None):
        self._delete_case(case_id=case_id, promotion_uuid=promotion_uuid, session=session)

    @managed_session
    def delete_channel(self, channel_uuid, session=None):
        session.query(PromotionChannels).filter(PromotionChannels.channel_uuid == channel_uuid).delete()

    @managed_session
    def delete_promotion(self, promotion_uuid, session=None):
        pr = self.get_promotion(promotion_uuid=promotion_uuid)
        if not pr:
            return True
        if 'cases' in pr and isinstance(pr['cases'], list):
            for case in pr['cases']:
                self._delete_case(case_id=case['case_id'], promotion_uuid=promotion_uuid)
        self._delete_promotion(promotion_uuid=promotion_uuid)
