import time
from contextlib import contextmanager

import pytest

from figure1.admin.moderation.comments.domain import approve_comment
from figure1.admin.moderation.comments.domain import flag_comment
from figure1.common.base.trending import do_trend_update
from figure1.common.helpers import GroupManagement
from figure1.common.helpers import CommentSync
from figure1.common.models.db import CaseAnalytics
from figure1.common.models.db import Content
from figure1.common.models.db import Comment
from figure1.common.types import ReportReason, CommentState
from figure1.exceptions import CommentEditNotSupported
from figure1.exceptions import AcceptedAnswerError
from figure1.exceptions.user import InsufficientPermissions
from figure1.pro.cases.domain import get_case
from figure1.pro.comments.domain import do_post_comment
from figure1.pro.comments.domain import do_report_comment
from figure1.pro.comments.domain import do_delete_comment
from figure1.pro.comments.domain import do_edit_comment
from figure1.pro.comments.domain import add_or_remove_accepted_answer


def post_comment(user_uid, content_uuid, parent_uuid=None, text='test1'):
    c = do_post_comment(user_uid=user_uid,
                        content_uuid=content_uuid,
                        comment_text=text,
                        parent_comment_uuid=parent_uuid)
    return c


@contextmanager
def assert_no_raises(exception):
    try:
        yield
    except exception as e:
        raise AssertionError("It should not raise this Exception ", e)


def get_fs_doc(comment_uuid, session):
    comment_dict = CommentSync.generate_tree_branch(comment_uuid=comment_uuid, session=session)
    k = next(iter(comment_dict))
    return comment_dict[k]


def get_case_doc(case_uuid, fs):
    doc = fs.collection('casesDBv2') \
        .document(case_uuid).get()
    count = 0
    while not doc.exists:
        doc = fs.collection('casesDBv2') \
            .document(case_uuid).get()
        count += 1
        time.sleep(1)
        if count >= 10:
            raise TimeoutError("Timed out waiting for firestore")

    return doc.to_dict()


def test_post_comment(load_db, test_content, test_non_physician_user, test_physician_user, get_firestore_client):
    session = load_db
    case_uuid = test_content['caseUuid']
    physician = test_physician_user
    other = test_non_physician_user
    fs = get_firestore_client

    task = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    task.apply(timeout=10)

    get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)
    phys_comment = post_comment(user_uid=physician['userUid'], content_uuid=test_content['contentUuid'])
    parent_uuid = phys_comment['uuid']

    nonphys = post_comment(user_uid=other['userUid'], content_uuid=test_content['contentUuid'], parent_uuid=parent_uuid)

    doc = get_fs_doc(comment_uuid=parent_uuid, session=session)

    assert doc['isPhysician'] is True
    assert doc['text'] == 'test1'

    doc = get_fs_doc(comment_uuid=parent_uuid, session=session)

    parent_username = physician['username']
    assert nonphys['uuid'] in doc['children']
    assert doc['children'][nonphys['uuid']]['text'] == f'@{parent_username} test1'
    assert doc['children'][nonphys['uuid']]['isPhysician'] is False
    case_doc = get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)

    """
    Ensure comment count increments in parent case document
    """
    assert case_doc['commentCount'] >= 1

    """
    Ensure comment count on content item increments
    """
    assert 'contentItems' in case_doc
    test_comment_count = 0
    for i, c in enumerate(case_doc['contentItems']):
        assert case_doc['contentItems'][i].get('contentUuid') is not None
        if case_doc['contentItems'][i]['contentUuid'] == test_content['contentUuid']:
            fs_content_doc = case_doc['contentItems'][i]
            assert fs_content_doc.get('caption') == 'Case Caption'
            assert fs_content_doc.get('contentType') == 'content'
            test_comment_count = case_doc['contentItems'][i]['commentCount']

    assert test_comment_count >= 1

    """
    Trend score should be at least one for the comment just posted.
    """
    score = None
    for i in do_trend_update(session=session):
        if i.get("_id") == test_content.get('caseUuid'):
            score = i.get("doc").get("trendScore")
    #
    assert score > 0
    assert session.query(CaseAnalytics).get(test_content.get('caseUuid')).trend_score > 0


