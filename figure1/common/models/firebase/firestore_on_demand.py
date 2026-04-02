from google.cloud.firestore import DELETE_FIELD
from figure1.core import FirebaseClient


class FirebaseCollectionManager(FirebaseClient):

    def __init__(self):
        """
        The arguments here are handled with the same logic the SDK uses, the number of arguments for documents and for
        collection must be equal. They are then used _in order_ to generate the path.

        For example if the following is passed in:
        collections=['usersVotesDB', 'contentUuid'], documents=['userUid', 'questionOption']
        the path generated would be:
        firebase_db.collection('userVotesDB').document(userUid).collection(contentUuid).document('questionOption').path

        :param documents:
        :param collections:
        :param fs_client: A configured firestore client object
        """
        super().__init__()
        self.fs = None
        self.collections = []
        self.documents = []

    def set_fs_client(self, documents: list, collections: list):
        if len(documents) != len(collections):
            raise ValueError("Documents and Collections lists must be the same length")
        self.collections = collections
        self.documents = documents
        fs = self.fs_client
        for doc, coll in zip(documents, collections):
            fs = fs.collection(coll).document(doc)
        self.fs = fs

    def set(self, firestore_document, merge=True):
        """
        Execute the firestore update

        :param firestore_document:
        :param merge: Boolean - merge=False replaces the document, merge=True attempts to update the document
        :return:
        """
        self.fs.set(firestore_document, merge=merge)

    def get(self):
        """
        Get a firestore document, use to_dict() to make it usable.
        :return: DocumentSnapshot
        """
        return self.fs.get()

    def delete(self, field_name):
        """
        This only works on toplevel keys for a map. Pass in the name of the key to delete. The document must exist.

        :param field_name:
        :return:
        """
        self.fs.update({field_name: DELETE_FIELD})

    def delete_document(self):
        """
        Delete a document in firestore
        :return:
        """
        self.fs.delete()

    @staticmethod
    def sync(*args, **kwargs):
        """
        This class is not compatible with the task-based way of running firestore updates, so we return an empty array

        :param args:
        :param kwargs:
        :return: []
        """
        return []
