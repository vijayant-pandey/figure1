import time

from figure1.common.models.db import VerificationTag, VerificationNote, UserVerification, \
    UserVerificationTag, SpecialtyTreeV2, ProfessionV2, UserProfile, User
from figure1.common.types import VerificationStatus


def _get_tags_fs_doc(fs):
    def get_doc():
        return fs.collection('referenceData').document('verificationTags').get()

    doc = get_doc()
    count = 0
    while not doc.exists:
        doc = get_doc()
        count += 1
        if count >= 10:
            raise TimeoutError("Firestore document not populated is %s seconds", count)
        time.sleep(1)
    return doc.to_dict()


def test_edit_verification(client,
                           headers,
                           load_db,
                           test_user,
                           test_user_pending_verification,
                           test_country,
                           test_state,
                           test_school,
                           user_specialty):
    session = load_db
    session.commit()
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    profession = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None),
                                                       SpecialtyTreeV2.subspecialty_uuid.is_(None)).first()
    response = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "first_name": "updatedFirstName",
        "graduation_year": 2000,
        "last_name": "updatedLastName",
        "medical_license": 'abc123',
        "npi_number": 1234567893,
        "school_uuid": str(test_school.school_uuid),
        "profession_uuid": str(profession.specialty_uuid),
        "specialty_uuid": user_specialty.treeUuid,
        "country_uuid": str(test_country.country_uuid),
        "state_uuid": str(test_state.country_uuid),
        "flag_for_review": True,
    })

    j = response.json
    assert response.status_code == 200

    session.refresh(test_user_pending_verification)
    assert test_user_pending_verification.first_name == 'updatedFirstName'
    assert test_user_pending_verification.last_name == 'updatedLastName'
    assert test_user_pending_verification.user_profile.display_name == 'updatedFirstName updatedLastName'

    user_metadata = session.query(UserProfile).filter(UserProfile.user_uuid == user_uuid).one()
    assert user_metadata.country_uuid == test_country.country_uuid
    assert user_metadata.state_uuid == test_state.country_uuid

    verification = session.query(UserVerification).filter(UserVerification.user_uuid == user_uuid).one()
    assert verification.graduation_year == 2000
    assert verification.school_uuid == test_school.school_uuid
    assert verification.license.license_number == 'abc123'
    assert verification.npi.npi_number == 1234567893
    assert verification.flagged_for_review is True


def test_edit_verification_with_empty_npi_number(client,
                                                 headers,
                                                 load_db,
                                                 test_user,
                                                 test_user_pending_verification):
    session = load_db
    session.commit()
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    response = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "npi_number": 1234567893,
    })

    verification = session.query(UserVerification).filter(UserVerification.user_uuid == user_uuid).one()
    assert response.status_code == 200
    assert verification.npi.npi_number == 1234567893

    response1 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "npi_number": "   ",
    })

    session.refresh(verification)
    assert response1.status_code == 200
    assert verification.npi is None

    response2 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "npi_number": 1234567893,
    })

    session.refresh(verification)
    assert response2.status_code == 200
    assert verification.npi.npi_number == 1234567893

    response3 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "npi_number": "",
    })

    session.refresh(verification)
    assert response3.status_code == 200
    assert verification.npi is None


def test_edit_verification_with_empty_first_name_or_last_name(client,
                                                              headers,
                                                              load_db,
                                                              test_user,
                                                              test_user_pending_verification):
    session = load_db
    session.commit()
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid

    assert test_user_pending_verification.first_name != ""
    assert test_user_pending_verification.last_name != ""

    response = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "first_name": "",
    })

    assert response.status_code == 200
    session.refresh(test_user_pending_verification)
    assert test_user_pending_verification.first_name == ""

    response1 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "first_name": "    ",
    })

    assert response1.status_code == 200
    session.refresh(test_user_pending_verification)
    assert test_user_pending_verification.first_name == "    "

    response2 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "last_name": "",
    })

    assert response2.status_code == 200
    session.refresh(test_user_pending_verification)
    assert test_user_pending_verification.last_name == ""

    response3 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "last_name": "    ",
    })

    assert response3.status_code == 200
    session.refresh(test_user_pending_verification)
    assert test_user_pending_verification.last_name == "    "

    response4 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "first_name": "firstname",
        "last_name": "lastname",
    })

    assert response4.status_code == 200
    session.refresh(test_user_pending_verification)
    assert test_user_pending_verification.user_profile.display_name == "firstname lastname"

    response5 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "first_name": "",
        "last_name": "",
    })

    assert response5.status_code == 200
    session.refresh(test_user_pending_verification)
    assert test_user_pending_verification.user_profile.display_name == " "


