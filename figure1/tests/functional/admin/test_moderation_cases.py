import time
from typing import Callable

from figure1.common.models.db import CaseNote, CaseEdit, CaseMediaEdit, Case, Label, CaseLabel, ContentUpdate
from figure1.admin.moderation.cases.domain import add_partner_case_settings
from figure1.common.types import CaseState, Locale, CaseRejectionReason
from figure1.common.types.case import ContentUpdateType
from figure1.configuration import es_settings
from figure1.tests.utils.case import create_test_case


def _create_fs_draft(fs, user_uid, draft_uid, case_uuid):
    fs.collection('userDraftsDB') \
        .document(user_uid) \
        .collection('all') \
        .document(draft_uid) \
        .set({"draftUid": draft_uid, "caseUuid": str(case_uuid)})


def _get_fs_doc(documents, collections, fs, doc_filter: Callable[[dict], bool] = None):
    count = 0
    for d, c in zip(documents, collections):
        fs = fs.collection(c).document(d)
    doc = fs.get()
    while not doc.exists or (doc_filter and not doc_filter(doc.to_dict())):
        doc = fs.get()
        count += 1
        if count >= 10:
            raise TimeoutError
        time.sleep(1)
    return doc.to_dict()


def test_approve_case(client, headers, load_db, test_case_pending_approval, test_user):
    test_case = test_case_pending_approval
    session = load_db
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Approving for invalid case returns 404
    invalid_case_uuid = '00000000-0000-0000-0000-000000000000'
    response = client.post(f'/admin/v1/moderation/cases/{invalid_case_uuid}/approve', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Approving for invalid user returns 404
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/approve', headers=headers, json={
        'moderator_uid': 'fake_user'
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Approving marks case state as approved and updates published_at
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/approve', headers=headers, json={
        'moderator_uid': test_user.get('userUid')
    })
    assert response.status_code == 200

    session.refresh(test_case)
    assert len(test_case.case_history) == 2
    assert str(test_case.case_history[-1].event_author_uuid) == test_user.get('userUuid')
    assert test_case.case_history[-1].case_state == CaseState.PENDING_NLP
    assert test_case.state == CaseState.PENDING_NLP


def test_reject_case(client, headers, load_db, test_case_pending_approval, test_user, get_firestore_client):
    test_case = test_case_pending_approval
    session = load_db
    fs = get_firestore_client

    draft_uid = 'GxJFitHdu8TuVWvNh0F4'
    _create_fs_draft(fs=fs, user_uid=test_user.get('userUid'), draft_uid=draft_uid, case_uuid=test_case.case_uuid)

    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Rejecting with invalid reason returns 400
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/reject', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'reason': 'cat_picture'
    })
    assert response.status_code == 400
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Rejecting for invalid case returns 404
    invalid_case_uuid = '00000000-0000-0000-0000-000000000000'
    response = client.post(f'/admin/v1/moderation/cases/{invalid_case_uuid}/reject', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'reason': 'inappropriate_content',
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Rejecting for invalid user returns 404
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/reject', headers=headers, json={
        'moderator_uid': 'fake_user',
        'reason': 'inappropriate_content',
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Rejecting with allow_revision=true reason marks case state as rejected and updates firestore
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/reject', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'reason': 'not_direct_care',
    })
    assert response.status_code == 200

    session.refresh(test_case)
    assert test_case.state == CaseState.REJECTED
    assert test_case.published_at is None
    assert len(test_case.case_history) == 2
    assert str(test_case.case_history[-1].event_author_uuid) == test_user.get('userUuid')
    assert test_case.case_history[-1].case_state == CaseState.REJECTED

    fs_doc = _get_fs_doc(documents=[test_user.get('userUid'), draft_uid],
                         collections=['userDraftsDB', 'all'],
                         fs=fs,
                         doc_filter=lambda x: 'rejectionReason' in x)
    assert fs_doc.get('rejectionReason') == 'not_direct_care'
    assert fs_doc.get('rejectionReasonMessage') == CaseRejectionReason.NOT_DIRECT_CARE.message

    # Rejecting with allow_revision=false reason deletes case
    test_case.state = CaseState.PENDING_APPROVAL
    session.commit()
    assert len(test_case.case_history) == 3

    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/reject', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'reason': 'inappropriate_content',
    })
    assert response.status_code == 200

    session.refresh(test_case)
    assert test_case.state == CaseState.DELETED
    assert test_case.published_at is None
    assert test_case.deleted_at is not None
    assert len(test_case.content) == 0
    assert len(test_case.case_history) == 4
    assert str(test_case.case_history[-1].event_author_uuid) == test_user.get('userUuid')
    assert test_case.case_history[-1].case_state == CaseState.DELETED


