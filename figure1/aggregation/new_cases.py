import logging
from datetime import datetime
from datetime import timedelta
from typing import Tuple

from sqlalchemy.orm import Query

from figure1.common.models.db import Case
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import CaseReaction
from figure1.common.models.db import CaseSpecialtyV2
from figure1.common.models.db import Comment
from figure1.common.models.db import Content
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.models.db import User
from figure1.common.models.db import UserFollow
from figure1.common.models.db import UserSavedCase
from figure1.common.models.db import UserSpecialtyTreeV2
from figure1.common.types import CaseState
from figure1.common.types import CaseClassification
from figure1.common.types import CommentState
from figure1.core import celery_app
from figure1.core import TaskBase
from figure1.store import NewCaseHandler

logger = logging.getLogger('figure1.datafeed.new_cases')


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.generate_new_case_datafeed')
def regenerate_new_cases_task(self):
    NewCasesDatafeed.generate_new_cases(session=self.session)


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.add_new_case_datafeed')
def add_new_case_task(self, case_uuid):
    NewCasesDatafeed.get_user_targets_by_case(case_uuid=case_uuid, session=self.session)


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.new_case_datafeed.clean_expired')
def clean_expired_new_cases_task(self):
    NewCasesDatafeed.clean_old_cases(session=self.session)