def test_post_anonymous_comment(load_db, approved_anonymous_case_and_content_and_user,
                                test_physician_user, get_firestore_client):
    session = load_db
    case, content, author = approved_anonymous_case_and_content_and_user
    case_uuid = case.case_uuid
    content_uuid = content.content_uuid
    author_uid = author.get('userUid')
    author_uuid = author.get('userUuid')
    fs = get_firestore_client

    task = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    task.apply(timeout=10)

    # The case author post a comment
    get_case_doc(case_uuid=str(case_uuid), fs=fs)
    author_comment = post_comment(user_uid=author_uid, content_uuid=content_uuid)
    doc = get_fs_doc(comment_uuid=author_comment['uuid'], session=session)
    assert doc['isAnonymous'] is True
    assert doc['text'] == 'test1'

    # The case comment count should include anonymous comments
    case_doc = get_case_doc(case_uuid=str(case_uuid), fs=fs)
    assert case_doc['commentCount'] == 1

    # The author comment count should not include anonymous comments
    author_comment_count = Comment.get_comment_count(user_uuid=author_uuid, include_anonymous=False)
    assert author_comment_count.get('approved_comment_count', None) == 0

    # The case author reply to the author_comment
    get_case_doc(case_uuid=str(case_uuid), fs=fs)
    author_reply = post_comment(user_uid=author_uid, content_uuid=content_uuid, parent_uuid=author_comment['uuid'],
                                text='author_reply')

    doc = get_fs_doc(comment_uuid=author_comment['uuid'], session=session)

    child = doc['children'][author_reply['uuid']]

    assert child['isAnonymous'] is True
    assert child['text'] == 'author_reply'
    assert not child.get('authorUuid')
    assert not child.get('username')
    assert not child.get('avatar')
    assert not child['author'].get('displayname')
    assert not child['author'].get('avatar')
    assert not child['author'].get('username')
    assert not child['author'].get('userUid')
    assert not child['author'].get('userUuid')
    assert not child['author'].get('profileLink')
    assert not child['author'].get('profileLinkText')
    assert not child['author'].get('userType')
    assert not child['author'].get('countryUuid')
    assert not child['author'].get('stateUuid')
    assert not child['author'].get('isPartner')
    assert not child['author'].get('legacyAccount')

    # A random user reply to the author_comment
    get_case_doc(case_uuid=str(case_uuid), fs=fs)
    random_user_dict = test_physician_user
    random_user_comment = post_comment(user_uid=random_user_dict['userUid'], content_uuid=content_uuid,
                                       parent_uuid=author_comment['uuid'], text='random_user_comment')
    doc = get_fs_doc(comment_uuid=author_comment['uuid'], session=session)

    child = doc['children'][random_user_comment['uuid']]

    assert child['isAnonymous'] is False
    assert child['text'] == 'random_user_comment'

    # The case author reply to the random_user_comment
    random_user_comment2 = post_comment(user_uid=random_user_dict['userUid'], content_uuid=content_uuid,
                                        text='random_user_comment2')
    author_reply2 = post_comment(user_uid=author_uid, content_uuid=content_uuid,
                                 parent_uuid=random_user_comment2['uuid'], text='author_reply2')

    doc = get_fs_doc(comment_uuid=random_user_comment2['uuid'], session=session)

    child = doc['children'][author_reply2['uuid']]

    assert child['isAnonymous'] is True
    assert child['text'] == '@' + random_user_dict['username'] + ' author_reply2'
    assert not child.get('authorUuid')
    assert not child.get('username')
    assert not child.get('avatar')
    assert not child['author'].get('displayname')
    assert not child['author'].get('avatar')
    assert not child['author'].get('username')
    assert not child['author'].get('userUid')
    assert not child['author'].get('userUuid')
    assert not child['author'].get('profileLink')
    assert not child['author'].get('profileLinkText')
    assert not child['author'].get('userType')
    assert not child['author'].get('countryUuid')
    assert not child['author'].get('stateUuid')
    assert not child['author'].get('isPartner')
    assert not child['author'].get('legacyAccount')


