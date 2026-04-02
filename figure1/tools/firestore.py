import logging
from firebase_admin import auth

from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.firebase.utils import delete_collection_batch

logger = logging.getLogger('figure1.tools.firestore')


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.delete_firestore_collection')
def delete_firestore_collection(self: FirebaseTaskBase, collection_name: str):
    path = self.fs_client.collection(collection_name)

    logger.info(f"Deleting collection: {collection_name}")
    delete_collection_batch(collection_path=path, batch=self.batch)
    logger.info(f"Finished deleting collection: {collection_name}")


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.delete_auth_users')
def delete_auth_users(self: FirebaseTaskBase, dry_run: bool = True):
    fb_app = self.fs_app

    uids = []
    page = auth.list_users(max_results=1000, app=fb_app)
    while page:
        uids.extend([u.uid for u in page.users])
        page = page.get_next_page()

    if not dry_run:
        delete_size = 500
        page_count = len(uids) // delete_size + 1
        pages = [uids[i * delete_size:(i + 1) * delete_size] for i in range(0, page_count)]
        for page in pages:
            auth.delete_users(uids=page, app=fb_app)

    logging.info(f"Firebase deletions completed (dry_run={dry_run}).  Total users: {len(uids)}")
    return {"deleted": len(uids)}
