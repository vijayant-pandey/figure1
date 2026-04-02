import os

from figure1.common.models.db import UserVerificationHistory
from figure1.common.types import VerificationStatus
from figure1.tools.verify import bulk_verify

DATABASE = os.path.join(os.path.dirname(__file__), './data')


def test_bulk_verify(test_user, test_user_pending_verification, load_db):
    session = load_db

    filename = os.path.join(os.path.dirname(__file__), 'bulk_verify_test.csv')
    with open(filename, 'x') as f:
        f.write(str(test_user_pending_verification.user_uuid))

    v = test_user_pending_verification.user_verification
    h = list(session.query(UserVerificationHistory)
             .filter(UserVerificationHistory.verification_record_uuid == v.verification_uuid)
             .all())
    assert v.verification_status != VerificationStatus.VERIFIED
    assert len(list(h)) == 1

    bulk_verify(filename=filename, moderator_uid=test_user.get('userUid'), session=session)

    session.refresh(v)
    assert v.verification_status == VerificationStatus.VERIFIED

    assert test_user_pending_verification.user_state.block_legacy_migration is True

    h = list(session.query(UserVerificationHistory)
             .filter(UserVerificationHistory.verification_record_uuid == v.verification_uuid)
             .all())
    assert len(h) > 1
    assert any([x for x in h if x.verification_status == 'VERIFIED'])