def test_flag_case(client, headers, load_db, test_case_pending_approval, test_user, get_firestore_client):
    test_case = test_case_pending_approval
    session = load_db
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Flag for invalid case returns 404
    invalid_case_uuid = '00000000-0000-0000-0000-000000000000'
    response = client.post(f'/admin/v1/moderation/cases/{invalid_case_uuid}/flag', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Flag for invalid user returns 404
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/flag', headers=headers, json={
        'moderator_uid': 'fake_user'
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Flag case sets state to flagged
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/flag', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response.status_code == 200

    session.refresh(test_case)
    assert test_case.state == CaseState.FLAGGED
    assert test_case.published_at is None
    assert len(test_case.case_history) == 2
    assert str(test_case.case_history[-1].event_author_uuid) == test_user.get('userUuid')
    assert test_case.case_history[-1].case_state == CaseState.FLAGGED


def test_remove_paging_from_case(client, headers, load_db, test_case_pending_approval, test_user, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    test_case1, content = create_test_case(
        author_uuid=test_user.get('userUuid'),
        is_paging_case=True,
        language=Locale.EN_US.code,
        title="Case Title",
        caption="Case Caption",
        state=CaseState.PENDING_APPROVAL,
        session=session)

    # invalid case returns 404
    invalid_case_uuid = '00000000-0000-0000-0000-000000000000'
    response1 = client.post(f'/admin/v1/moderation/cases/{invalid_case_uuid}/remove_paging', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response1.status_code == 404

    # invalid user returns 404
    response2 = client.post(f'/admin/v1/moderation/cases/{test_case1.case_uuid}/remove_paging', headers=headers, json={
        'moderator_uid': 'fake_user'
    })
    assert response2.status_code == 404

    # non paging case returns 422
    test_case2 = test_case_pending_approval
    response3 = client.post(f'/admin/v1/moderation/cases/{test_case2.case_uuid}/remove_paging', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response3.status_code == 422

    # sets is_paging to False
    response4 = client.post(f'/admin/v1/moderation/cases/{test_case1.case_uuid}/remove_paging', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response4.status_code == 200

    session.refresh(test_case1)
    assert test_case1.is_paging_case is False
    assert test_case1.published_at is None


def test_case_note(client, headers, load_db, test_case_pending_approval, test_user, get_firestore_client):
    test_case = test_case_pending_approval
    session = load_db
    fs = get_firestore_client

    # Case note with missing text returns 400
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/note', headers=headers, json={
        'moderator_uid': test_user.get('userUid')
    })
    assert response.status_code == 400

    # Case note for invalid case returns 404
    invalid_case_uuid = '00000000-0000-0000-0000-000000000000'
    response = client.post(f'/admin/v1/moderation/cases/{invalid_case_uuid}/note', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'text': 'sample case note'
    })
    assert response.status_code == 404

    # Case note for invalid user returns 404
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/note', headers=headers, json={
        'moderator_uid': 'fake_user',
        'text': 'sample case note'
    })
    assert response.status_code == 404

    # Case note adds row to case note
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/note', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'text': 'sample case note'
    })
    assert response.status_code == 200

    n = session.query(CaseNote).filter(CaseNote.case_uuid == test_case.case_uuid).one()
    assert n
    assert n.text == 'sample case note'


def test_case_edit(client, headers, load_db, test_case_pending_approval, test_user, get_firestore_client):
    test_case = test_case_pending_approval
    session = load_db
    fs = get_firestore_client

    content = test_case.content[0]
    original_case_title = content.title
    original_case_caption = content.caption
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Case edit for invalid case returns 404
    invalid_case_uuid = '00000000-0000-0000-0000-000000000000'
    response = client.post(f'/admin/v1/moderation/cases/{invalid_case_uuid}/edit', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Case edit for invalid user returns 404
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit', headers=headers, json={
        'moderator_uid': 'fake_user',
    })
    assert response.status_code == 404
    assert len(test_case.case_history) == 1
    assert test_case.case_history[-1].event_author_uuid is None

    # Case edit with suggested_edit=true adds row to m_case_edit, does not yet update content
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit?suggested_edit=true',
                           headers=headers,
                           json={
                               'moderator_uid': test_user.get('userUid'),
                               'title': 'sample title edit',
                               'caption': 'sample caption edit',
                               'diagnosis': 'sample diagnosis edit'
                           })
    assert response.status_code == 200

    session.refresh(test_case)
    session.refresh(content)
    e = session.query(CaseEdit).filter(CaseEdit.content_uuid == content.content_uuid).one()
    assert e
    assert e.title == 'sample title edit'
    assert e.caption == 'sample caption edit'
    assert e.diagnosis == 'sample diagnosis edit'
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit_suggested',
                           headers=headers)
    assert response.status_code == 200
    session.refresh(test_case)
    assert test_case.state == CaseState.EDIT_SUGGESTED
    assert len(test_case.case_history) == 2
    assert test_case.case_history[-1].case_state == CaseState.EDIT_SUGGESTED

    assert content.title == original_case_title
    assert content.caption == original_case_caption
    assert len(content.updates) == 0

    #
    # Case edit with suggested_edit not set applies edit immediately
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit',
                           headers=headers,
                           json={
                               'moderator_uid': test_user.get('userUid'),
                               'caption': 'another caption edit'
                           })

    assert response.status_code == 200
    session.refresh(content)
    assert content.caption == f'another caption edit'


