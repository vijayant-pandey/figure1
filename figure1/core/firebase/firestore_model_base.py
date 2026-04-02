import abc
from google.cloud.firestore_v1 import DocumentReference, DocumentSnapshot, WriteBatch
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from .firebase_client import FirebaseClient


class FirestoreSyncBase(BaseModel):
    """
    This model is used to manage objects which can sync their state to a firestore document

    Required overrides are:

    """
    _fs_client_cache = None
    _firestore_document_reference: Optional[DocumentReference] = None

    class Config:
        underscore_attrs_are_private = True

    @property
    def fs_client(self):
        if self._fs_client_cache is None:
            self._fs_client_cache = FirebaseClient()
        return self._fs_client_cache.fs_client

    @abc.abstractmethod
    def generate_firestore_document(self, session=None) -> dict:
        """
        Return a document to write to firestore. Should be implemented by inheriting class.
        :return:
        """
        return {}

    def generate_firestore_update_document(self, session=None) -> dict:
        """
        Return a document to update to firestore.
        :return:
        """
        return {}

    @property
    def firestore_doc_reference(self) -> DocumentReference:
        """
        Returns the firestore document reference
        :return:
        """
        return self._firestore_document_reference

    @firestore_doc_reference.setter
    def firestore_doc_reference(self, value):
        self._firestore_document_reference = value

    def firestore_write(self, session=None, merge=True):
        """
        Execute a write to firestore

        :param merge: merge=true tries to merge the document with and existing document in firestore, merge=false
            replaces the document
        :type merge: bool

        :param session: Database session, it is passed to generate_firestore_document()
        :type session: Session

        :return:
        """
        from figure1.configuration import app_settings
        import logging
        
        if app_settings.read_only_dev_mode:
            logger = logging.getLogger('figure1.read_only_mode')
            logger.warning(f"READ-ONLY MODE: Blocked firestore_write() operation on {self.__class__.__name__}")
            return
            
        if not isinstance(self.firestore_doc_reference, DocumentReference):
            raise ValueError("Document reference has not been correctly configured")
        self.firestore_doc_reference.set(self.generate_firestore_document(session), merge=merge)

    def firestore_batch_write(self, batch, session=None, merge=True):
        """
        Execute a batch write to firestore

        :param batch: the firestore batch client
        :type batch: WriteBatch

        :param merge: merge=true tries to merge the document with and existing document in firestore, merge=false
            replaces the document
        :type merge: bool

        :param session: Database session, it is passed to generate_firestore_document()
        :type session: Session

        :return:
        """
        from figure1.configuration import app_settings
        import logging

        if app_settings.read_only_dev_mode:
            logger = logging.getLogger('figure1.read_only_mode')
            logger.warning(f"READ-ONLY MODE: Blocked firestore_batch_write() operation on {self.__class__.__name__}")
            return

        if not isinstance(self.firestore_doc_reference, DocumentReference):
            raise ValueError("Document reference has not been correctly configured")

        batch.set(self.firestore_doc_reference,
                  self.generate_firestore_document(session),
                  merge=merge)

    def firestore_get(self) -> DocumentSnapshot:
        """
        Execute a get on the firestore document

        :return:
        """
        if not isinstance(self.firestore_doc_reference, DocumentReference):
            raise ValueError("Document reference has not been correctly configured")
        return self.firestore_doc_reference.get()

    def firestore_update(self, session):
        """
        Execute a update to firestore. If the self.firestore_doc_reference does not exist, it would
        execute self.firestore_write(session=session) to create a new document.

        :param session: Database session
        :return:
        """
        from figure1.configuration import app_settings
        import logging
        
        if app_settings.read_only_dev_mode:
            logger = logging.getLogger('figure1.read_only_mode')
            logger.warning(f"READ-ONLY MODE: Blocked firestore_update() operation on {self.__class__.__name__}")
            return
            
        if not isinstance(self.firestore_doc_reference, DocumentReference):
            raise ValueError("Document reference has not been correctly configured")
        if not self.firestore_doc_reference.get().exists:
            self.firestore_write(session=session)
        else:
            self.firestore_doc_reference.update(self.generate_firestore_update_document(session=session))

    def firestore_reset(self, **kwargs):
        """
        Reset the document at the configured path, this means different things in different contexts, so it must
        be created by the subclass.
        :return: None
        """
        pass
