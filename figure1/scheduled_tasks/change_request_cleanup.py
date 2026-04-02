from figure1.core import celery_app
from figure1.core import TaskBase
from datetime import timedelta
from figure1.common.helpers.verification import close_expired_empty_change_requests


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.scheduled.change_request_cleanup')
def cleanup_change_request_task(self, close_from: timedelta = timedelta(days=2)):
    """
    Reverts open change requests that do not have a verification type associated with them
    :param self:
    :param close_from:
    :return:
    """
    close_expired_empty_change_requests(close_from=close_from, session=self.session)