class NewCasesDatafeed:

    @staticmethod
    def get_new_cases_query(since: timedelta = timedelta(days=7), max_comments=3, session=None) -> Query:
        """
        Look for new cases with no more than <max_comments> posted <since>
        :param since: A timedelta indicating how far back to go to consider a new case, defaults to 7 days
        :type since: timedelta
        :param max_comments: If there are more than <max_comments>, there is sufficient engagement, so ignore this case
        :type max_comments: int
        :param session: ORM session
        :return:
        """
        if not isinstance(since, timedelta):
            raise ValueError("Since must be a timedelta type")
        new_cases: Query = session.query(Case).filter(Case.published_at >= datetime.utcnow() - since,
                                                      Case.state == CaseState.APPROVED,
                                                      Case.group_uuid.is_(None),
                                                      Case.case_classification != CaseClassification.NONMEDICAL) \
            .join(Content).filter(Content.approved_comments_count <= max_comments) \
            .order_by(Case.published_at.asc())
        return new_cases

    @staticmethod
    def get_case_specialties(case_uuid, session):
        """
        Return specialties attached to a case
        :param case_uuid:
        :param session:
        :return:
        """
        for cs in session.query(CaseSpecialtyV2).filter(CaseSpecialtyV2.deleted_at.is_(None),
                                                        CaseSpecialtyV2.case_uuid == case_uuid).all():
            ob = cs.as_object()
            yield ob.specialtyUuid

    @staticmethod
    def get_tree_query_for_specialty(specialty_uuid=None, sub_specialty_uuid=None, profession_uuid=None) -> Query:
        q = Query([SpecialtyTreeV2])
        if sub_specialty_uuid is not None:
            q = q.filter(SpecialtyTreeV2.subspecialty_uuid == sub_specialty_uuid,
                         SpecialtyTreeV2.specialty_type == 'tree')
        elif specialty_uuid is not None:
            q = q.filter(SpecialtyTreeV2.specialty_v2_uuid == specialty_uuid, SpecialtyTreeV2.specialty_type == 'tree')
        elif profession_uuid is not None:
            q = q.filter(SpecialtyTreeV2.profession_uuid == profession_uuid, SpecialtyTreeV2.specialty_type == 'tree')
        else:
            raise ValueError("Generating a tree query requires one of the elements")
        return q

    @staticmethod
    def find_matching_user_specialty(case_specialty=None, session=None) -> Tuple[list, list]:
        """
        For a given specialty, return all matching professions, specialties, and subspecialties
        :param case_specialty:
        :param session:
        :return: Tuple[profession_tree_uuids, specialty_tree_uuids, sub_specialty_tree_uuids]
        """
        sub_spec_q = NewCasesDatafeed.get_tree_query_for_specialty(sub_specialty_uuid=case_specialty)
        spec_q = NewCasesDatafeed.get_tree_query_for_specialty(specialty_uuid=case_specialty)

        sub_spec_tree_uuids = [str(x.specialty_uuid) for x in sub_spec_q.with_session(session).all()]
        spec_tree_uuids = [str(x.specialty_uuid) for x in spec_q.with_session(session).all()]
        return spec_tree_uuids, sub_spec_tree_uuids

    @staticmethod
    def user_case_interactions(case_uuid, session) -> set:
        """
        Ensure a user has not interacted with this case. We do this by returning all forbidden user_uuids for this case.
        This is more efficient in this case since the case will not have many interactions yet.
        Specifically, this returns users who have:
        - Saved the case
        - Commented on the case
        - Followed the author
        - Reacted to the case

        :param case_uuid:
        :param session:
        :return:
        """
        interaction_set = set()
        user_saved_cases = UserSavedCase.users_saved_case(session=session, case_uuid=case_uuid)
        if user_saved_cases:
            for u in user_saved_cases:
                interaction_set.add(u)

        for k, v in CaseReaction.get_case_reactions(case_uuid=case_uuid, session=session).items():
            if v:
                for u in v:
                    interaction_set.add(u)

        for author in session.query(CaseAuthor.author_uuid).filter(CaseAuthor.case_uuid == case_uuid).all():
            interaction_set.add(str(author[0]))
            for f in UserFollow.get_user_followers(session=session, user_uuid=author[0]):
                interaction_set.add(str(f))

        for comment_author in session.query(Comment.author_uuid).join(Content) \
                .filter(Content.case_uuid == case_uuid, Comment.state == CommentState.APPROVED).all():
            interaction_set.add(str(comment_author[0]))

        return interaction_set

    @staticmethod
    def user_specialty_target_query() -> Query:
        return Query([UserSpecialtyTreeV2]).filter(UserSpecialtyTreeV2.is_primary.is_(True))

    @staticmethod
    def get_user_targets_by_case(case_uuid, session):
        """
        Go through users until we find enough targets for a given case. We are looking first for users who have a
         sub-specialty that is one of the case specialties, then a user specialty, and finally a profession. Users who
         match a case cannot be matched to another case. As a result, we have to go through all cases looking for each
          so that users get a more specific case.

        This should be triggered when a new case is posted

        :param case_uuid:
        :param session:
        :return:
        """
        specialties_tree_uuids = dict()
        ch = NewCaseHandler()
        ch.remove_new_case_queues(case_uuid=case_uuid)
        i_set = NewCasesDatafeed.user_case_interactions(case_uuid=case_uuid, session=session)
        case_specialties = list(NewCasesDatafeed.get_case_specialties(case_uuid=case_uuid, session=session))
        ss_user_search = NewCasesDatafeed.user_specialty_target_query()
        spec_user_search = NewCasesDatafeed.user_specialty_target_query()
        sub_specialty_tree_list = []
        specialty_tree_list = []

        for s in case_specialties:
            if s in specialties_tree_uuids:
                continue
            s, ss = NewCasesDatafeed.find_matching_user_specialty(case_specialty=s, session=session)
            sub_specialty_tree_list.extend(list(ss))
            specialty_tree_list.extend(list(s))
        ss_user_search = ss_user_search \
            .filter(UserSpecialtyTreeV2.tree_uuid.in_(sub_specialty_tree_list)).with_session(session)
        spec_user_search = spec_user_search \
            .filter(UserSpecialtyTreeV2.tree_uuid.in_(specialty_tree_list)).with_session(session)
        c = ss_user_search.count()
        user_list = []

        for u in ss_user_search.all():
            user_uuid = str(u.user_uuid)
            if user_uuid in i_set:
                continue
            user_list.append(user_uuid)

        ch.write_new_case(case=case_uuid, users=user_list, score=2, interacted_set=i_set)
        if c < 1000:
            user_list = []
            for u in spec_user_search.all():
                user_uuid = str(u.user_uuid)
                if user_uuid in i_set:
                    continue
                user_list.append(str(u.user_uuid))
            c = c + spec_user_search.count()
            ch.write_new_case(case=case_uuid, users=user_list, score=1)
        logger.info("Found %s users for new case %s", c, case_uuid)

    @staticmethod
    def clean_old_cases(session):
        """
        Call on a schedule to remove old cases, and add new ones. This also removes cases that no longer meet the
        criteria to be promoted.
        :param session:
        :return:
        """
        ch = NewCaseHandler()
        cq = NewCasesDatafeed.get_new_cases_query(session=session)
        new_case_uuids = []
        new_case_queue = ch.get_new_cases_list()
        for i in cq.all():
            new_case_uuids.append(str(i.case_uuid))
            if str(i.case_uuid) not in new_case_queue:
                NewCasesDatafeed.get_user_targets_by_case(case_uuid=str(i.case_uuid), session=session)

        for case in new_case_queue:
            if case not in new_case_uuids:
                ch.remove_new_case_queues(case_uuid=case)

    @staticmethod
    def generate_new_cases(session=None):
        """
        This can be called to completely regenerate the list of new cases, this can take a few minutes to run.
        :return:
        """
        user_recommends = dict()
        cq = NewCasesDatafeed.get_new_cases_query(session=session)
        for i in cq.all():
            case_uuid = str(i.case_uuid)
            user_recommends.update({case_uuid: {}})
        for k, v in user_recommends.items():
            NewCasesDatafeed.get_user_targets_by_case(case_uuid=str(k), session=session)
        NewCasesDatafeed.clean_old_cases(session=session)

    @staticmethod
    def get_all_new_cases():
        """
        Returns a list of cases currently set as new cases
        :return:
        """
        ch = NewCaseHandler()
        return ch.get_new_cases_list()

    @staticmethod
    def get_new_case(session, cases_per_user=10, user_uuid=None):
        """
        If a user_uuid passed in, get the number of new cases recommended for this user.
        :param session:
        :param cases_per_user:
        :param user_uuid:
        :return:
        """
        ch = NewCaseHandler()
        if user_uuid is not None:
            u = User.get_user_by_uuid(user_uuid=user_uuid, raise_exception=True, session=session)
            for i in range(0, cases_per_user):
                r = ch.get_new_case_by_user(user_uuid=str(u.user_uuid))
                yield dict(username=u.username, user_uuid=str(u.user_uuid), email=u.email, user_uid=u.user_uid,
                           case_uuid=r)
        else:
            for u in session.query(User).filter(User.deleted_at.is_(None)).order_by(User.created_at.desc()).limit(
                    10).all():
                for i in range(1, cases_per_user):
                    r = ch.get_new_case_by_user(user_uuid=str(u.user_uuid))
                    yield dict(username=u.username, user_uuid=str(u.user_uuid), email=u.email, user_uid=u.user_uid,
                               case_uuid=r)

                logger.info("Recommended case %s for user %s", r, str(u.user_uuid))
                yield dict(username=u.username, user_uuid=str(u.user_uuid), email=u.email, user_uid=u.user_uid,
                           case_uuid=r)

    @staticmethod
    def get_sent_queue():

        ch = NewCaseHandler()
        return list(ch.get_sent_cases())
