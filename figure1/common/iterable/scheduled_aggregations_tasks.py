import logging
from pydantic import ValidationError
from figure1.common.types import CommentModel
from figure1.notifications.iterable import BaseAggregateEvent
from figure1.notifications.iterable import IterableAggregateEvent
from figure1.notifications.iterable import IterableAggregateEventWrapper
from figure1.notifications.iterable import CaseAggregateEvent

from crontab import CronTab
from sqlalchemy import func

from figure1.exceptions import UserError
from figure1.core import TaskBase
from figure1.core import managed_session
from figure1.core import celery_app
from figure1.store import TaskLock
from figure1.store import TaskQueue
from figure1.common.helpers import UserDocument
from figure1.common.models.db import CaseReaction
from figure1.common.models.db import Comment
from figure1.common.models.db import Case
from figure1.common.models.db import UserFollow
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import Content
from datetime import datetime
from datetime import timezone
from datetime import timedelta

from .api import IterableAPI
from figure1.common.models.db import UserScheduledAggregations
from figure1.common.models.db import AggregateEvents

logger = logging.getLogger(__name__)

"""
Aggregation Events
These events are intended to run on a schedule. The find_new_tasks task is the entry point here, to add a new event,
start with adding a function that finds runnable tasks for your event.

"""


def add_scheduled_aggregation_tasks(sender, **kwargs):
    """
    This is triggered from figure1.__init__ to add a scheduled task
    :param sender:
    :param kwargs:
    :return:
    """
    sender.add_periodic_task(1800, find_new_tasks.si(), name='Look for new runnable tasks every 30 minutes')


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.check_for_runnable_tasks')
def find_new_tasks(self):
    """
    This task is solely meant to run on a schedule to determine if there are any tasks to run. In most cases,
    this means running a function that is specific to a given task or event.

    :param self:
    :return:
    """
    generate_case_summary_task(session=self.session)


def user_follower_count_aggregate(user_uuid, last_run_date, session):
    """
    Returns the number of followers added since last_run_date. In the event of a negative number, 0 is returned
    :param user_uuid:
    :param last_run_date:
    :param session:
    :return: Positive integer
    """
    return session.query(UserFollow.user_uuid) \
        .filter(UserFollow.deleted_at.is_(None),
                UserFollow.updated_at >= last_run_date,
                UserFollow.user_uuid == user_uuid) \
        .count()


def user_case_reaction_aggregate(user_uuid, last_run_date, session):
    """
    Returns a model populated with cases with reactions since last_run_date, the user_uuid is the author of the case
    :param user_uuid:
    :param last_run_date:
    :param session:
    :return: Dict of {<case_uuid>: reaction_count}
    """
    cr = {}
    case_reaction_query = session.query(CaseReaction.case_uuid, func.count('1')) \
        .join(CaseAuthor, CaseAuthor.author_uuid == user_uuid) \
        .filter(CaseReaction.created_at >= last_run_date,
                CaseReaction.deleted_at.is_(None),
                CaseReaction.case_uuid == CaseAuthor.case_uuid) \
        .group_by(CaseReaction.case_uuid)

    for reaction in case_reaction_query.all():
        cr.update({str(reaction[0]): reaction[1]})
    return cr


def user_case_comment_aggregate(last_run_date, session, case_author_uuid=None):
    """
    Returns a dictionary of models ( keyed by case_uuid ) populated with cases that have had comments since
    last_run_date. This can take a comment author uuid which will return any cases with comments authors by that user
     that have had new comments since the last run.
    This can also take a case_author_uuid which will look for new comments since the last run on cases authored by
    this user_uuid
    Only one can be passed, if both are passed, then comment_author_uuid is used.

    :param case_author_uuid:
    :param comment_author_uuid:
    :param last_run_date:
    :param session:
    :return: Dict of CaseAggregateEvent models keyed by case_uuid
    """

    case_aggregate = {}
    aggregate_query = None
    if case_author_uuid:
        aggregate_query = session.query(Comment, Content) \
            .join(Content, Content.content_uuid == Comment.content_uuid) \
            .join(Case, Case.case_uuid == Content.case_uuid) \
            .join(CaseAuthor, CaseAuthor.case_uuid == Case.case_uuid) \
            .filter(Comment.created_at >= last_run_date,
                    CaseAuthor.author_uuid == case_author_uuid,
                    Comment.state == 'APPROVED',
                    Case.state == 'APPROVED')
    else:
        return {}

    for c in aggregate_query.all():

        case_uuid = str(c[1].case_uuid)
        comment_model = CommentModel.from_orm(c[0])

        if case_uuid not in case_aggregate:
            event_model = CaseAggregateEvent(caseCaption=c[1].caption, caseTitle=c[1].title, caseUuid=case_uuid)
            case_aggregate.update({case_uuid: event_model})
        case_aggregate[case_uuid].comments.append(comment_model)
        case_aggregate[case_uuid].commentCount += 1
    return case_aggregate


