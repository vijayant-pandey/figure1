import uuid

from figure1.common.models.db import Media, Case
from figure1.common.types import MediaType, CaseState
from figure1.tests.utils.case import create_test_case


def _add_content__media_to_case(content_uuid, session):
    media = Media()
    media.media_uuid = uuid.uuid4()
    media.content_uuid = content_uuid
    media.type = MediaType.IMAGE
    media.filename = "filename"

    session.add(media)
    session.commit()


def test_case_clone(load_db, test_user):
    session = load_db
    user = test_user
    case, content = create_test_case(
        author_uuid=user.get('userUuid'),
        is_paging_case=False,
        language='en',
        title="Default case",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)

    old_case_uuid = case.case_uuid
    _add_content__media_to_case(content.content_uuid, session)

    assert case.content is not None
    assert len(case.content) == 1
    assert len(case.content[0].media) == 1
    new_case = case.clone(session)
    session.commit()

    old_case = session.query(Case).filter(Case.case_uuid == old_case_uuid).one()

    assert old_case_uuid != new_case.case_uuid
    assert old_case.group_uuid == new_case.group_uuid
    assert old_case.state == new_case.state
    assert old_case.published_at == new_case.published_at
    assert old_case.is_paging_case == new_case.is_paging_case
    assert old_case.rejection_reason == new_case.rejection_reason
    assert old_case.case_type == new_case.case_type
    assert old_case.cme1_credits == new_case.cme1_credits
    assert old_case.passing_score == new_case.passing_score
    assert old_case.synced_at == new_case.synced_at
    assert old_case.language == new_case.language

    assert len(new_case.content) == 1
    assert len(new_case.content[0].media) == 1

    for old_case_content, new_case_content in zip(old_case.content, new_case.content):
        assert new_case.case_uuid == new_case_content.case_uuid
        assert old_case_content.sponsored_content_uuid == new_case_content.sponsored_content_uuid
        assert old_case_content.extension_uuid == new_case_content.extension_uuid
        assert old_case_content.features_uuid == new_case_content.features_uuid
        assert old_case_content.display_order == new_case_content.display_order
        assert old_case_content.content_type == new_case_content.content_type
        assert old_case_content.title == new_case_content.title
        assert old_case_content.caption == new_case_content.caption
        assert old_case_content.is_feed_card == new_case_content.is_feed_card
        assert old_case_content.feed_card_type == new_case_content.feed_card_type
        assert old_case_content.section == new_case_content.section

    for old_case_media, new_case_media in zip(old_case.content[0].media, new_case.content[0].media):
        assert new_case.case_uuid == new_case_media.case_uuid
        assert old_case_media.type == new_case_media.type
        assert old_case_media.legacy_id == new_case_media.legacy_id
        assert old_case_media.filename == new_case_media.filename
        assert old_case_media.display_order == new_case_media.display_order
        assert old_case_media.width == new_case_media.width
        assert old_case_media.height == new_case_media.height
        assert old_case_media.original_filename == new_case_media.original_filename
        assert old_case_media.is_feed_card_media == new_case_media.is_feed_card_media
        assert old_case_media.video_url == new_case_media.video_url
        assert old_case_media.video_url_generated_at == new_case_media.video_url_generated_at
        assert old_case_media.filename_exists == new_case_media.filename_exists
        assert old_case_media.original_filename_exists == new_case_media.original_filename_exists
        assert old_case_media.checked_at == new_case_media.checked_at