def test_post_comment_to_group_case_content(load_db, test_content_obj, test_group_case, test_physician_user):
    session = load_db
    user_dict = test_physician_user
    content = test_content_obj
    group_case, _ = test_group_case
    old_content_case_uuid = content.case_uuid
    content.case_uuid = group_case.case_uuid
    session.commit()

    # user can not post comment to a group case content without sufficient permissions.
    with pytest.raises(InsufficientPermissions):
        comment = post_comment(user_uid=user_dict['userUid'], content_uuid=content.content_uuid)

    GroupManagement.add_user_to_group(user_uuid=user_dict['userUuid'],
                                      group_uuid=group_case.group_uuid,
                                      session=session)
    session.commit()

    # user can post comment to a group case content with sufficient permissions.
    with assert_no_raises(InsufficientPermissions):
        comment = post_comment(user_uid=user_dict['userUid'], content_uuid=content.content_uuid)

    content.case_uuid = old_content_case_uuid
    GroupManagement.remove_user_from_group(user_uuid=user_dict['userUuid'],
                                           group_uuid=group_case.group_uuid,
                                           session=session)
    session.commit()


def test_edit_comment(load_db, test_content, test_physician_user, test_non_physician_user, get_firestore_client):
    session = load_db
    case_uuid = test_content['caseUuid']
    comment_author = test_physician_user
    other_user = test_non_physician_user
    fs = get_firestore_client

    task = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    task.apply(timeout=10)

    get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)
    comment = post_comment(user_uid=comment_author['userUid'], content_uuid=test_content['contentUuid'])
    comment_uuid = comment['uuid']

    doc = get_fs_doc(comment_uuid=comment_uuid, session=session)

    session.commit()
    assert doc['text'] == 'test1'
    assert doc['edited'] is False

    """
    Ensure non-author cannot edit
    """
    with pytest.raises(CommentEditNotSupported):
        do_edit_comment(user_uid=other_user['userUid'],
                        comment_uuid=comment_uuid,
                        comment_text="Updated comment for another user")

    """
    Ensure valid comment edit is successful
    """
    do_edit_comment(user_uid=comment_author['userUid'],
                    comment_uuid=comment_uuid,
                    comment_text="Updated comment text")

    doc = get_fs_doc(comment_uuid=comment_uuid, session=session)

    c = session.query(Comment).get(comment_uuid)
    assert c.text == "Updated comment text"
    assert c.edited is True
    assert doc['text'] == 'Updated comment text'
    assert doc['edited'] is True

    """
    Ensure non-approved comments cannot be edited
    """
    do_report_comment(reporting_user_uid=other_user['userUid'],
                      report_reason=ReportReason.PRIVACY,
                      text=None,
                      comment_uuid=comment_uuid,
                      session=session)
    session.commit()
    with pytest.raises(CommentEditNotSupported):
        do_edit_comment(user_uid=comment_author['userUid'],
                        comment_uuid=comment_uuid,
                        comment_text="Update reported comment")

    """
    Ensure accepted answers cannot be edited
    """
    accepted_answer = post_comment(user_uid=comment_author['userUid'], content_uuid=test_content['contentUuid'])
    accepted_answer_uuid = accepted_answer['uuid']
    add_or_remove_accepted_answer(is_accepted_answer=True,
                                  comment_uuid=accepted_answer_uuid,
                                  user_uid=comment_author['userUid'])
    with pytest.raises(CommentEditNotSupported):
        do_edit_comment(user_uid=comment_author['userUid'],
                        comment_uuid=accepted_answer_uuid,
                        comment_text="Update accepted answer")
    add_or_remove_accepted_answer(is_accepted_answer=False,
                                  comment_uuid=accepted_answer_uuid,
                                  user_uid=comment_author['userUid'])


