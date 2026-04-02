import logging
from datetime import timedelta
from datetime import timezone

from figure1.common.elasticsearch import add_or_update_case
from figure1.common.elasticsearch import get_related_cases
from figure1.common.helpers import CaseDetail
from figure1.common.helpers import CommentSync
from figure1.common.helpers import FeedCard
from figure1.common.models.db import Case
from figure1.common.models.db import CasePublications as CasePublicationsDB
from figure1.common.models.db import Content
from figure1.common.types import CaseState
from figure1.common.types import FirebaseAction
from figure1.common.types import PublicCaseStates
from figure1.common.types.versions import Version
from figure1.common.utils.date_utils import utc_now
from figure1.configuration import app_settings
from figure1.exceptions import CaseNotFound
from figure1.exceptions import CaseSyncThrottled

logger = logging.getLogger('case_detail_firestore')


class CaseDetailV2:
    firebase_collection = 'casesDBv2'
    version = Version(current=4, minimum=1)

    def __init__(self, path):
        self._path = path

    def set_comment_data(self, comment_data):
        return {
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": comment_data
        }

    def set_publication_data(self, publication_data):
        return {
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": publication_data.as_dict()
        }

    def set_user_case_data(self, user_case_data):
        return {
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": user_case_data
        }

    def set_case_detail(self, case_data):

        return {
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": case_data
        }

    def set_related_cases(self, related):
        return {
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": related
        }

    def delete(self):
        return {
            "path": self._path,
            "action": FirebaseAction.DELETE
        }

    def delete_collection(self):
        return {
            "path": self._path,
            "action": FirebaseAction.DELETE_COLLECTION
        }

    @staticmethod
    def sync(firebase_db, case_uuid, action, columns=None, session=None, **kwargs):
        case_detail_only = kwargs.get('case_detail_only', False)
        logger = logging.getLogger(__name__)
        throttle_seconds = app_settings.case_sync_throttle
        logger.info(f"Syncing case details for case uuid {case_uuid}")
        if not case_uuid:
            logger.error(f"No case_uuid was provided")
            return []
        c = session.query(Case).get(case_uuid)
        can_sync_to_firestore = True
        if c:
            if c.synced_at:
                if utc_now(timezone=timezone.utc) - timedelta(seconds=throttle_seconds) > c.synced_at:
                    logger.error("Can sync again, last sync at %s before %s", c.synced_at,
                                 utc_now(timezone=timezone.utc) - timedelta(seconds=throttle_seconds))
                elif c.state is CaseState.APPROVED or c.state is CaseState.SC_APPROVED:
                    logger.error("Do not sync")
                    can_sync_to_firestore = False
                else:
                    logger.error("Case is not in approved state, sync is not throttled, last sync at %s before %s",
                                 c.synced_at,
                                 utc_now(timezone=timezone.utc) - timedelta(seconds=throttle_seconds))
        else:
            logger.error("Unable to find case with uuid %s", case_uuid)
            return StopIteration
        if app_settings.case_sync_throttle_enabled is False:
            can_sync_to_firestore = True

        path = firebase_db.collection(CaseDetailV2.firebase_collection).document(str(case_uuid)).path
        sync_object = CaseDetailV2(path=path)
        try:
            case = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
            case.update({'version': CaseDetailV2.version.current})
        except CaseNotFound as nf:
            logger.error("Case not found: %s", nf)
            case = {'caseState': 'NOTFOUND'}
        else:
            add_or_update_case(case_uuid=str(case_uuid), session=session)

        if (case.get('caseState') not in [x for x in PublicCaseStates.__members__]) or \
                c.deleted_at:
            yield sync_object.delete()
            yield sync_object.set_case_detail(case_data=dict(caseState=case.get('caseState'),
                                                             caseUuid=str(case_uuid)))
            return StopIteration

        if case_detail_only:
            yield sync_object.set_case_detail(case_data=case)
            return StopIteration

        if can_sync_to_firestore:
            yield sync_object.set_case_detail(case_data=case)

            c.synced_at = utc_now(timezone=timezone.utc)
            session.add(c)

            related_cases_path = firebase_db \
                .collection(CaseDetailV2.firebase_collection) \
                .document(str(case_uuid)) \
                .collection('relatedCases')
            delete_related_cases = CaseDetailV2(path=related_cases_path)
            yield delete_related_cases.delete_collection()

            related_cases = get_related_cases(case_uuid=case_uuid)

            for r in related_cases['hits']['hits']:
                related = FeedCard.feed_card(feed_item=r)
                if related:
                    yield RelatedCasesV2.sync_search(firebase_db=firebase_db,
                                                     action=action,
                                                     case_uuid=case_uuid,
                                                     related=related)

            for publication in CasePublications.sync(firebase_db=firebase_db,
                                                     case_uuid=case_uuid,
                                                     action=action,
                                                     session=session):
                yield publication

        else:
            raise CaseSyncThrottled
        user_case_data = CaseDetail.case_actions(case_uuid=case_uuid, session=session)
        for user_uuid in user_case_data.keys():
            yield CaseUserActions.sync_user_data(firebase_db=firebase_db,
                                                 action=action,
                                                 case_uuid=str(case_uuid),
                                                 user_uuid=user_uuid,
                                                 user_case_data=user_case_data[user_uuid])