def test_case_edit_reject(client, headers, load_db, test_case_pending_approval, test_user, get_firestore_client):
    test_case = test_case_pending_approval
    session = load_db
    fs = get_firestore_client

    content = test_case.content[0]
    original_case_title = content.title
    original_case_caption = content.caption
    e = CaseEdit.create(content_uuid=content.content_uuid,
                        moderator_uuid=test_user.get('userUuid'),
                        session=session,
                        caption='sample caption edit')
    test_case.state = CaseState.EDIT_SUGGESTED
    session.commit()

    # Rejecting case edit does not modify case content
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit/reject/{e.edit_uuid}',
                           headers=headers,
                           json={'moderator_uid': test_user.get('userUid')})
    assert response.status_code == 200

    session.refresh(e)
    assert e.edit_applied is False
    assert e.edit_approved is False
    assert e.deleted_at is not None
    session.refresh(test_case)
    assert content.title == original_case_title
    assert content.caption == original_case_caption


def test_case_edit_approve(client, headers, load_db, test_case_pending_approval, test_user, get_firestore_client):
    test_case = test_case_pending_approval
    session = load_db
    fs = get_firestore_client

    content = test_case.content[0]
    original_case_title = content.title
    e = CaseEdit.create(content_uuid=content.content_uuid,
                        moderator_uuid=test_user.get('userUuid'),
                        session=session,
                        caption='sample caption edit',
                        diagnosis='sample diagnosis edit')
    test_case.state = CaseState.EDIT_SUGGESTED
    session.commit()

    # Approving case edit updates case content with edit details
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit/approve/{e.edit_uuid}',
                           headers=headers,
                           json={'moderator_uid': test_user.get('userUid')})
    assert response.status_code == 200

    session.refresh(e)
    assert e.edit_applied is True
    assert e.edit_approved is True
    session.refresh(test_case)
    assert content.title == original_case_title
    assert content.caption == 'sample caption edit'
    assert len(content.updates) == 1
    assert content.updates[0].text == 'sample diagnosis edit'
    assert content.updates[0].update_type == ContentUpdateType.DIAGNOSIS
    assert content.updates[0].linked_update_uuid is None


def test_case_edit_media_reject(client, headers, load_db, test_case_pending_approval, test_user):
    test_case = test_case_pending_approval
    session = load_db

    content = test_case.content[0]
    media = content.media[0]
    original_filename = media.filename
    e = CaseMediaEdit.create(media_uuid=media.media_uuid,
                             moderator_uuid=test_user.get('userUuid'),
                             session=session,
                             filename='editedImage.png')
    test_case.state = CaseState.EDIT_SUGGESTED
    session.commit()

    # Rejecting case media edit does not modify media filename
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit/reject/media/{e.media_edit_uuid}',
                           headers=headers,
                           json={'moderator_uid': test_user.get('userUid')})
    assert response.status_code == 200

    session.refresh(e)
    session.refresh(test_case)
    assert e.edit_applied is False
    assert e.edit_approved is False
    assert e.deleted_at is not None
    assert media.filename == original_filename


def test_case_edit_media_approve(client, headers, load_db, test_case_pending_approval, test_user):
    test_case = test_case_pending_approval
    session = load_db

    content = test_case.content[0]
    media = content.media[0]
    e = CaseMediaEdit.create(media_uuid=media.media_uuid,
                             moderator_uuid=test_user.get('userUuid'),
                             session=session,
                             filename='editedImage.png')
    test_case.state = CaseState.EDIT_SUGGESTED
    session.commit()

    # Approving case media edit updates media filename
    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/edit/approve/media/{e.media_edit_uuid}',
                           headers=headers,
                           json={'moderator_uid': test_user.get('userUid')})
    assert response.status_code == 200

    session.refresh(e)
    assert e.edit_applied is True
    assert e.edit_approved is True

    session.refresh(test_case)
    assert media.filename == 'editedImage.png'