def test_edit_group_case_comment(load_db, test_content_obj, test_physician_user, test_group_case):
    session = load_db
    user_dict = test_physician_user
    content = test_content_obj
    group_case, _ = test_group_case
    old_content_case_uuid = content.case_uuid
    content.case_uuid = group_case.case_uuid
    session.commit()

    GroupManagement.add_user_to_group(user_uuid=user_dict['userUuid'],
                                      group_uuid=group_case.group_uuid,
                                      session=session)
    session.commit()

    result = post_comment(user_uid=user_dict['userUid'], content_uuid=content.content_uuid)

    comment_uuid = result['uuid']
    # user can edit comment with sufficient permissions.
    with assert_no_raises(InsufficientPermissions):
        do_edit_comment(user_uid=user_dict['userUid'],
                        comment_uuid=comment_uuid,
                        comment_text="Update reported comment")

    # user can not edit comment without sufficient permissions.
    GroupManagement.remove_user_from_group(user_uuid=user_dict['userUuid'],
                                           group_uuid=group_case.group_uuid,
                                           session=session)
    session.commit()

    with pytest.raises(InsufficientPermissions):
        do_edit_comment(user_uid=user_dict['userUid'],
                        comment_uuid=comment_uuid,
                        comment_text="Update reported comment")

    content.case_uuid = old_content_case_uuid
    session.commit()


def test_delete_comment(load_db, test_content, test_user, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    case_uuid = test_content['caseUuid']

    task = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    task.apply(timeout=10)
    get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)

    c1 = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])

    c2 = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])
    add_or_remove_accepted_answer(is_accepted_answer=True,
                                  comment_uuid=c2['uuid'],
                                  user_uid=test_user['userUid'])

    db_count = session.query(Content).get(test_content.get('contentUuid'))
    first_db_count = db_count.approved_comments_count
    assert first_db_count >= 2

    do_delete_comment(comment_uuid=c2['uuid'])
    session.refresh(db_count)
    assert db_count.approved_comments_count == first_db_count - 1
    comment2 = session.query(Comment).get(c2['uuid'])
    assert comment2.replyable is False
    assert comment2.state is CommentState.DELETED
    assert comment2.is_accepted_answer is False

    doc2 = get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)
    second_count = doc2.get('commentCount')
    assert 'acceptedAnswer' not in doc2
    assert second_count + 1 == first_db_count


def test_report_comment(load_db, test_content, test_user, get_firestore_client):
    session = load_db
    c = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])
    fs = get_firestore_client
    doc = get_fs_doc(comment_uuid=c['uuid'], session=session)
    assert doc['replyable'] is True
    rep = do_report_comment(reporting_user_uid=test_user['userUid'],
                            report_reason=ReportReason.PRIVACY,
                            text=None,
                            comment_uuid=c['uuid'],
                            session=session)
    assert 'success' in rep
    count = 0
    while doc['replyable'] is True:
        doc = get_fs_doc(comment_uuid=c['uuid'], session=session)
        count += 1
        time.sleep(5)
        if count >= 10:
            raise TimeoutError("Timed out waiting for firestore")
    assert doc['isReported'] is True
    assert doc['replyable'] is False


def test_report_group_case_comment(load_db, test_content_obj, test_physician_user, test_group_case):
    session = load_db
    user_dict = test_physician_user
    content = test_content_obj
    group_case, _ = test_group_case
    old_content_case_uuid = content.case_uuid
    content.case_uuid = group_case.case_uuid
    session.commit()

    GroupManagement.add_user_to_group(user_uuid=user_dict['userUuid'],
                                      group_uuid=group_case.group_uuid,
                                      session=session)
    session.commit()

    comment = post_comment(user_uid=user_dict['userUid'], content_uuid=content.content_uuid)

    # user can report comment with sufficient permissions.
    with assert_no_raises(InsufficientPermissions):
        result = do_report_comment(reporting_user_uid=user_dict['userUid'],
                                   report_reason=ReportReason.PRIVACY,
                                   text=None,
                                   comment_uuid=comment['uuid'],
                                   session=session)
    assert 'success' in result

    # user can not report comment without sufficient permissions.
    GroupManagement.remove_user_from_group(user_uuid=user_dict['userUuid'],
                                           group_uuid=group_case.group_uuid,
                                           session=session)
    session.commit()

    with pytest.raises(InsufficientPermissions):
        result = do_report_comment(reporting_user_uid=user_dict['userUid'],
                                   report_reason=ReportReason.PRIVACY,
                                   text=None,
                                   comment_uuid=comment['uuid'],
                                   session=session)

    content.case_uuid = old_content_case_uuid
    session.commit()


