import logging

from sqlalchemy import text

from figure1.core import managed_session, translate_client
from figure1.common.helpers import CaseManagement
from figure1.common.models.db import Case, Label

from figure1.common.types import Locale

translate = translate_client()
logger = logging.getLogger(__name__)


@managed_session
def detect_case_language(case_uuid, session):
    if not translate:
        return None

    language = None
    case = session.query(Case).filter(Case.case_uuid == case_uuid).one()
    for content in case.content:
        if content.caption:
            detected_caption_lang = translate.detect_language(values=content.caption)
            if detected_caption_lang.get("confidence") > 0.95:
                lang = detected_caption_lang.get("language")
                for loc in Locale.__members__:
                    if Locale[loc].language_code == lang.upper():
                        language = Locale[loc]
            else:
                logger.info("Confidence is %s for language %s in caption",
                            detected_caption_lang.get("confidence"),
                            detected_caption_lang.get("language"))
        if content.title:
            detected_title_lang = translate.detect_language(values=content.title)
            if detected_title_lang.get("confidence") > 0.95:
                lang = detected_title_lang.get("language")
                for loc in Locale.__members__:
                    if Locale[loc].language_code == lang.upper():
                        if language:
                            if language.language_code != Locale[loc].language_code:
                                logger.error("Detected different languages on the same case")
                        else:
                            language = Locale[loc]
            else:
                logger.info("Confidence is %s for language %s in title",
                            detected_title_lang.get("confidence"),
                            detected_title_lang.get("language"))
        if language:
            logger.info("Detected language %s for content id %s in case %s",
                        language.code,
                        content.content_uuid,
                        case_uuid)

        else:
            logger.info("No language detected for content id %s in case %s", content.content_uuid, case_uuid)

    if language:
        case.language = language.code
        session.add(case)
        return language
    else:
        return "No language detected"


@managed_session
def translate_case_content(case_uuid, target_language=None, session=None):
    """
    This assumes you are translating to target_language
    :param case_uuid:
    :param session:
    :param target_language:
    :return:
    """
    source_lang = detect_case_language(case_uuid=case_uuid, session=session)
    if not isinstance(source_lang, Locale):
        return None
    CaseManagement.translate_case(case_uuid=case_uuid, session=session,
                                  source_language=source_lang.code, target_language=target_language)


@managed_session
def update_all_case_cme_labels(session=None):
    """
    This will update all case cme labels for all cases.
    :param session:
    :return:
    """
    case_cme_label = session.query(Label).filter(Label.kind == 'case_cme').one_or_none()
    if not case_cme_label:
        return {'error': 'The case CME label does not exist.'}
    session.execute(text("insert into c_case_label (created_at, updated_at, case_uuid, label_uuid) "
                         "select CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, case_uuid, label_uuid from c_case, r_label "
                         "where state='APPROVED' and group_uuid is NULL and kind='case_cme' "
                         "ON CONFLICT (case_uuid, label_uuid) DO NOTHING"))

    return {'success': "Updated all case cme labels for all cases."}
