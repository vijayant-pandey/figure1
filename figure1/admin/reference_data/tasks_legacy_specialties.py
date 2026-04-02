import logging
from figure1.admin.reference_data.prequel_model import ReferenceDataPrequelModel
from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.db import LegacySpecialtyType, LegacySpecialty, LegacySpecialtyProfession


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_legacy_specialties')
def initialize_legacy_specialties(self):
    logger = logging.getLogger(__name__)
    logger.info("Saving legacy specialties to postgres...")
    _save_legacy_specialties(session=self.session)
    logger.info("Done updating legacy specialties")


def _save_legacy_specialties(session):
    logger = logging.getLogger(__name__)
    for specialty in ReferenceDataPrequelModel().get_specialties():
        specialty_type = LegacySpecialtyType.create_if_missing(name=specialty.get('type_name'), session=session)
        specialty_profession = LegacySpecialtyProfession.create_if_missing(name=specialty.get('profession'),
                                                                           session=session)
        LegacySpecialty.create_if_missing(
            type_uuid=specialty_type.type_uuid,
            profession_uuid=specialty_profession.profession_uuid,
            label=specialty.get('label'),
            singular_label=specialty.get('singular_label'),
            plural_label=specialty.get('plural_label'),
            indefinite_article=specialty.get('indefinite_article'),
            skip_commit=True,
            session=session)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f'Failed to update specialties: {e}')