def handle_summary_event_by_case_author(user_uuid, last_run_date, session):
    """
    Groups together events based on the case author.

    :param user_uuid:
    :param last_run_date:
    :return: BaseAggregateEvent model
    """

    case_aggregate = user_case_comment_aggregate(last_run_date=last_run_date,
                                                 case_author_uuid=user_uuid,
                                                 session=session)
    case_reactions = user_case_reaction_aggregate(user_uuid=user_uuid,
                                                  last_run_date=last_run_date,
                                                  session=session)

    for cr, cr_count in case_reactions.items():
        if cr in case_aggregate:
            case_aggregate[cr].reactionCount = cr_count
        else:
            content = session.query(Content.caption, Content.title).filter(Content.case_uuid == cr).one_or_none()
            if not content:
                continue
            event_model = CaseAggregateEvent(caseCaption=content[0],
                                             caseTitle=content[1],
                                             caseUuid=cr,
                                             reactionCount=cr_count)
            case_aggregate.update({cr: event_model})

    base_aggregate_event = BaseAggregateEvent()
    for case_uuid, model in case_aggregate.items():
        base_aggregate_event.cases.append(model)
        base_aggregate_event.totalCommentCount += model.commentCount
        base_aggregate_event.totalReactionCount += model.reactionCount
    base_aggregate_event.totalFollowerCount = user_follower_count_aggregate(user_uuid=user_uuid,
                                                                            last_run_date=last_run_date,
                                                                            session=session)

    return base_aggregate_event


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.handle_case_author_summary_aggregation')
def handle_summary_event_by_case_author_task(self, user_uuid=None):
    """
    This task essentially decides if the aggregate should run and sets the last_run_date. The work is done by
    handle_summary_event_by_case_author which returns a populated base Aggregate event.
    Passing a user_uuid is optional, if one isn't passed, then use the queue for this task.
    :param self:
    :param user_uuid:
    :return:
    """
    tl = TaskLock('summary_by_case_author')
    if not tl.create_lock(self.request.id):
        logger.error("Failed to acquire lock")
        return

    tq = TaskQueue('summary_by_case_author')
    if not user_uuid and not tq.get_queue_len():
        logger.info("Nothing in the queue")
        tl.unlock(self.request.id)
        return
    if user_uuid:
        tq.write_queue([user_uuid])

    while True:
        if not tq.get_queue_len():
            logger.info("No items left in queue")
            break
        user_uuid = tq.get_item()
        try:
            user = UserDocument.user_detail(user_uuid=user_uuid, session=self.session)
        except UserError:
            logger.exception("Caught error for user %s, skipping", user_uuid)
            continue

        except ValidationError:
            logger.exception("User validation failed")
            continue

        summary_setting = self.session.query(UserScheduledAggregations) \
            .filter(UserScheduledAggregations.user_uuid == user_uuid,
                    UserScheduledAggregations.event_name == 'SUMMARY_BY_CASE_AUTHOR').one_or_none()

        if not summary_setting:
            logger.error("No task entry for this user %s", user_uuid)
            continue

        if summary_setting.last_run_date:
            if summary_setting.last_run_date >= (datetime.now(tz=timezone.utc) - timedelta(seconds=14400)):
                logger.info("Likely a duplicate task - skipping for user ( %s )", summary_setting.user_uuid)
                continue

            last_run_date = summary_setting.last_run_date
        else:
            c = CronTab(summary_setting.event_schedule)
            last_run_date = datetime.fromtimestamp(c.previous(delta=False, default_utc=True), tz=timezone.utc)

        iterable_api = IterableAPI()
        if iterable_api.iterable_api_disabled:
            logger.error("Iterable api is disabled")
            continue

        baseAggregate = handle_summary_event_by_case_author(user_uuid=user_uuid,
                                                            session=self.session,
                                                            last_run_date=last_run_date)

        # SUMMARY_BY_CASE_AUTHOR event is not needed per Stephanie Meszaros 10/10/2024
        # event = IterableAggregateEvent.parse_obj(user)
        # event.event = baseAggregate
        # summary_setting.last_run_date = datetime.utcnow()
        # self.session.add(summary_setting)

        # event_wrapper = IterableAggregateEventWrapper(dataFields=event,
        #                                               email=event.email,
        #                                               eventName='SUMMARY_BY_CASE_AUTHOR')

        # logger.debug("Generated event %s", event_wrapper.json())

        # iterable_api.track_event(event_wrapper=event_wrapper)

    logger.info("Exiting aggregation task")


