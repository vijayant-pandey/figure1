import logging
from elasticsearch.helpers import bulk
from figure1.common.models.db import CaseReaction, Comment, Content, CaseAnalytics, CaseLabel, Label, Case
from figure1.configuration import es_settings
from sqlalchemy import func
from figure1.common.utils import date_utils
from figure1.core import TaskBase, celery_app
from figure1.core import es

logger = logging.getLogger("figure1.task.trend_score")


def get_case_labels(session, case_uuid):
    case_labels = []
    for label in session.query(Label) \
            .filter(CaseLabel.case_uuid == case_uuid) \
            .join(CaseLabel, CaseLabel.label_uuid == Label.label_uuid) \
            .all():
        case_labels.append(label.kind)
    return case_labels


def do_trend_update(session):
    trends = {}
    trending_label_uuid = session.query(Label).filter(Label.kind == 'trending').one()
    logger.info("Fetching Case reactions for the last week")
    for cr in session.query(func.count(CaseReaction.case_reaction), CaseReaction.case_uuid) \
            .filter(CaseReaction.updated_at >= date_utils.last_week(timezone=True)) \
            .group_by(CaseReaction.case_uuid).all():
        reaction_count = int(cr[0] / 2)
        if cr[1] not in trends:
            trends.update({cr[1]: reaction_count})
        else:
            trends[cr[1]] += reaction_count

    logger.info("Fetching comments for the last week")
    for com in session.query(func.count(Comment.comment_uuid), Content.case_uuid) \
            .filter(Comment.updated_at >= date_utils.last_week(timezone=True)) \
            .join(Content, Comment.content_uuid == Content.content_uuid) \
            .group_by(Content.case_uuid).all():
        if com[1] not in trends:
            trends.update({com[1]: com[0]})
        else:
            trends[com[1]] += com[0]

    logger.info("Add trend scores into Case analytics")
    for k in trends.keys():
        logger.debug("Updating %s with score %d", k, trends[k])
        ca = session.query(CaseAnalytics).get(k)
        if ca:
            ca.trend_score = trends[k]
        else:
            ca = CaseAnalytics()
            ca.case_uuid = k
            ca.trend_score = trends[k]
            session.add(ca)
    logger.info("Update existing case analytics entries")
    for c in session.query(CaseAnalytics) \
            .filter(CaseAnalytics.updated_at <= date_utils.last_week(timezone=True), CaseAnalytics.trend_score > 0) \
            .all():

        c.trend_score = c.trend_score / 2
        if c.trend_score < 2:
            session.delete(c)
        else:
            session.add(c)
    session.flush()

    logger.info("Updating elasticsearch documents")

    for update_trend in session.query(CaseAnalytics).filter(CaseAnalytics.trend_score > 0).all():
        case_labels = get_case_labels(session=session, case_uuid=update_trend.case_uuid)
        logger.info("Got case labels %s", case_labels)
        # Only add the trending label if the case is in approved state - this should exempt all spon-con
        if session.query(Case) \
                .filter(Case.state != 'APPROVED',
                        Case.case_uuid == update_trend.case_uuid) \
                .one_or_none():
            CaseLabel.delete(case_uuid=update_trend.case_uuid,
                             label_uuid=trending_label_uuid.label_uuid,
                             session=session)

            if 'trending' in case_labels:
                case_labels.remove('trending')
                logger.info("Removing trending case label, %s", case_labels)
            yield {
                "_op_type": "update",
                "_index": es_settings.cases_alias,
                "_id": str(update_trend.case_uuid),
                "doc": {
                    "labels": case_labels,
                    "trendScore": 0,
                }
            }

        # Remove trending label if the score is 0
        if update_trend.trend_score == 0:
            CaseLabel.delete(case_uuid=update_trend.case_uuid,
                             label_uuid=trending_label_uuid.label_uuid,
                             session=session)
            if 'trending' in case_labels:
                case_labels.remove('trending')
                logger.info("Removing trending case label, %s", case_labels)
            yield {
                "_op_type": "update",
                "_index": es_settings.cases_alias,
                "_id": str(update_trend.case_uuid),
                "doc": {
                    "labels": case_labels,
                    "trendScore": 0,
                }
            }
            continue

        if update_trend.trend_score != 0:
            CaseLabel.create(case_uuid=update_trend.case_uuid,
                             label_uuid=trending_label_uuid.label_uuid,
                             session=session)
            if 'trending' not in case_labels:
                case_labels.append('trending')
            yield {
                "_op_type": "update",
                "_index": es_settings.cases_alias,
                "_id": str(update_trend.case_uuid),
                "doc": {
                    "labels": case_labels,
                    "trendScore": update_trend.trend_score,
                }
            }
    session.commit()


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.update_trending')
def update_trending_records(self):
    """
    First, count all reactions and comments in the last 4 hours. This becomes the new trend score.
    Second, for all cases that did not have a trend score change in the last 4 hours, divide the existing trend
    score by 2. This will round down eventually ending with a trend score of 0.

    """
    bulk(es, do_trend_update(session=self.session), chunk_size=10000, raise_on_error=False)
