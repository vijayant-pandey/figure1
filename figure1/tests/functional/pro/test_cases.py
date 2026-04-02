import string
import uuid
from random import choice
from unittest.mock import patch, MagicMock

from figure1.common.elasticsearch import add_or_update_case
from figure1.common.models.db.c_content_update_model import ContentUpdateTranslations
from figure1.common.types import Locale
from figure1.pro.cases.domain import get_case, submit_case_reaction
from figure1.common.models.db import Case, CaseReaction, CaseReport, UserSavedCase, Label, CaseProgress, \
    AnonymousUser, ContentTranslation
from figure1.common.helpers import UserManagement, GroupManagement, CaseManagement, CaseDetail
from figure1.common.types.case import CaseState
from figure1.tests.utils.case import create_test_case
from figure1.configuration import app_settings, es_settings


def _get_user_activity_doc(case_uuid, user_uuid, fs):
    doc = fs.collection('casesDBv2') \
        .document(case_uuid) \
        .collection('userActions') \
        .document(user_uuid).get()
    return doc.to_dict()


def _get_user_profile_activity_doc(case_uuid, user_uuid, fs):
    doc = fs.collection('usersProfileDB') \
        .document(user_uuid) \
        .collection('activity') \
        .document(case_uuid).get()
    return doc.to_dict()


def _random_string(length):
    letters = string.ascii_letters
    return ''.join(choice(letters) for _ in range(length))


def _create_user(session):
    user = _random_string(16)
    mgmt = UserManagement(user_uid=f'test_{user}', session=session, is_new_user=True)
    mgmt.add_user(first_name=f'test_{user}_first_name',
                  last_name=f'test_{user}_last_name',
                  email=f'test_{user}@figure1.com',
                  user_uuid=None,
                  legacy=False)
    return mgmt.user


def _create_case(author_uuid, session, is_anonymous=False):
    case, _ = create_test_case(
        author_uuid=author_uuid,
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        is_anonymous=is_anonymous,
        session=session)
    # Add case to elasticsearch
    session.commit()
    add_or_update_case(case_uuid=str(case.case_uuid), session=session)
    # Add case to firestore
    t = get_case(case_uuid=case.case_uuid, return_task=True).pop('task')
    t.apply(timeout=10)
    return case


def _create_label(name, session):
    return Label.create_or_update(name=name,
                                  kind=name.lower(),
                                  is_public=True,
                                  session=session)


def test_case_resync_timeout(load_db, get_elasticsearch_client):
    """
    Ensure that multiple sync calls do not continuously update firestore
    """
    session = load_db
    app_settings.case_sync_throttle_enabled = True
    user = _create_user(session=session)
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid
    c = Case.get_case(case_uuid=case_uuid)
    last_synced = c.synced_at
    t = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    t.apply(timeout=10)
    c2 = Case.get_case(case_uuid=case_uuid)
    assert c2.synced_at == last_synced


def test_case_resync_timeout_throttle_disabled(load_db, get_elasticsearch_client):
    """
    Ensure that disabling the case sync throttle results in two updates.
    """
    session = load_db
    app_settings.case_sync_throttle_enabled = False
    user = _create_user(session=session)
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid
    c = Case.get_case(case_uuid=case_uuid)
    last_synced = c.synced_at
    t = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    t.apply(timeout=10)
    c2 = Case.get_case(case_uuid=case_uuid)
    assert c2.synced_at > last_synced


