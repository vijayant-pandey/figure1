import logging
from typing import Optional
from elasticsearch_dsl import Search
from elasticsearch_dsl import A
from elasticsearch_dsl import Q
from elasticsearch_dsl import SF

from figure1.common.types import CaseClassification
from figure1.common.types.elasticsearch import ESUserDocument
from figure1.core import es
from figure1.core import celery_app
from figure1.core import TaskBase
from figure1.core import managed_session
from figure1.store import Recommended
from figure1.configuration import es_settings
from figure1.common.models.db import Comment
from figure1.common.models.db import Content
from figure1.common.models.db import CaseReaction
from figure1.common.models.db import UserSavedCase
from figure1.common.models.db import UserInterest
from figure1.common.models.db import UserSpecialtyTreeV2
from figure1.common.models.db import UserRecommendedCase

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='figure1.backend.event.on_save_case', base=TaskBase)
def on_case_save_task(self, user_uuid):
    on_case_save(user_uuid=user_uuid, session=self.session)
    Recommended.regenerate_user(str(user_uuid))


@celery_app.task(bind=True, name='figure1.backend.event.on_new_reaction', base=TaskBase)
def on_new_reaction_task(self, user_uuid):
    on_new_reaction(user_uuid=user_uuid, session=self.session)
    Recommended.regenerate_user(str(user_uuid))


@celery_app.task(bind=True, name='figure1.backend.event.on_new_comment', base=TaskBase)
def on_new_comment_task(self, user_uuid):
    on_new_comment(user_uuid=user_uuid, session=self.session)
    Recommended.regenerate_user(str(user_uuid))


@celery_app.task(bind=True, name='figure1.backend.user_profile.update', base=TaskBase)
def update_user_profile(self, user_uuid):
    regenerate_user_profile(user_uuid=user_uuid)


@managed_session
def get_recommended_history(user_uuid, session):
    """
    Returns a generator of <case_uuid>, <created_at> tuples for a given user
    :param user_uuid:
    :param session:
    :return:
    """
    for r in session.query(UserRecommendedCase) \
            .filter(UserRecommendedCase.user_uuid == user_uuid, UserRecommendedCase.deleted_at.is_(None)) \
            .all():
        yield str(r.case_uuid), r.created_at


def _get_elasticsearch_user(user_uuid) -> ESUserDocument:
    return ESUserDocument.get(id=str(user_uuid), index=es_settings.users_alias, using=es, ignore=404)


@managed_session
def on_new_comment(user_uuid, session) -> Optional[ESUserDocument]:
    user = _get_elasticsearch_user(str(user_uuid))
    if not user:
        return
    user.caseComments = []
    q = session.query(Comment.content_uuid) \
        .filter(Comment.author_uuid == user_uuid) \
        .order_by(Comment.created_at.desc())
    if q.count() == 0:
        return user
    for c in q.all():
        case = session.query(Content.case_uuid).filter(Content.content_uuid == c[0]).one_or_none()
        if case and str(case[0]) not in list(user.caseComments):
            user.caseComments.append(str(case[0]))
    user.save(using=es, index=es_settings.users_alias)
    return user


@managed_session
def on_new_reaction(user_uuid, session) -> Optional[ESUserDocument]:
    user = _get_elasticsearch_user(str(user_uuid))
    if not user:
        return
    user.caseReactions = []
    q = session.query(CaseReaction.case_uuid) \
        .filter(CaseReaction.user_uuid == user_uuid, CaseReaction.deleted_at.is_(None)) \
        .order_by(CaseReaction.created_at.desc())
    if q.count() == 0:
        return user
    for c in q.limit(10).all():
        user.caseReactions.append(str(c[0]))
    user.save(using=es, index=es_settings.users_alias)
    return user


def on_interest_update(user_uuid, session):
    pass


@managed_session
def on_case_save(user_uuid, session) -> Optional[ESUserDocument]:
    user = _get_elasticsearch_user(str(user_uuid))
    if not user:
        return
    user.caseSaved = []
    q = session.query(UserSavedCase.case_uuid) \
        .filter(UserSavedCase.user_uuid == user_uuid, UserSavedCase.deleted_at.is_(None)) \
        .order_by(UserSavedCase.created_at.desc())
    if q.count() == 0:
        return user
    for c in q.limit(10).all():
        user.caseSaved.append(str(c[0]))
    user.save(using=es, index=es_settings.users_alias)
    return user