def test_accepted_answer(load_db, test_content, test_user, get_firestore_client):
    session = load_db
    fs = get_firestore_client

    c = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])
    c2 = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])
    c3 = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])

    comment_uuid = c['uuid']
    comment_uuid2 = c2['uuid']
    comment_uuid3 = c3['uuid']

    comment = session.query(Comment).get(comment_uuid)
    assert comment.is_accepted_answer is False

    comment2 = session.query(Comment).get(comment_uuid2)
    assert comment2.is_accepted_answer is False

    comment3 = session.query(Comment).get(comment_uuid3)
    assert comment3.is_accepted_answer is False

    # Ensure accepted answer can be set
    add_or_remove_accepted_answer(is_accepted_answer=True,
                                  comment_uuid=comment_uuid,
                                  user_uid=test_user['userUid'])

    session.refresh(comment)
    assert comment.is_accepted_answer
    comment_doc = get_fs_doc(comment_uuid=comment_uuid, session=session)
    case_doc = get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)
    assert comment_doc['isAcceptedAnswer'] is True
    assert case_doc['acceptedAnswer'] is not None
    assert case_doc['acceptedAnswer']['commentUuid'] == comment_uuid

    # Ensure accepted answer can be unset
    add_or_remove_accepted_answer(is_accepted_answer=False,
                                  comment_uuid=comment_uuid,
                                  user_uid=test_user['userUid'])

    session.refresh(comment)
    assert comment.is_accepted_answer is False
    comment_doc = get_fs_doc(comment_uuid=comment_uuid, session=session)
    case_doc = get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)
    assert comment_doc['isAcceptedAnswer'] is False
    assert 'acceptedAnswer' not in case_doc

    # Ensure accepted answer can be replaced.
    add_or_remove_accepted_answer(is_accepted_answer=True,
                                  comment_uuid=comment_uuid2,
                                  user_uid=test_user['userUid'])

    session.refresh(comment2)
    assert comment2.is_accepted_answer is True
    comment_doc = get_fs_doc(comment_uuid=comment_uuid2, session=session)
    case_doc = get_case_doc(case_uuid=test_content.get('caseUuid'), fs=fs)
    assert comment_doc['isAcceptedAnswer'] is True
    assert case_doc['acceptedAnswer'] is not None
    assert case_doc['acceptedAnswer']['commentUuid'] == comment_uuid2

    # Only comments that are in the APPROVED state are selectable as accepted answers.
    rep = do_report_comment(reporting_user_uid=test_user['userUid'],
                            report_reason=ReportReason.PRIVACY,
                            text=None,
                            comment_uuid=comment_uuid,
                            session=session)
    session.commit()
    with pytest.raises(AcceptedAnswerError):
        res = add_or_remove_accepted_answer(is_accepted_answer=True,
                                            comment_uuid=comment_uuid,
                                            user_uid=test_user['userUid'])

    # The case author does not have the option to remove their selected comment/reply
    # as the accepted answer while waiting for moderation review
    flag_comment(comment_uuid=comment_uuid2,
                 moderator_uid=test_user['userUid'],
                 session=session)
    session.commit()
    session.refresh(comment2)

    assert comment2.state is CommentState.FLAGGED
    with pytest.raises(AcceptedAnswerError):
        res = add_or_remove_accepted_answer(is_accepted_answer=False,
                                            comment_uuid=comment_uuid2,
                                            user_uid=test_user['userUid'])
    session.refresh(comment2)
    assert comment2.is_accepted_answer is True

    # The case author does not have the option to add a new accepted answer while waiting for moderation review
    with pytest.raises(AcceptedAnswerError):
        res = add_or_remove_accepted_answer(is_accepted_answer=True,
                                            comment_uuid=comment_uuid3,
                                            user_uid=test_user['userUid'])
    session.refresh(comment2)
    assert comment2.is_accepted_answer is True
    assert comment3.is_accepted_answer is False

    do_delete_comment(comment_uuid2, session=session)