def test_case_save(client, headers, load_db, get_firestore_client, test_group_case):
    session = load_db
    group_case, _ = test_group_case
    user = _create_user(session=session)
    user_uid = user.user_uid
    fs = get_firestore_client
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid

    # Missing user returns 404
    response = client.post(f'/pro/v1/case/{case_uuid}/action', headers=headers, json={
        'user_uid': "fake_user",
        'action': 'save'
    })
    assert response.status_code == 404

    # Missing case returns 404
    response = client.post(f'/pro/v1/case/00000000-0000-0000-0000-000000000000/action', headers=headers, json={
        'user_uid': user_uid,
        'action': 'save'
    })
    assert response.status_code == 404

    # Save case creates entry in db
    response = client.post(f'/pro/v1/case/{case_uuid}/action?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'action': 'save'
    })
    assert response.status_code == 200
    assert UserSavedCase.get_is_saved(case_uuid=case_uuid, user_uuid=user.user_uuid, session=session)
    userActivity = _get_user_activity_doc(case_uuid=str(case_uuid), user_uuid=str(user.user_uuid), fs=fs)
    assert userActivity['saved'] is True

    # Unsave marks entry as deleted
    response = client.post(f'/pro/v1/case/{case_uuid}/action?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'action': 'unsave'
    })
    assert response.status_code == 200
    assert not UserSavedCase.get_is_saved(case_uuid=case_uuid, user_uuid=user.user_uuid, session=session)
    userActivity = _get_user_activity_doc(case_uuid=str(case_uuid), user_uuid=str(user.user_uuid), fs=fs)
    assert 'saved' not in userActivity

    # Save updates db again
    response = client.post(f'/pro/v1/case/{case_uuid}/action?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'action': 'save'
    })
    assert response.status_code == 200
    assert UserSavedCase.get_is_saved(case_uuid=case_uuid, user_uuid=user.user_uuid, session=session)

    # group case tests
    group_case_uuid, group_uuid = group_case.case_uuid, group_case.group_uuid

    # a user can not save a group case without sufficient permissions.
    assert group_uuid is not None
    response = client.post(f'/pro/v1/case/{group_case_uuid}/action?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'action': 'save'
    })
    assert response.status_code == 403
    assert not UserSavedCase.get_is_saved(case_uuid=group_case_uuid, user_uuid=user.user_uuid, session=session)
    userActivity = _get_user_activity_doc(case_uuid=str(group_case_uuid), user_uuid=str(user.user_uuid), fs=fs)
    assert userActivity is None

    # a user can save a group case with sufficient permissions.
    assert group_uuid is not None
    GroupManagement.add_user_to_group(user_uuid=user.user_uuid, group_uuid=group_uuid, session=session)
    session.commit()

    response = client.post(f'/pro/v1/case/{group_case_uuid}/action?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'action': 'save'
    })

    assert response.status_code == 200
    assert UserSavedCase.get_is_saved(case_uuid=group_case_uuid, user_uuid=user.user_uuid, session=session)
    userActivity = _get_user_activity_doc(case_uuid=str(group_case_uuid), user_uuid=str(user.user_uuid), fs=fs)
    assert userActivity['saved'] is True

    GroupManagement.remove_user_from_group(user_uuid=user.user_uuid, group_uuid=group_uuid, session=session)
    session.commit()


def test_case_report(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    user_uid = user.user_uid
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid

    # Missing user returns 404
    response = client.post(f'/pro/v1/case/{case_uuid}/action?force_synchronous=true', headers=headers, json={
        'user_uid': "fake_user",
        'action': 'report',
        'value': 'report text sample'
    })
    assert response.status_code == 404

    # Missing case returns 404
    response = client.post(f'/pro/v1/case/00000000-0000-0000-0000-000000000000/action', headers=headers, json={
        'user_uid': user_uid,
        'action': 'report',
        'value': 'report text sample'
    })
    assert response.status_code == 404

    # Report case creates entry in db
    response = client.post(f'/pro/v1/case/{case_uuid}/action?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'action': 'report',
        'value': 'report text sample'
    })
    assert response.status_code == 200
    report = session.query(CaseReport) \
        .filter(CaseReport.case_uuid == case_uuid, CaseReport.user_uuid == user.user_uuid) \
        .one().as_dict()
    assert report.get('text') == 'report text sample'