class RelatedCasesV2(CaseDetailV2):

    def __init__(self, path):
        super().__init__(path=path)

    @staticmethod
    def sync_search(firebase_db, action, case_uuid, related):
        path = firebase_db.collection(CaseDetailV2.firebase_collection) \
            .document(str(case_uuid)) \
            .collection('relatedCases') \
            .document(related.get('caseUuid')) \
            .path
        sync_object = CaseDetailV2(path=path)
        if action is FirebaseAction.SET:
            return sync_object.set_related_cases(related=related)


class CommentV2(CaseDetailV2):
    def __init__(self, path):
        super().__init__(path=path)

    @staticmethod
    def sync(firebase_db, case_uuid, action, columns=None, session=None, **kwargs):
        logger.info(f"Syncing comments for case uuid {case_uuid}")
        comment_content_item = Content.get_first_content_item(case_uuid=case_uuid, session=session)
        if not comment_content_item:
            logger.warning("not syncing comment on case %s: No content item labeled for comments", case_uuid)
        else:
            for comment_tree_branch in CommentSync.get_comments_by_content_uuid(
                    content_uuid=comment_content_item.content_uuid,
                    session=session):
                for tlc in comment_tree_branch.keys():
                    yield CommentV2.sync_case_comments(firebase_db=firebase_db,
                                                       action=action,
                                                       case_uuid=str(case_uuid),
                                                       content_uuid=comment_content_item.content_uuid,
                                                       comment_struct=comment_tree_branch[tlc])

    @staticmethod
    def sync_case_comments(firebase_db, action, case_uuid, content_uuid, comment_struct):
        path = firebase_db.collection(CaseDetailV2.firebase_collection) \
            .document(case_uuid) \
            .collection(str(content_uuid)) \
            .document(comment_struct['commentUuid']) \
            .path
        sync_object = CaseDetailV2(path=path)
        if action is FirebaseAction.SET:
            return sync_object.set_comment_data(comment_data=comment_struct)
        if action is FirebaseAction.DELETE:
            return sync_object.delete()


class CaseUserActions(CaseDetailV2):
    def __init__(self, path):
        super().__init__(path=path)

    @staticmethod
    def sync_user_data(firebase_db, action, case_uuid, user_uuid, user_case_data):
        path = firebase_db.collection(CaseDetailV2.firebase_collection) \
            .document(case_uuid) \
            .collection('userActions') \
            .document(user_uuid) \
            .path
        sync_object = CaseDetailV2(path=path)
        if action is FirebaseAction.SET:
            return sync_object.set_user_case_data(user_case_data=user_case_data)


class CasePublications(CaseDetailV2):

    def __init__(self, path):
        super().__init__(path=path)

    @staticmethod
    def sync(firebase_db, case_uuid, action, columns=None, session=None, **kwargs):
        if session is None:
            raise StopIteration

        to_sync = session.query(CasePublicationsDB).filter(CasePublicationsDB.case_uuid == case_uuid)

        if to_sync.count() < 1:
            logger.error("Nothing to sync")
            return StopIteration

        collection = firebase_db.collection(CaseDetailV2.firebase_collection) \
            .document(case_uuid) \
            .collection('casePublications')

        existing_publications_set = set(list(CasePublications.check_existing(collection)))
        publication_id_set = set([str(x.pub_med_id) for x in to_sync.all()])
        logger.error("Existing publications %s, to publish %s", existing_publications_set, publication_id_set)
        if existing_publications_set.difference(publication_id_set):
            logger.error("Removing existing publications")
            for doc in list(existing_publications_set):
                yield CasePublications._sync_case_publication(firebase_db=firebase_db,
                                                              action=FirebaseAction.DELETE,
                                                              case_uuid=case_uuid,
                                                              publication=None,
                                                              document_id=doc)

        for publication in to_sync.all():
            yield CasePublications._sync_case_publication(firebase_db=firebase_db,
                                                          action=action,
                                                          case_uuid=case_uuid,
                                                          publication=publication,
                                                          document_id=publication.pub_med_id)

    @staticmethod
    def _sync_case_publication(firebase_db, action, case_uuid, publication, document_id):
        path = firebase_db.collection(CaseDetailV2.firebase_collection) \
            .document(case_uuid) \
            .collection('casePublications') \
            .document(document_id) \
            .path
        sync_object = CaseDetailV2(path=path)
        if action is FirebaseAction.SET:
            return sync_object.set_publication_data(publication_data=publication)
        if action is FirebaseAction.DELETE:
            return sync_object.delete()

    @staticmethod
    def check_existing(fs_collection):
        for doc in fs_collection.list_documents():
            yield doc.id
