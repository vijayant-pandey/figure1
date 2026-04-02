import logging

from mementos import mementos
from figure1.core.firebase import firestore_client, configure_environment, firebase_app


class FirebaseClient(mementos):
    _fs_app = None
    _fs_client = None

    def __init__(self):
        """
        This class inherits from mementos in order to cache instances. This saves from having to configure firestore
        on every call.
        """
        print("Configure Environment")
        # print(configure_environment())
        try:
            configure_environment()
        except Exception as e:
            logging.error(f"Failed to configure firestore environment: %s", e)
        self.base_firebase_class_path = 'figure1.common.models.firebase'

    @property
    def fs_app(self):
        if self._fs_app is None:
            self._fs_app = firebase_app()
        return self._fs_app

    @property
    def fs_client(self):
        if self._fs_client is None:
            self._fs_client = firestore_client()
        return self._fs_client

    def get_class(self, kls):
        parts = kls.split('.')
        module = ".".join(parts[:-1])
        m = __import__(module)
        for comp in parts[1:]:
            m = getattr(m, comp)
        return m

    def load_class(self, firebasemodel):
        try:
            return self.get_class(self.base_firebase_class_path + '.' + firebasemodel)
        except AttributeError as ae:
            return {'error': f"Failed to load {firebasemodel} from {self.base_firebase_class_path}"}
        except ModuleNotFoundError as notfound:
            return {'error': f"Failed to load {firebasemodel} from {self.base_firebase_class_path}"}