def test_case_reaction(client, headers, load_db, get_firestore_client, get_elasticsearch_client, test_group_case):
    session = load_db
    group_case, _ = test_group_case
    user = _create_user(session=session)
    user_uid = user.user_uid
    fs = get_firestore_client
    es = get_elasticsearch_client
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid

    # Invalid reaction returns 400
    response = client.post(f'/pro/v1/case/{case_uuid}/reaction?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'reaction': 'invalid_reaction',
        'value': True
    })
    assert response.status_code == 400
    # Missing user returns 404
    response = client.post(f'/pro/v1/case/{case_uuid}/reaction?force_synchronous=true', headers=headers, json={
        'user_uid': "fake_user",
        'reaction': 'agree',
        'value': True
    })
    assert response.status_code == 404

    # Missing case returns 404
    response = client.post(f'/pro/v1/case/00000000-0000-0000-0000-000000000000/reaction?force_synchronous=true',
                           headers=headers,
                           json={
                               'user_uid': user_uid,
                               'reaction': 'agree',
                               'value': 'true'
                           })
    assert response.status_code == 404

    # Valid post creates reaction
    response = client.post(f'/pro/v1/case/{case_uuid}/reaction?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'reaction': 'agree',
        'value': True
    })
    assert response.status_code == 200
    reaction = session.query(CaseReaction) \
        .filter(CaseReaction.case_uuid == case_uuid, CaseReaction.user_uuid == user.user_uuid) \
        .one().as_dict()

    assert reaction.get('caseReaction') is 'AGREE'
    userActivity = _get_user_activity_doc(case_uuid=str(case_uuid), user_uuid=str(user.user_uuid), fs=fs)
    assert 'agree' in userActivity['reactions']

    profileActivity = _get_user_profile_activity_doc(case_uuid=str(case_uuid), user_uuid=str(user.user_uuid), fs=fs)
    assert profileActivity.get('allReactions').get('agree') == 1

    b = es.get(index=es_settings.cases_alias, id=str(case_uuid))
    assert b.get('_source').get('allReactions').get('agree') == 1

    assert str(user.user_uuid) in b.get('_source').get('reactions').get('agree')

    # Setting reaction value to  false modifies current record
    response = client.post(f'/pro/v1/case/{case_uuid}/reaction?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'reaction': 'agree',
        'value': False
    })

    assert response.status_code == 200
    reaction = session.query(CaseReaction) \
        .filter(CaseReaction.case_uuid == case_uuid, CaseReaction.user_uuid == user.user_uuid) \
        .one_or_none()
    assert reaction is None

    d = es.get(index=es_settings.cases_alias, id=str(case_uuid))
    assert str(user.user_uuid) not in d.get('_source').get('reactions').get('agree')

    # group case tests
    group_case_uuid, group_uuid = group_case.case_uuid, group_case.group_uuid

    # a user can not react to a group case without sufficient permissions.
    assert group_uuid is not None
    response = client.post(f'/pro/v1/case/{group_case_uuid}/reaction?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'reaction': 'agree',
        'value': True
    })
    assert response.status_code == 403

    # a user can react to a group case with sufficient permissions.
    assert group_uuid is not None
    GroupManagement.add_user_to_group(user_uuid=user.user_uuid, group_uuid=group_uuid, session=session)
    session.commit()

    response = client.post(f'/pro/v1/case/{group_case_uuid}/reaction?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'reaction': 'agree',
        'value': True
    })
    assert response.status_code == 200
    GroupManagement.remove_user_from_group(user_uuid=user.user_uuid, group_uuid=group_uuid, session=session)
    session.commit()