def test_edit_verification_with_empty_school_uuid(client,
                                                  headers,
                                                  load_db,
                                                  test_user,
                                                  test_school,
                                                  test_user_pending_verification):
    session = load_db
    session.commit()
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    verification = session.query(UserVerification).filter(UserVerification.user_uuid == user_uuid).one()

    response = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "school_uuid": str(test_school.school_uuid),
    })

    assert response.status_code == 200
    session.refresh(verification)
    assert verification.school_uuid == test_school.school_uuid

    response1 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "school_uuid": "",
    })

    assert response1.status_code == 200
    session.refresh(verification)
    assert verification.school_uuid is None

    response2 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "school_uuid": str(test_school.school_uuid),
    })

    assert response2.status_code == 200
    session.refresh(verification)
    assert verification.school_uuid == test_school.school_uuid

    response3 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "school_uuid": "      ",
    })

    assert response3.status_code == 200
    session.refresh(verification)
    assert verification.school_uuid is None


def test_edit_verification_with_empty_graduation_year(client,
                                                      headers,
                                                      load_db,
                                                      test_user,
                                                      test_user_pending_verification):
    session = load_db
    session.commit()
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    verification = session.query(UserVerification).filter(UserVerification.user_uuid == user_uuid).one()

    response = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "graduation_year": "2000",
    })

    assert response.status_code == 200
    session.refresh(verification)
    assert verification.graduation_year == 2000

    response1 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "graduation_year": "",
    })

    assert response1.status_code == 200
    session.refresh(verification)
    assert verification.graduation_year is None

    response2 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "graduation_year": "2001",
    })

    assert response2.status_code == 200
    session.refresh(verification)
    assert verification.graduation_year == 2001

    response3 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "graduation_year": "          ",
    })

    assert response3.status_code == 200
    session.refresh(verification)
    assert verification.graduation_year is None


def test_edit_verification_with_empty_medical_license(client,
                                                      headers,
                                                      load_db,
                                                      test_user,
                                                      test_user_pending_verification):
    session = load_db
    session.commit()
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    verification = session.query(UserVerification).filter(UserVerification.user_uuid == user_uuid).one()

    response = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "medical_license": "ml001",
    })

    assert response.status_code == 200
    session.refresh(verification)
    assert verification.license.license_number == "ml001"

    response1 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "medical_license": "  ",
    })

    assert response1.status_code == 200
    session.refresh(verification)
    assert verification.license.license_number == "  "

    response2 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "medical_license": "k001",
    })

    assert response2.status_code == 200
    session.refresh(verification)
    assert verification.license.license_number == "k001"

    response3 = client.patch(f'/admin/v1/verification/edit/{user_uid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "medical_license": "",
    })

    assert response3.status_code == 200
    session.refresh(verification)
    assert verification.license.license_number == ""


def test_add_note(client, headers, load_db, test_user, test_user_pending_verification):
    session = load_db
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    response = client.post(f'/admin/v1/verification/note', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "text": "Sample note",
    })
    assert response.status_code == 200

    n = session.query(VerificationNote) \
        .filter(VerificationNote.user_uuid == user_uuid) \
        .order_by(VerificationNote.created_at) \
        .all()
    assert len(n) == 1
    assert n[0].text == 'Sample note'

    response = client.post(f'/admin/v1/verification/note', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "text": "Another note",
    })
    assert response.status_code == 200

    n = session.query(VerificationNote) \
        .filter(VerificationNote.user_uuid == user_uuid) \
        .order_by(VerificationNote.created_at) \
        .all()
    assert len(n) == 2
    assert n[0].text == 'Sample note'
    assert n[1].text == 'Another note'


def test_update_state(client, headers, load_db, test_user, test_user_pending_verification):
    session = load_db
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    v = session.query(UserVerification) \
        .filter(UserVerification.user_uuid == user_uuid) \
        .one()
    assert v.verification_status == VerificationStatus.PENDING_MANUAL_VERIFICATION

    response = client.post(f'/admin/v1/verification/state', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "state": "unverifiable",
        "flag_for_review": False
    })

    assert response.status_code == 200

    session.refresh(v)
    assert v.verification_status == VerificationStatus.UNVERIFIABLE
    assert v.flagged_for_review is False
    response = client.post(f'/admin/v1/verification/state', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "state": "verified",
        "flag_for_review": True,
    })

    assert response.status_code == 200

    session.refresh(v)
    assert v.verification_status == VerificationStatus.VERIFIED
    assert v.flagged_for_review is True

    response2 = client.post(f'/admin/v1/verification/state', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "state": "verified",
        "flag_for_review": False,
    })
    assert response2.status_code == 200
    session.refresh(v)
    assert v.flagged_for_review is False


