from figure1 import celery_app
from figure1.common.models.firebase import CaseDetailV2
from figure1.common.types.versions import Version
from figure1.core import FirestoreSyncBase, TaskBase


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.backend.sync_firestore_data_versions_task')
def sync_firestore_data_versions_task(self):
    sync_firestore_data_versions()


def sync_firestore_data_versions():
    FirestoreDataVersions(casesDBv2=CaseDetailV2.version).firestore_write()


class FirestoreDataVersions(FirestoreSyncBase):
    """
    Handles syncing firestore data versions to firestore
    """
    casesDBv2: Version

    @property
    def firestore_doc_reference(self):
        return self.fs_client\
            .collection('configurationDB')\
            .document('versions')

    def generate_firestore_document(self, session=None):
        return self.dict()

    def firestore_reset(self):
        self.firestore_doc_reference.delete()