def test_post_queued_comment(load_db, test_case_comment_queue, test_user, get_firestore_client):
    case = test_case_comment_queue
    case_uuid = str(case.case_uuid)
    content = case.content[0]

    fs = get_firestore_client

    comment = post_comment(user_uid=test_user['userUid'], content_uuid=content.content_uuid)

    task = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    task.apply(timeout=10)
    case_doc = get_case_doc(case_uuid=case_uuid, fs=fs)

    """
    Ensure comment is not posted immediately
    """
    assert case_doc['commentCount'] == 0
    assert 'contentItems' in case_doc
    for i, c in enumerate(case_doc['contentItems']):
        assert case_doc['contentItems'][i].get('contentUuid') is not None
        if case_doc['contentItems'][i]['contentUuid'] == str(content.content_uuid):
            fs_content_doc = case_doc['contentItems'][i]
            assert fs_content_doc.get('caption') == 'Case Caption'
            assert fs_content_doc.get('contentType') == 'content'
            assert case_doc['contentItems'][i]['commentCount'] == 0

    """
    Ensure comment is added after approval
    """
    approve_comment(comment_uuid=comment['uuid'],
                    moderator_uid=test_user['userUid'])

    task = get_case(case_uuid=case_uuid, return_task=True).pop('task')
    task.apply(timeout=10)
    case_doc = get_case_doc(case_uuid=case_uuid, fs=fs)

    assert case_doc['commentCount'] == 1
    assert 'contentItems' in case_doc
    for i, c in enumerate(case_doc['contentItems']):
        assert case_doc['contentItems'][i].get('contentUuid') is not None
        if case_doc['contentItems'][i]['contentUuid'] == str(content.content_uuid):
            fs_content_doc = case_doc['contentItems'][i]
            assert fs_content_doc.get('caption') == 'Case Caption'
            assert fs_content_doc.get('contentType') == 'content'
            assert case_doc['contentItems'][i]['commentCount'] == 1


def test_report_comment_chain(load_db,
                              test_content,
                              test_user,
                              get_firestore_client):
    """
    Ensure that when multiple comments reply to a single unapproved comment, all have the reply-to username removed
    :param load_db:
    :param test_content:
    :param test_user:
    :param get_firestore_client:
    :return:
    """
    top_comment = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])

    reply_1 = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'],
                           parent_uuid=top_comment['uuid'])

    reply_2 = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'],
                           parent_uuid=top_comment['uuid'])

    comment_doc = get_fs_doc(comment_uuid=top_comment['uuid'], session=load_db)

    assert f'@{test_user.get("username")}' in comment_doc['children'][reply_1['uuid']]['text']
    assert f'@{test_user.get("username")}' in comment_doc['children'][reply_2['uuid']]['text']

    rep = do_report_comment(reporting_user_uid=test_user['userUid'],
                            report_reason=ReportReason.PRIVACY,
                            text=None,
                            comment_uuid=top_comment['uuid'])

    top_reported = get_fs_doc(comment_uuid=top_comment['uuid'], session=load_db)

    assert top_reported['children'][reply_1['uuid']]['text'] == 'test1'
    assert top_reported['children'][reply_2['uuid']]['text'] == 'test1'
    assert top_reported.get('commentState') == 'reported'
    assert top_reported.get('isReported') is True


def test_accepted_answer_endpoint(client, headers, test_content, test_user, load_db):
    comment = post_comment(user_uid=test_user['userUid'], content_uuid=test_content['contentUuid'])
    comment_uuid = comment['uuid']

    # is_accepted_answer = true
    response = client.post(f'/pro/v1/comment/{comment_uuid}/accepted_answer',
                           headers=headers,
                           json={'is_accepted_answer': True,
                                 'user_uid': test_user['userUid']})
    assert response.status_code == 200

    # is_accepted_answer = false
    response = client.post(f'/pro/v1/comment/{comment_uuid}/accepted_answer',
                           headers=headers,
                           json={'is_accepted_answer': False,
                                 'user_uid': test_user['userUid']})
    assert response.status_code == 200
