from figure1.common.firebase import delete_collection_batch
from figure1.common.models.db import Groups
from figure1.common.models.firebase.groups_db import FirestoreGroups, FirestoreGroupMember, FirestoreReferenceGroups
from figure1.common.types import GroupModel
from figure1.core import celery_app, FirebaseTaskBase


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.sync_groups')
def sync_groups(self, clean=None):
    batch = self.fs_client.batch()

    group_db_collection_path = self.fs_client.collection('groupsDB')
    delete_collection_batch(collection_path=group_db_collection_path, batch=batch)

    firebase_write_count = 0
    for group in Groups.get_all_groups(session=self.session):
        # sync to referenceData
        FirestoreReferenceGroups(group_uuid=group.group_uuid).firestore_batch_write(batch,
                                                                                    session=self.session,
                                                                                    merge=True)
        firebase_write_count += 1
        if firebase_write_count % 500 == 0:
            batch.commit()

        # sync to groupsDB
        FirestoreGroups(group_uuid=group.group_uuid).firestore_batch_write(batch, session=self.session)
        firebase_write_count += 1
        if firebase_write_count % 500 == 0:
            batch.commit()

        for each_member in group.members:
            FirestoreGroupMember(group_uuid=group.group_uuid, user_uuid=each_member.user_uuid)\
                .firestore_batch_write(batch, session=self.session)

            firebase_write_count += 1
            if firebase_write_count % 500 == 0:
                batch.commit()
    batch.commit()
