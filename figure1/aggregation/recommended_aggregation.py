import logging
from figure1.events import AggregationEvents
from figure1.core import celery_app, TaskBase, managed_session
from figure1.store import Recommended
from figure1.common.models.db import UserRecommendedCase

logger = logging.getLogger('figure1.datafeed')


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.generate_user_recommendation_profile')
def generate_user_recommendations_task(self):
    lock = Recommended.set_lock(task_id=self.request.id)
    if lock is False:
        logger.error("Max tasks running")
        return 'Max Tasks Running'

    set_recommended_history(session=self.session)

    logger.error("Generating recommendations for 2000 users in task %s", self.request.id)
    for u in Recommended.get_regenerate_user(count=2000):
        if not u:
            Recommended.delete_lock(task_id=self.request.id)
            return "No users to regenerate"
        update_recommended(user_uuid=u)
        Recommended.set_lock(task_id=self.request.id)
    logger.error("Generating recommendations for 1000 users in task %s complete", self.request.id)
    Recommended.delete_lock(task_id=self.request.id)


@managed_session
def set_recommended_history(session=None):
    """
    Add case to cases recommended
    :param session:
    :return:
    """
    sent_history = Recommended.get_sent_user_keys()
    if sent_history:
        for k, v in sent_history.items():
            c = UserRecommendedCase()
            c.case_uuid = v
            c.user_uuid = k
            c.deleted_at = None
            session.merge(c)
            session.flush()
        Recommended.delete_sent_user_keys()


def update_recommended(user_uuid):
    if isinstance(user_uuid, list):
        for u in user_uuid:
            update_recommended(user_uuid=u)
    else:
        case_uuid = AggregationEvents.GENERATE_RECOMMENDATION(user_uuid=user_uuid)
        if case_uuid:
            logger.info("Recommended case %s for user %s ", case_uuid, user_uuid)
            Recommended.add_user_recommended_case(user_uuid=user_uuid, case_uuid=case_uuid)
