from random import choice

from figure1.common.helpers import CaseManagement, GroupManagement
from figure1.common.models.db import Label
from figure1.common.types import CaseState
from figure1.common.types.groups import GroupTypes
from figure1.tests.utils.case import create_test_case


def test_is_case_cme(load_db, test_user):
    session = load_db
    author = test_user
    case, _ = create_test_case(
        author_uuid=author.get('userUuid'),
        is_paging_case=False,
        language='en',
        title="Default case",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)
    group = GroupManagement.create_group(group_name='test_group_1_' + ''.join(choice("abcdefghijk") for _ in range(10)),
                                         group_label='test_group_label_1',
                                         group_type=GroupTypes.USER,
                                         group_creator_uuid=author.get('userUuid'),
                                         session=session)
    Label.create_or_update(name="case_cme",
                           kind="case_cme",
                           is_public=True,
                           session=session)

    session.flush()
    # Given group_uuid is None, a case is case CME eligible if the case state is APPROVED
    CaseManagement.update_case_cme_label(case_uuid=case.case_uuid,
                                         case_state=case.state,
                                         group_uuid=case.group_uuid,
                                         session=session)
    assert case.is_case_cme is True

    # Given group_uuid is None, a case is not case CME eligible if the case state is not APPROVED.
    for each_state in CaseState.__members__:
        if each_state == 'APPROVED':
            continue
        case.state = CaseState[each_state]
        session.add(case)
        session.flush()
        CaseManagement.update_case_cme_label(case_uuid=case.case_uuid,
                                             case_state=case.state,
                                             group_uuid=case.group_uuid,
                                             session=session)
        session.refresh(case)
        assert case.is_case_cme is False

    # group case is not case CME eligible
    case.state = CaseState.APPROVED
    session.add(case)
    session.flush()
    CaseManagement.update_case_cme_label(case_uuid=case.case_uuid,
                                         case_state=case.state,
                                         group_uuid=case.group_uuid,
                                         session=session)
    session.refresh(case)
    assert case.is_case_cme is True

    case.group_uuid = group.groupUuid
    session.add(case)
    session.flush()
    CaseManagement.update_case_cme_label(case_uuid=case.case_uuid,
                                         case_state=case.state,
                                         group_uuid=case.group_uuid,
                                         session=session)
    session.refresh(case)
    assert case.is_case_cme is False

    GroupManagement.remove_user_from_group(user_uuid=author.get('userUuid'),
                                           group_uuid=group.groupUuid,
                                           session=session)
    GroupManagement.delete_group(group_uuid=group.groupUuid, session=session)
    session.flush()