def find_case_authors(session, limit):
    """
    Return only authors without an entry
    :param session:
    :param limit:
    :return:
    """
    case_author_list_query = session.query(CaseAuthor.author_uuid) \
        .join(UserScheduledAggregations,
              CaseAuthor.author_uuid == UserScheduledAggregations.user_uuid,
              full=True).filter(UserScheduledAggregations.user_uuid.is_(None)) \
        .group_by(CaseAuthor.author_uuid)

    if limit:
        return [str(author[0]) for author in case_author_list_query.limit(limit).all()]
    return [str(author[0]) for author in case_author_list_query.all()]


@managed_session
def generate_case_summary_task(session, limit=0, force=False, user_uuid=None):
    """
    Look for any new case authors. Usually called by scheduled task, but may be called directly. When it is called
    by scheduled task, there are no additional parameters passed.
    This function also checks to ensure that the task did not run inside the window that exists between scheduling
    and running.

    :param session:
    :param limit: Only process this number of users
    :param force: Ignore the scheduled time, and run now. Note that this parameter still respects the last_run_date
    :param user_uuid: If passed, only run this user_uuid
    :return:
    """
    case_summary = AggregateEvents.SUMMARY_BY_CASE_AUTHOR
    tq = TaskQueue('summary_by_case_author')
    tl = TaskLock('summary_by_case_author')
    if user_uuid:
        scheduled = UserScheduledAggregations()
        scheduled.user_uuid = user_uuid
        scheduled.event_name = case_summary.name.upper()
        scheduled.event_schedule = case_summary.value.default_schedule
        session.merge(scheduled)
        session.commit()
        handle_summary_event_by_case_author_task.delay(user_uuid)
        return

    if tq.get_queue_len():
        if tl.check_lock_status(task_id='None') is None:
            handle_summary_event_by_case_author_task.delay()
        return
    author_list = find_case_authors(session=session, limit=limit)
    task_query = session.query(UserScheduledAggregations) \
        .filter(UserScheduledAggregations.event_name == case_summary.name.upper()) \
        .order_by(UserScheduledAggregations.last_run_date)

    if limit:
        task_query = task_query.limit(limit)
    task_list = set()

    for author in author_list:
        scheduled = UserScheduledAggregations()
        scheduled.user_uuid = author
        scheduled.event_name = case_summary.name.upper()
        scheduled.event_schedule = case_summary.value.default_schedule
        scheduled.last_run_date = None
        session.add(scheduled)
        session.flush()

    for aggregate_task in task_query.all():
        c = CronTab(aggregate_task.event_schedule)
        if aggregate_task.last_run_date and force is False:
            if aggregate_task.last_run_date >= (datetime.now(tz=timezone.utc) - timedelta(seconds=14400)):
                logger.debug("Task ran too recently - skipping ( %s )", aggregate_task.user_uuid)
                continue

        if force:
            task_list.add(str(aggregate_task.user_uuid))
        if c.next(default_utc=True) <= 3600:
            task_list.add(str(aggregate_task.user_uuid))
    session.commit()
    tq.write_queue(list(task_list))
    handle_summary_event_by_case_author_task.delay()
