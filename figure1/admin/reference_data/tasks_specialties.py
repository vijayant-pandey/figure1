import logging

from figure1.common.types import ProfessionCategoryDisplayOrder
from google.api_core.exceptions import ServiceUnavailable
from figure1.core import FirebaseTaskBase, celery_app
from figure1.admin.reference_data.model_methods import get_tagging_specialties
from figure1.admin.reference_data.model_methods import get_registration_specialties
from figure1.admin.reference_data.model_methods import get_registration_professions
from figure1.admin.reference_data.model_methods import get_interests_specialties

logger = logging.getLogger('figure1.reference_data.specialties')


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_specialties')
def initialize_specialties(self, clean=None):
    logger.info("Syncing specialties, professions, and interests to firestore...")
    _sync_specialties(fs_client=self.fs_client, session=self.session, )
    _sync_interests(fs_client=self.fs_client, session=self.session)
    _sync_professions(fs_client=self.fs_client, session=self.session)
    logger.info("Done updating specialties, professions, and interests")


def _sync_specialties(fs_client, session):
    specialties = fs_client.collection('referenceData').document('specialties')
    tagging_specialties = {}
    logger.info("Syncing specialties")
    for tagging_specialty in get_tagging_specialties(session=session):
        logger.debug("Adding specialty %s", tagging_specialty.dict())
        tagging_specialties.update({
            tagging_specialty.specialtyUuid: {
                'uuid': tagging_specialty.specialtyUuid,
                'name': tagging_specialty.specialtyName,
                'depth': 1
            }
        })
    specialties.set({'tagging': tagging_specialties}, merge=False)
    logger.info("Specialties synced")


def _sync_interests(fs_client, session):
    interests = fs_client.collection('referenceData').document('interests')
    interests_specialties = {}
    for i in get_interests_specialties(session=session):
        interests_specialties.update({
            i.get('specialtyUuid'):
                {
                    'interestUuid': i.get('specialtyUuid'),
                    'interestName': i.get('specialtyName')
                }
        })
    interests.set(interests_specialties, merge=False)


def _sync_professions(fs_client, session):
    logger = logging.getLogger(__name__)
    batch = fs_client.batch()

    for profession in get_registration_professions(session=session):
        category_name_ns = profession.professionCategoryLabel
        display_order = ProfessionCategoryDisplayOrder.otherhcp.value
        if category_name_ns in ProfessionCategoryDisplayOrder.__members__:
            display_order = ProfessionCategoryDisplayOrder[category_name_ns].value
        profession_fs = fs_client.collection('referenceData').document('professions')
        try:
            profession_fs.set(
                {profession.professionUuid: {**profession.dict(),
                                             'displayOrder': display_order}},
                merge=True)

        except ServiceUnavailable:
            logger.error("Raised service unavailable")
        count = 0
        for specialty in get_registration_specialties(session=session,
                                                      profession_uuid=profession.professionUuid):
            if specialty.specialty:
                specialty_fs = fs_client.collection('referenceData') \
                    .document('professions') \
                    .collection(profession.professionUuid) \
                    .document(specialty.treeUuid)
                batch.set(specialty_fs, specialty.dict(), merge=True)
                count += 1
                if not count % 500:
                    batch.commit()
            else:
                profession_fs = fs_client.collection('referenceData') \
                    .document('professions') \
                    .collection(profession.professionUuid) \
                    .document(specialty.treeUuid)
                batch.set(profession_fs, {**specialty.dict(), 'displayOrder': display_order}, merge=True)
                count += 1
                if not count % 500:
                    batch.commit()
        batch.commit()