def test_tags(client, headers, load_db, test_user, test_user_pending_verification, get_firestore_client,
              get_elasticsearch_client, create_user_es_index):
    session = load_db
    fs = get_firestore_client
    es = get_elasticsearch_client
    user_index = create_user_es_index
    moderator_uid = test_user.get('userUid')
    user_uid = test_user_pending_verification.user_uid
    user_uuid = test_user_pending_verification.user_uuid

    # Create tag
    response = client.post(f'/admin/v1/verification/tag/manage', headers=headers, json={
        'moderator_uid': moderator_uid,
        'actions': [{
            'action': 'create',
            'name': 'Test tag'
        }]
    })
    assert response.status_code == 200

    t = session.query(VerificationTag) \
        .filter(VerificationTag.name == 'Test tag') \
        .one_or_none()
    assert t

    doc = _get_tags_fs_doc(fs)
    assert doc['all'][str(t.tag_uuid)]['name'] == 'Test tag'
    assert doc['all'][str(t.tag_uuid)]['tagUuid'] == str(t.tag_uuid)
    fs.collection('referenceData').document('verificationTags').delete()

    # Update tag
    response = client.post(f'/admin/v1/verification/tag/manage', headers=headers, json={
        'moderator_uid': moderator_uid,
        'actions': [{
            'action': 'update',
            'uuid': str(t.tag_uuid),
            'name': 'Updated tag'
        }]
    })
    assert response.status_code == 200

    session.refresh(t)
    assert t.name == 'Updated tag'

    doc = _get_tags_fs_doc(fs)
    assert doc['all'][str(t.tag_uuid)]['name'] == 'Updated tag'
    assert doc['all'][str(t.tag_uuid)]['tagUuid'] == str(t.tag_uuid)
    fs.collection('referenceData').document('verificationTags').delete()

    # Delete tag
    response = client.post(f'/admin/v1/verification/tag/manage', headers=headers, json={
        'moderator_uid': moderator_uid,
        'actions': [{
            'action': 'delete',
            'uuid': str(t.tag_uuid),
        }]
    })
    assert response.status_code == 200

    session.refresh(t)
    assert t.deleted_at is not None

    doc = _get_tags_fs_doc(fs)
    assert len(doc['all']) == 0

    # Modify tags for user verification
    tag_a = VerificationTag.create(name="tag_a", session=session)
    tag_b = VerificationTag.create(name="tag_b", session=session)
    tag_c = VerificationTag.create(name="tag_c", session=session)
    tag_d = VerificationTag.create(name="tag_d", session=session)

    session.flush()

    response = client.post(f'/admin/v1/verification/tag', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "tag_uuids": [tag_a.tag_uuid, tag_c.tag_uuid, tag_d.tag_uuid],
    })
    assert response.status_code == 200

    user_doc = es.get(index=user_index, id=user_uuid)
    for v in user_doc.get('_source').get('verificationTags'):
        assert v.get('tagUuid') in [str(tag_a.tag_uuid), str(tag_c.tag_uuid), str(tag_d.tag_uuid)]
    assert len(user_doc.get('_source').get('verificationTags')) == 3

    n = session.query(UserVerificationTag) \
        .filter(UserVerificationTag.user_uuid == user_uuid, UserVerificationTag.deleted_at.is_(None)) \
        .order_by(UserVerificationTag.created_at)
    assert n.count() == 3
    for resp in n.all():
        assert resp.deleted_at is None
        assert resp.tag_uuid in [tag_a.tag_uuid, tag_c.tag_uuid, tag_d.tag_uuid]

    response = client.post(f'/admin/v1/verification/tag', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "tag_uuids": [tag_c.tag_uuid, tag_b.tag_uuid, tag_a.tag_uuid],
    })

    assert response.status_code == 200
    user_doc = es.get(index=user_index, id=user_uuid)
    for v in user_doc.get('_source').get('verificationTags'):
        assert v.get('tagUuid') in [str(tag_c.tag_uuid), str(tag_b.tag_uuid), str(tag_a.tag_uuid)]
    assert len(user_doc.get('_source').get('verificationTags')) == 3

    n = session.query(UserVerificationTag) \
        .filter(UserVerificationTag.user_uuid == user_uuid, UserVerificationTag.deleted_at.is_(None)) \
        .order_by(UserVerificationTag.created_at)
    assert n.count() == 3
    for resp in n.all():
        assert resp.tag_uuid in [tag_c.tag_uuid, tag_b.tag_uuid, tag_a.tag_uuid]

    response = client.post(f'/admin/v1/verification/tag', headers=headers, json={
        'moderator_uid': moderator_uid,
        "user_uids": [user_uid],
        "tag_uuids": [],
    })

    assert response.status_code == 200
    user_doc = es.get(index=user_index, id=user_uuid)
    assert user_doc.get('_source').get('verificationTags') is None
