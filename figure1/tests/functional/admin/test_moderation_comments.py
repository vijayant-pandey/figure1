from figure1.common.models.db import CommentReport
from figure1.common.models.db import User
from figure1.common.models.db import Comment

from figure1.common.types import CommentState
from figure1.common.types import CommentRejectionReason


def test_approve_comment(client, headers, load_db, test_reported_comment, test_user):
    session = load_db
    session.commit()
    c = test_reported_comment

    # Approving for invalid comment returns 404
    invalid_comment_uuid = '00000000-0000-0000-0000-000000000000'
    response = client.post(f'/admin/v1/moderation/comments/{invalid_comment_uuid}/approve', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response.status_code == 404

    # Approving for invalid user returns 404
    response = client.post(f'/admin/v1/moderation/comments/{c.comment_uuid}/approve', headers=headers, json={
        'moderator_uid': 'fake_user'
    })
    assert response.status_code == 404

    # Approving marks comment state as approved and updates c_comment_report
    response = client.post(f'/admin/v1/moderation/comments/{c.comment_uuid}/approve', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response.status_code == 200

    session.refresh(c)
    r = session.query(CommentReport).filter(CommentReport.comment_uuid == c.comment_uuid).one()
    assert c.state == CommentState.APPROVED
    assert r.moderator_approved is True
    assert r.moderator_reviewed is True
    assert str(r.moderator_uuid) == test_user.get('userUuid')


def test_reject_comment(client, headers, load_db, test_reported_comment, test_user):
    test_reported_comment.is_accepted_answer = True
    session = load_db
    session.commit()
    c = test_reported_comment

    # Rejecting for invalid comment returns 404
    invalid_comment_uuid = '00000000-0000-0000-0000-000000000000'
    response = client.post(f'/admin/v1/moderation/comments/{invalid_comment_uuid}/reject', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'reason': CommentRejectionReason.UNSUPPORTED.name
    })
    assert response.status_code == 404

    # Rejecting for invalid user returns 404
    response = client.post(f'/admin/v1/moderation/comments/{c.comment_uuid}/reject', headers=headers, json={
        'moderator_uid': 'fake_user',
        'reason': CommentRejectionReason.UNSUPPORTED.name
    })
    assert response.status_code == 404

    # Rejecting for invalid reason returns 400
    response = client.post(f'/admin/v1/moderation/comments/{c.comment_uuid}/reject', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'reason': 'invalid_reason'
    })
    assert response.status_code == 400

    # Rejecting marks comment state as rejected and updates c_comment_report
    response = client.post(f'/admin/v1/moderation/comments/{c.comment_uuid}/reject', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'reason': CommentRejectionReason.UNSUPPORTED.name
    })
    assert response.status_code == 200

    session.refresh(c)
    r = session.query(CommentReport).filter(CommentReport.comment_uuid == c.comment_uuid).one()
    assert c.state == CommentState.REJECTED
    assert c.rejection_reason == CommentRejectionReason.UNSUPPORTED
    assert r.moderator_approved is False
    assert r.moderator_reviewed is True
    # assert r.is_accepted_answer is False
    assert str(r.moderator_uuid) == test_user.get('userUuid')


def test_flag_comment(client, headers, load_db, test_comment, test_comment_pending_approval, test_user):
    session = load_db
    session.commit()
    c = test_comment
    u = session.query(User).get(test_user.get('userUuid'))
    u_dict = u.as_dict()
    # Flag for invalid comment returns 404
    invalid_comment_uuid = '00000000-0000-0000-0000-000000000000'
    response_1 = client.post(f'/admin/v1/moderation/comments/{invalid_comment_uuid}/flag', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response_1.status_code == 404

    # Flag for invalid user returns 404
    response_2 = client.post(f'/admin/v1/moderation/comments/{c.comment_uuid}/flag', headers=headers, json={
        'moderator_uid': 'fake_user'
    })
    assert response_2.status_code == 404

    # Flag marks comment state as flagged
    response_3 = client.post(f'/admin/v1/moderation/comments/{c.comment_uuid}/flag', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response_3.status_code == 200

    session.refresh(c)
    assert c.state == CommentState.FLAGGED

    # Flag for pending approval comment marks comment state as pending_approval_flagged
    c2 = test_comment_pending_approval
    response_4 = client.post(f'/admin/v1/moderation/comments/{c2.comment_uuid}/flag', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
    })
    assert response_4.status_code == 200

    session.refresh(c2)
    assert c2.state == CommentState.PENDING_APPROVAL_FLAGGED


def test_report_comment(client, headers, load_db, test_comment, test_user):
    session = load_db
    session.commit()
    c = test_comment

    # Report marks comment state as reported
    response = client.post(f'/pro/v1/comment/{c.comment_uuid}/report', headers=headers, json={
        'report_reason': 'OTHER',
        'reporting_user_uid': test_user.get('userUid'),
        'text': "this app is great 5 stars"
    })
    assert response.status_code == 200

    session.refresh(c)
    assert c.state == CommentState.REPORTED
    r = session.query(CommentReport).filter(CommentReport.comment_uuid == c.comment_uuid).one()
    assert r
    assert str(r.user_uuid) == test_user.get('userUuid')


def test_review_accepted_answer(client, headers, load_db, test_user, test_comment):
    session = load_db
    session.commit()

    c = test_comment
    assert c.moderator_reviewed is False

    # Only accepted answer can be reviewed
    response0 = client.post(f'/admin/v1/moderation/comments/review', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'comment_uuids': [str(c.comment_uuid)],
        'status': 'reviewed'
    })
    assert response0.status_code == 422

    c.is_accepted_answer = True
    session.add(c)
    session.commit()

    session.refresh(c)
    assert c.is_accepted_answer is True

    # status == reviewed
    response = client.post(f'/admin/v1/moderation/comments/review', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'comment_uuids': [str(c.comment_uuid)],
        'status': 'reviewed'
    })
    assert response.status_code == 200

    session.refresh(c)
    assert c.moderator_reviewed is True

    # status == pending_review
    response2 = client.post(f'/admin/v1/moderation/comments/review', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'comment_uuids': [str(c.comment_uuid)],
        'status': 'pending_review'
    })
    assert response2.status_code == 200

    session.refresh(c)
    assert c.moderator_reviewed is False

    # missing moderator uid
    response3 = client.post(f'/admin/v1/moderation/comments/review', headers=headers, json={
        'comment_uuids': [str(c.comment_uuid)],
        'status': 'pending_review'
    })
    assert response3.status_code == 422

    # missing comment_uuids
    response3 = client.post(f'/admin/v1/moderation/comments/review', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'status': 'pending_review'
    })
    assert response3.status_code == 422

    # missing status
    response4 = client.post(f'/admin/v1/moderation/comments/review', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'comment_uuids': [str(c.comment_uuid)],
    })
    assert response4.status_code == 422

    # invalid status
    response5 = client.post(f'/admin/v1/moderation/comments/review', headers=headers, json={
        'moderator_uid': test_user.get('userUid'),
        'comment_uuids': [str(c.comment_uuid)],
        'status': 'invalid status'
    })
    assert response5.status_code == 400