def test_case_update(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    user_uid = user.user_uid
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid
    resolved_uuid = _create_label(name="Resolved", session=session).label_uuid
    unresolved_uuid = _create_label(name="Unresolved", session=session).label_uuid

    # Missing user returns 404
    response = client.post(f'/pro/v1/case/{case_uuid}/update?force_synchronous=true', headers=headers, json={
        'user_uid': 'fake_user',
        'text': 'Update text'
    })
    assert response.status_code == 404

    # Missing case returns 404
    response = client.post(f'/pro/v1/case/00000000-0000-0000-0000-000000000000/update?force_synchronous=true',
                           headers=headers,
                           json={'user_uid': user_uid, 'text': 'Update text'})
    assert response.status_code == 404

    # Missing text returns 400
    response = client.post(f'/pro/v1/case/{case_uuid}/update?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid
    })
    assert response.status_code == 400

    # Null content_uuid saves update on first content of case
    update_text = "Update text"
    response = client.post(f'/pro/v1/case/{case_uuid}/update?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'text': update_text,
        'resolved': False
    })
    assert response.status_code == 200
    case = session.query(Case) \
        .filter(Case.case_uuid == case_uuid) \
        .one()
    assert len(case.content[0].updates) == 1
    assert case.content[0].updates[0].text == update_text
    assert not any(label.label_uuid == resolved_uuid for label in case.labels)
    assert any(label.label_uuid == unresolved_uuid for label in case.labels)

    # Can add new update and change to resolved
    update_text2 = "Second update text"
    response = client.post(f'/pro/v1/case/{case_uuid}/update?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'text': update_text2,
        'resolved': True
    })
    assert response.status_code == 200
    session.refresh(case)
    session.refresh(case.content[0])
    assert len(case.content[0].updates) == 2
    assert case.content[0].updates[1].text == update_text2
    assert case.content[0].updates[1].linked_update_uuid is None
    assert any(label.label_uuid == resolved_uuid for label in case.labels)
    assert not any(label.label_uuid == unresolved_uuid for label in case.labels)

    # Test linked_update_uuid
    update_text3 = "Third update text"
    response = client.post(f'/pro/v1/case/{case_uuid}/update?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'text': update_text3,
        'resolved': True,
        'linked_update_uuid': '02b7d6a2-72e5-411e-a3b2-bfaf7c732311'
    })
    assert response.status_code == 200
    session.refresh(case)
    session.refresh(case.content[0])
    assert str(case.content[0].updates[-1].linked_update_uuid) == '02b7d6a2-72e5-411e-a3b2-bfaf7c732311'


def test_add_case_diagnosis(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    user_uid = user.user_uid
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid

    diagnosis_text = "diagnosis text"
    response = client.post(f'/pro/v1/case/{case_uuid}/update?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'diagnosis_text': diagnosis_text
    })
    assert response.status_code == 200
    case = session.query(Case) \
        .filter(Case.case_uuid == case_uuid) \
        .one()
    assert len(case.content[0].updates) == 1
    assert case.content[0].updates[0].text == diagnosis_text
    assert case.diagnoses[0].text == "diagnosis text"


def test_content_position(client, headers, load_db):
    session = load_db
    user = _create_user(session=session)
    user_uid = user.user_uid
    case_uuid = _create_case(author_uuid=user.user_uuid, session=session).case_uuid

    # Test updating content position, setting to incomplete
    res = client.post(f'/pro/v1/case/{case_uuid}/progress?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'content_position': 1,
        'is_complete': False
    })
    assert res.status_code == 200

    cp = session.query(CaseProgress).get((case_uuid, user.user_uuid))
    assert cp.content_position == 1
    assert cp.completed_at is None

    # Test updating content position, setting to complete
    res = client.post(f'/pro/v1/case/{case_uuid}/progress?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'content_position': 3,
        'is_complete': True,
        'degree_type': 'M.D.'
    })
    assert res.status_code == 200

    session.refresh(cp)
    assert cp.content_position == 3
    assert cp.completed_at is not None

    # Test null is_complete does not update previous completion state
    res = client.post(f'/pro/v1/case/{case_uuid}/progress?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'content_position': 3,
        'is_complete': None,
        'degree_type': 'M.D.'
    })
    assert res.status_code == 200

    session.refresh(cp)
    assert cp.content_position == 3
    assert cp.completed_at is not None

    # Test invalid degree_type
    res = client.post(f'/pro/v1/case/{case_uuid}/progress?force_synchronous=true', headers=headers, json={
        'user_uid': user_uid,
        'content_position': 1,
        'is_complete': False,
        'degree_type': "ThisDegreeTypeIsOverTheMaxCharacterLimit"
    })
    assert res.status_code == 422

    # Test anonymous user
    anon = AnonymousUser()
    anon.user_uid = 'anonymous_uid'
    anon.user_uuid = user.user_uuid
    session.add(anon)
    session.commit()

    res = client.post(f'/pro/v1/case/{case_uuid}/progress?force_synchronous=true', headers=headers, json={
        'user_uid': 'anonymous_uid',
        'content_position': 4,
        'is_complete': None,
        'degree_type': 'M.D.'
    })
    assert res.status_code == 200

    session.refresh(cp)
    assert cp.content_position == 4
    assert cp.completed_at is not None


