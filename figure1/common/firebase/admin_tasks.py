import logging
from firebase_admin import auth as fb_auth
from firebase_admin.exceptions import FirebaseError

from figure1.core import firebase_app, TaskBase, FirebaseClient, celery_app

fs = FirebaseClient()


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(FirebaseError,),
                 retry_backoff=True,
                 max_retries=4,
                 name='figure1.frontend.change_firebase_email')
def change_firebase_email(self, user_uid, email):
    fb_app = firebase_app()
    logging.info("Updating email for user %s in firebase", user_uid)
    fb_auth.update_user(uid=user_uid, email=email, app=fb_app)