def regenerate_user_profile(user_uuid) -> Optional[ESUserDocument]:
    """
    Aggregates data from user activity. Only relies on data within elasticsearch.

    :param user_uuid:
    :return:
    """
    user = _get_elasticsearch_user(user_uuid=user_uuid)
    if not user:
        return None
    q = Search(using=es, index=es_settings.cases_alias)
    if user.caseSaved:
        user.caseSavedTopMeshTerms = []
        user.caseSavedTopSpecialties = []
        sc = q.__copy__()
        sc.aggs.bucket('specialtyUuids', A("terms", field="specialtyUuids"))
        sc.aggs.bucket('meshTerms', A("terms", field="meshTerms"))
        sc = sc.query(
            Q('bool', must=[Q("terms", caseUuid=list(user.caseSaved))], filter=Q('term', caseState='APPROVED')))
        resp = sc.execute()
        for mt in resp.aggregations.meshTerms.buckets:
            user.caseSavedTopMeshTerms.append(mt.key)
        for spec in resp.aggregations.specialtyUuids.buckets:
            user.caseSavedTopSpecialties.append(spec.key)
    else:
        u = on_case_save(user_uuid=user_uuid)
        if u:
            user = u
    if user.caseReactions:
        cr = q.__copy__()
        cr = cr.query(Q('bool', must=[Q("terms", caseUuid=list(user.caseReactions))],
                        filter=Q('term', caseState='APPROVED')))
        cr.aggs.bucket('specialtyUuids', A("terms", field="specialtyUuids"))
        cr.aggs.bucket('meshTerms', A("terms", field="meshTerms"))
        resp = cr.execute()
        user.caseReactionsTopSpecialties = []
        user.caseReactionsTopMeshTerms = []
        for mt in resp.aggregations.meshTerms.buckets:
            user.caseReactionsTopMeshTerms.append(mt.key)
        for spec in resp.aggregations.specialtyUuids.buckets:
            user.caseReactionsTopSpecialties.append(spec.key)
    else:
        u = on_new_reaction(user_uuid=user_uuid)
        if u:
            user = u
    if user.caseComments:
        c = q.__copy__()
        c = c.query(Q('bool', filter=[Q("terms", caseUuid=list(user.caseComments))]))
        c.aggs.bucket('specialtyUuids', A("terms", field="specialtyUuids"))
        c.aggs.bucket('meshTerms', A("terms", field="meshTerms"))
        resp = c.execute(ignore_cache=True)
        user.caseCommentsTopMeshTerms = []
        user.caseCommentsTopSpecialties = []
        for mt in resp.aggregations.meshTerms.buckets:
            user.caseCommentsTopMeshTerms.append(mt.key)
        for spec in resp.aggregations.specialtyUuids.buckets:
            user.caseCommentsTopSpecialties.append(spec.key)
    else:
        u = on_new_comment(user_uuid=user_uuid)
        if u:
            user = u
    user.save(using=es, index=es_settings.users_alias)
    return user


def generate_recommended_case(user_uuid, recommended=None):
    """
        Given a user_uuid and a list of caseUuids to never return, send back a recommended case. This runs several
        aggregations, so it is not intended to be used inline.

        :param user_uuid:
        :param recommended:
        :return:
        """
    if not recommended:
        recommended = [x[0] for x in list(get_recommended_history(user_uuid=user_uuid))]
    if not isinstance(recommended, list):
        recommended = [recommended]

    user = regenerate_user_profile(user_uuid)

    if not user:
        logger.error("No user found")
        return {}
    bool_should = []

    if user.caseReactionsTopSpecialties:
        bool_should.append(Q("terms", specialtyUuids=list(user.caseReactionsTopSpecialties), boost=1.0))
    if user.caseCommentsTopSpecialties:
        bool_should.append(Q("terms", specialtyUuids=list(user.caseCommentsTopSpecialties), boost=1.2))
    if user.caseSavedTopSpecialties:
        bool_should.append(Q("terms", specialtyUuids=list(user.caseSavedTopSpecialties), boost=1.3))

    userInterests = UserInterest.q.filter(UserInterest.user_uuid == user_uuid, UserInterest.deleted_at.is_(None)).all()
    if userInterests:
        userInterestUuids = [str(x.interest_uuid) for x in userInterests]
        bool_should.append(Q("terms", specialtyUuids=userInterestUuids, boost=1.1))

    userSpecialties_inst = UserSpecialtyTreeV2.q.filter(UserSpecialtyTreeV2.user_uuid == user_uuid,
                                                        UserSpecialtyTreeV2.is_primary.is_(True),
                                                        UserSpecialtyTreeV2.deleted_at.is_(None)).first()
    if userSpecialties_inst:
        userSpecialties = userSpecialties_inst.as_object()

        if userSpecialties:
            if userSpecialties.tree.subspecialty and userSpecialties.tree.subspecialty.isValidInterest:
                bool_should.append(
                    Q("terms", specialtyUuids=[userSpecialties.tree.subspecialty.specialtyUuid], boost=1.3))
            if userSpecialties.tree.specialty and userSpecialties.tree.specialty.isValidInterest:
                bool_should.append(Q("terms", specialtyUuids=[userSpecialties.tree.specialty.specialtyUuid], boost=1.1))

    q = Search(index=es_settings.cases_alias, using=es)
    fs_query = Q('bool', should=bool_should,
                 must_not=[Q("terms", caseUuid=recommended),
                           Q("term", isAnonymous=True),
                           Q("exists", field="groupUuid"),
                           Q("term", caseClassification=CaseClassification.NONMEDICAL.value)],
                 filter=[Q("term", caseState="APPROVED")])
    trend_score = SF('field_value_factor', missing=1, field="trendScore", factor=1.0, modifier="log2p")
    published_score = SF('exp', publishedAt=dict(scale="7d", decay=0.9))
    fs = Q('function_score',
           score_mode="sum",
           boost_mode="sum",
           query=fs_query,
           functions=[trend_score, published_score])

    q = q.query(fs)
    resp = q.execute()
    if resp.success and resp.hits:
        for h in resp.hits:
            res = h.to_dict()
            return res['caseUuid']