def test_set_case_labels(client, headers, load_db, test_case_pending_approval, test_user):
    test_case = test_case_pending_approval
    session = load_db

    labels = session.query(Label).all()

    cl = session.query(CaseLabel) \
        .filter(CaseLabel.case_uuid == test_case_pending_approval.case_uuid,
                CaseLabel.deleted_at.is_(None)) \
        .all()
    assert len(cl) == 0

    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/labels',
                           headers=headers,
                           json={
                               'moderator_uid': test_user.get('userUid'),
                               'label_uuids': [labels[1].label_uuid, labels[2].label_uuid]
                           })
    assert response.status_code == 200

    cl = [x for x, in (session.query(CaseLabel.label_uuid)
                       .filter(CaseLabel.case_uuid == test_case_pending_approval.case_uuid,
                               CaseLabel.deleted_at.is_(None))
                       .all())]
    assert len(cl) == 2
    assert labels[1].label_uuid in cl
    assert labels[2].label_uuid in cl

    response = client.post(f'/admin/v1/moderation/cases/{test_case.case_uuid}/labels',
                           headers=headers,
                           json={
                               'moderator_uid': test_user.get('userUid'),
                               'label_uuids': [labels[2].label_uuid]
                           })
    assert response.status_code == 200

    cl = [x for x, in (session.query(CaseLabel.label_uuid)
                       .filter(CaseLabel.case_uuid == test_case_pending_approval.case_uuid,
                               CaseLabel.deleted_at.is_(None))
                       .all())]
    assert len(cl) == 1
    assert labels[1].label_uuid not in cl
    assert labels[2].label_uuid in cl


def test_case_note_with_media(client,
                              headers,
                              load_db,
                              test_user,
                              test_case_pending_approval,
                              get_elasticsearch_client):
    test_case = test_case_pending_approval
    es = get_elasticsearch_client
    session = load_db
    content = test_case.content[0]
    media = content.media[0]
    e = CaseMediaEdit.create(media_uuid=media.media_uuid,
                             moderator_uuid=test_user.get('userUuid'),
                             session=session,
                             filename='editedImage.png')
    session.commit()
    response = client.post(f'/admin/v1/moderation/tagging/{test_case.case_uuid}/flag', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'text': 'sample case note'
    })
    assert response.status_code == 200
    es_state = es.get(index=es_settings.cases_alias, id=str(test_case.case_uuid))
    mod_notes = es_state.get('_source', {}).get('moderationNotes', [])
    assert len(mod_notes) > 0
    assert test_user.get('userUid') in [x.get('moderatorUid') for x in mod_notes]


def test_add_partner_case_details(load_db, test_user, test_case_pending_approval):
    test_case = test_case_pending_approval
    session = load_db
    moderator_uid = test_user.get("userUid")
    add_partner_case_settings(session=session,
                              moderator_uid=moderator_uid,
                              case_uuid=test_case.case_uuid,
                              data={'disclosure_text': "my disclosure text"})
    session.commit()
    q = session.query(Case).filter(Case.case_uuid == test_case.case_uuid).first()
    assert q.content[0].sponsored_content.disclosure_text == 'my disclosure text'
    add_partner_case_settings(session=session,
                              moderator_uid=moderator_uid,
                              case_uuid=test_case.case_uuid,
                              data={'external_link_url': "http://www.google.ca"})
    session.commit()
    session.refresh(q)
    assert q.content[0].extension.external_link_url == 'http://www.google.ca'
    assert q.content[0].extension.external_link_text == 'http://www.google.ca'

    add_partner_case_settings(session=session,
                              moderator_uid=moderator_uid,
                              case_uuid=test_case.case_uuid,
                              data={'external_link_text': "google",
                                    'external_link_url': "http://www.google.ca"})

    session.commit()
    session.refresh(q)
    assert q.content[0].extension.external_link_url == 'http://www.google.ca'
    assert q.content[0].extension.external_link_text == 'google'

    add_partner_case_settings(session=session,
                              moderator_uid=moderator_uid,
                              case_uuid=test_case.case_uuid,
                              data={'disclosure_text': "delete", 'sponsored_text': "my sponsored text"})
    session.commit()
    session.refresh(q)
    assert q.content[0].sponsored_content.disclosure_text is None
    assert q.content[0].sponsored_content.sponsored_text == 'my sponsored text'
