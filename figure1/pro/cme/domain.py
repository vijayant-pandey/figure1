from typing import Dict

from sqlalchemy.orm import Session

from figure1.common.firebase import do_firebase_sync
from figure1.core import managed_session
from figure1.common.models.db import User


@managed_session
def get_cme_activities(user_uid, session: Session) -> Dict:
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    do_firebase_sync.delay(firebasemodel='FirebaseUserCmeDB', uuid=user.user_uuid)

    return {'success': 'Task to sync cme activities started'}