def test_translate_case(load_db, test_case_pending_approval, case_update):
    session = load_db
    update_uuid = case_update.update_uuid
    case_uuid = test_case_pending_approval.case_uuid

    with patch('figure1.common.helpers.case_management.translate_client') as mock_translate_client:
        mock_translate = MagicMock()
        mock_translate.translate.return_value = {"translatedText": "translated_text"}
        mock_translate_client.return_value = mock_translate

        CaseManagement.translate_case(case_uuid, session, "en", target_language=Locale.PT_PT)
        session.flush()

        content = test_case_pending_approval.content[0]
        content_translation = session.query(ContentTranslation) \
            .filter(ContentTranslation.content_uuid == content.content_uuid,
                    ContentTranslation.target_language == "PT_PT").one_or_none()

        case_update_translation = session.query(ContentUpdateTranslations) \
            .filter(ContentUpdateTranslations.update_uuid == update_uuid,
                    ContentUpdateTranslations.language == "PT_PT").one_or_none()

        assert content_translation is not None
        assert content_translation.title == "translated_text"
        assert content_translation.caption == "translated_text"
        assert content_translation.target_language == "PT_PT"

        assert case_update_translation is not None
        assert case_update_translation.text == "translated_text"
        assert case_update_translation.language == "PT_PT"

        # call translate_case again with the same target language.
        CaseManagement.translate_case(case_uuid, session, "en", target_language=Locale.PT_PT)
        session.flush()

        content_translations = session.query(ContentTranslation) \
            .filter(ContentTranslation.content_uuid == content.content_uuid,
                    ContentTranslation.target_language == "PT_PT").all()

        assert len(content_translations) == 1
        content_translation = content_translations[0]
        assert content_translation.title == "translated_text"
        assert content_translation.caption == "translated_text"

        case_update_translations = session.query(ContentUpdateTranslations) \
            .filter(ContentUpdateTranslations.update_uuid == update_uuid,
                    ContentUpdateTranslations.language == "PT_PT").all()

        assert len(case_update_translations) == 1
        case_update_translation = case_update_translations[0]
        assert case_update_translation.language == "PT_PT"
        assert case_update_translation.text == "translated_text"


def test_firestore_case_detail_translations(load_db,
                                            case_update,
                                            test_case_pending_approval,
                                            case_content_translation,
                                            case_update_translation):
    session = load_db
    case_uuid = test_case_pending_approval.case_uuid
    case_data = CaseDetail.firestore_case_detail(case_uuid, session)

    content_items = case_data.get('contentItems', None)
    assert content_items is not None

    assert len(content_items) == 1
    content_0_translation = content_items[0]['translations']

    assert content_0_translation is not None
    assert isinstance(content_0_translation, dict)
    assert content_0_translation['PT_PT']['title'] == "title"
    assert content_0_translation['PT_PT']['caption'] == "caption"
    assert content_0_translation['PT_PT']['language'] == "PT_PT"

    updates = content_items[0]['updates']
    assert updates is not None

    assert len(updates) == 1
    update_0_translations = updates[0]['translations']

    assert update_0_translations is not None
    assert isinstance(update_0_translations, dict)
    assert update_0_translations['PT_PT']['text'] == 'text'
    assert update_0_translations['PT_PT']['language'] == 'PT_PT'


def test_firestore_case_detail(load_db):
    session = load_db
    user = _create_user(session=session)

    case, _ = create_test_case(
        author_uuid=user.user_uuid,
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        is_anonymous=True,
        session=session)

    session.commit()
    case_uuid = case.case_uuid
    case_data = CaseDetail.firestore_case_detail(case_uuid, session)

    author = case_data['authors'][0]
    assert case.is_anonymous is True
    assert author.get('displayName') is None
    assert author.get('caseCommentDisplayName') is None
    assert author.get('profileDisplayName') is None
    assert author.get('avatar') is None
    assert author.get('username') is None
    assert author.get('userUid') is None
    assert author.get('userUuid') is None
    assert author.get('profileLink') is None
    assert author.get('profileLinkText') is None
    assert author.get('userType') is None
    assert author.get('countryUuid') is None
    assert author.get('stateUuid') is None
    assert author.get('isPartner') is None
    assert author.get('legacyAccount') is None
    assert author.get('isAnonymous') is True
