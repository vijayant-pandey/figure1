import logging

from firebase_admin import auth
from google.cloud.firestore_v1 import CollectionReference, DocumentReference

from firebase_admin.auth import UserNotFoundError, \
    EmailAlreadyExistsError, \
    UidAlreadyExistsError

from figure1.core import firebase_app
from figure1.exceptions import FirebaseError

logger = logging.getLogger('figure1.firebase.utils')
batch_count = 0


def delete_deep_collection(top_level_client, batch_client, starting_batch_count=0):
    """
    To use this, pass in a client that is initialized to the top level of the collection you want to delete.
    For example, you could pass is something like this:
    tl = fs_client.collection('referenceData').document('schools_by_profession2')
    delete_deep_collection(tl)

    This function will descend to the bottom and delete everything on its way up, exclusive of the path passed in. In
    the example above, everything up to 'schools_by_profession2', but not including it would be deleted.
    """

    global batch_count

    def add_to_batch(document_reference, batch):
        global batch_count
        logger.debug("Batch count is %s", batch_count)
        if batch_count > 0 and not batch_count % 500:
            logger.info("Committed %s documents", batch_count)
            batch.commit()
        batch.delete(document_reference)
        batch_count += 1

    def recurse(doc, batch):
        """
        Given a document, attempts to descend to all sub-collections and delete all documents on the way up.
        :param doc: Can be a document reference or a collection reference.
        :param batch: This is a firestore batch client
        :param previous_batch_count: This is how many documents are ready to be commited, must commit every 500.
        :return:
        """

        if isinstance(doc, CollectionReference):
            for sub_col_doc in doc.list_documents():
                recurse(doc=sub_col_doc, batch=batch)
        elif isinstance(doc, DocumentReference):
            for sub_col in doc.collections():
                logger.debug("Descending to collection %s from document %s", sub_col.id, doc.path)
                for sub_col_doc in sub_col.list_documents(page_size=1000):
                    recurse(doc=sub_col_doc, batch=batch)
            add_to_batch(doc, batch=batch)
        else:
            logger.error("doc is unknown type %s", doc)

    if isinstance(top_level_client, DocumentReference):
        logger.info("Recursively deleting document %s", top_level_client.path)
        batch_client.commit()
        recurse(doc=top_level_client, batch=batch_client)
        logger.info("Deleted %s from document %s", batch_count, top_level_client.path)
        batch_client.commit()
        return batch_count

    elif isinstance(top_level_client, CollectionReference):
        docs_deleted = 0
        logger.info("Recursively deleting all documents in collection %s", top_level_client.id)
        for doc_ in top_level_client.list_documents(page_size=1000):
            recurse(doc_, batch=batch_client)
            logger.debug("Deleted %s records from document %s and all sub-collections", batch_count, doc_.path)
        batch_client.commit()
        return docs_deleted

    else:
        logger.error("Unrecognized reference passed, expected CollectionReference or DocumentReference")
        return 0


def delete_collection_batch(collection_path, batch, starting_batch_count=0) -> int:
    """
    Recursively deletes all documents in a firestore collection. The delete operations are batched. The collection
    path can be either a document path or a collection path.

    To handle firestore's limit of 500 operations in a single batch, this method requires passing in the number of
    operations already in the batch, and returns the number of operations after the deletes have been added.

    This will descend
    Intermediate batch commits are done as needed.
    """
    return delete_deep_collection(top_level_client=collection_path,
                                  batch_client=batch,
                                  starting_batch_count=starting_batch_count)


def get_firebase_user(email, fb_app):
    """
    Finds a firebase user and returns their uid.  If a user does not exist, returns None
    :param email:
    :param fb_app:
    """
    try:
        data = auth.get_user_by_email(email=email, app=fb_app)
    except UserNotFoundError:
        return None
    if not data.uid:
        raise FirebaseError(msg=f"Firebase API did not return a uid for user {email}", return_code=500)
    return data.uid


def create_firebase_user(email, uid=None, fb_app=None):
    """
    Create an authentication record for a user in firebase.  If uid is provided this uid will be used, otherwise
    a random uid will be generated.
    :param email:
    :param uid:
    :param fb_app:
    :return: The uid of the firebase user
    """
    if not fb_app:
        fb_app = firebase_app()

    auth_user = None
    if uid:
        auth_user = check_firebase_uid(uid=uid, email=email, fb_app=fb_app)
    if not auth_user:
        try:
            auth_user = auth.create_user(email=email, uid=uid, app=fb_app)
        except EmailAlreadyExistsError:
            logger.info("Firebase user already exists, skipping create %s", email)
            auth_user = auth.get_user_by_email(email=email, app=fb_app)

    if not auth_user.uid:
        raise FirebaseError(msg=f"Firebase API did not return a uid for user {email}", return_code=500)
    return auth_user.uid


def check_firebase_uid(uid, email, fb_app):
    """
    Checks for authentication records associated with a user_uid.  If an anonymous auth record already exists it will
    be linked to the given email.  If a record exists but is associated with a different email an error is raised.
    """
    try:
        auth_user = auth.get_user(uid=uid, app=fb_app)
    except UserNotFoundError:
        return
    if not auth_user:
        return

    if auth_user.email is None:
        logger.info("Uid %s is associated with an anonymous user, updating to email %s", email)
        auth_user = auth.update_user(uid=uid, email=email, app=fb_app)
        return auth_user
    if auth_user.email != email:
        logger.error("Firebase auth for uid %s already exists for email %s", uid, email)
        raise FirebaseError(msg=f"Firebase auth for uid is associated with a different email", return_code=500)
