from figure1.admin.reference_data.model_methods import get_all_verification_tags
from figure1.core import FirebaseTaskBase, celery_app


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.service.sync_verification_tags')
def sync_verification_tags(self, clean=None):
    doc = self.fs_client.collection('referenceData').document('verificationTags')
    doc_old = self.fs_client.collection('b_referenceData').document('verificationTags')

    firestore_data = {}
    for t in get_all_verification_tags(session=self.session):
        uuid = str(t.tag_uuid)
        firestore_data[uuid] = t.as_dict()

    doc.set({'all': firestore_data})
    doc_old.set({'all': firestore_data})
