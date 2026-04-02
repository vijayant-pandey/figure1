import uuid

from figure1.common.models.db import Case, QuestionOption, CampaignCase, CampaignPreviewUser, \
    MediaType, Campaign
from figure1.common.types import CaseState, ContentType, Locale, CampaignState, FeedCardType, \
    CaseType, ContentSection

from figure1.configuration import es_settings
from figure1.common.helpers.promo_card import PromoCardDetail
from figure1.admin.campaign.case.tasks import populate_template

from figure1.common.types.elasticsearch import ESCaseModel


def _get_fs_doc(fs, user_uid):
    def get_doc():
        return fs.collection('userFeedDB') \
            .document(user_uid).get()

    doc = get_doc()
    return doc.to_dict()


def test_static(client, headers, load_db, test_user, test_campaign):
    session = load_db
    moderator_uid = test_user.get('userUid')
    # Create Static Case
    response = client.post(f'/admin/v1/case/static', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Sample caption",
        "title": "Sample title",
        "media": [
            {"filename": "1.png", "height": 1080, "type": "image", "width": 1920}
        ],
        "external_link": {
            "external_link_url": "https://www.figure1.com",
            "external_link_text": "Learn more"
        },
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "feed_card": {
            "feed_card_type": "highlight",
            "feed_card_label": "Label",
            "feed_card_title": "Title",
            "button_text": "Start Activity",
            "colour": "236B84"
        },
        "isi": {
            "isi_embedded_content_link": "https://www.figure1.com",
            "isi_link": "https://www.figure1.com",
            "isi_text": "Full Prescribing Information, including Boxed WARNING"
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": "123",
            "sponsored_text": "Sponsored Content"
        }
    })
    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')
    content_uuid = response.json.get('content_uuid')

    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_DRAFT
    assert c.is_paging_case is False
    assert c.case_type == CaseType.STATIC
    assert len(c.authors) == 1
    assert str(c.authors[0].user_uuid) == test_user.get('userUuid')
    assert len(c.content) == 1
    assert str(c.content[0].content_uuid) == content_uuid
    assert c.content[0].content_type == ContentType.CONTENT
    assert c.content[0].is_feed_card is True
    assert c.content[0].caption == "Sample caption"
    assert c.content[0].title == "Sample title"
    assert c.content[0].feed_card_type == FeedCardType.HIGHLIGHT
    assert c.content[0].extension.external_link_text == "Learn more"
    assert c.content[0].extension.external_link_url == "https://www.figure1.com"
    assert c.content[0].extension.isi_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_embedded_content_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_text == "Full Prescribing Information, including Boxed WARNING"
    assert c.content[0].extension.feed_card_label == "Label"
    assert c.content[0].extension.feed_card_title == "Title"
    assert c.content[0].extension.colour == "236B84"
    assert c.content[0].extension.button_text == "Start Activity"
    assert c.content[0].features.comment_queue_enabled is False
    assert c.content[0].features.comments_enabled is True
    assert c.content[0].features.reactions_enabled is True
    assert c.content[0].features.save_enabled is True
    assert c.content[0].features.share_enabled is True
    assert c.content[0].features.zoom_enabled is True
    assert c.content[0].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[0].sponsored_content.job_code == "123"
    assert c.content[0].sponsored_content.sponsored_text == "Sponsored Content"
    assert len(c.content[0].media) == 1
    assert c.content[0].media[0].filename == "1.png"
    assert c.content[0].media[0].height == 1080
    assert c.content[0].media[0].width == 1920
    assert c.content[0].media[0].type == MediaType.IMAGE
    assert c.content[0].media[0].display_order == 0

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Tactic"
    assert cc[0].tactic_priority == 1


def test_quiz_and_case_updates(client, headers, load_db, test_user, test_campaign):
    session = load_db
    moderator_uid = test_user.get('userUid')
    # Create Quiz
    response = client.post(f'/admin/v1/case/quiz', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Quiz caption",
        "title": "Quiz title",
        "media": [
            {"filename": "1.png", "height": 1080, "type": "image", "width": 1920}
        ],
        "question_answer_details": "Details here",
        "question_options": [
            {"is_answer": True, "text": "Option A"},
            {"is_answer": False, "text": "Option B"},
            {"is_answer": False, "text": "Option C"}
        ],
        "external_link": {
            "external_link_url": "https://www.figure1.com",
            "external_link_text": "Learn more"
        },
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "feed_card": {
            "feed_card_type": "highlight",
            "feed_card_label": "Label",
            "feed_card_title": "Title",
            "button_text": "Start Activity",
            "colour": "236B84"
        },
        "isi": {
            "isi_embedded_content_link": "https://www.figure1.com",
            "isi_link": "https://www.figure1.com",
            "isi_text": "Full Prescribing Information, including Boxed WARNING"
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": "123",
            "sponsored_text": "Sponsored Content"
        }
    })
    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')
    content_uuid = response.json.get('content_uuid')

    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_DRAFT
    assert c.is_paging_case is False
    assert c.case_type == CaseType.QUIZ
    assert len(c.authors) == 1
    assert str(c.authors[0].user_uuid) == test_user.get('userUuid')
    assert len(c.content) == 1
    assert str(c.content[0].content_uuid) == content_uuid
    assert c.content[0].content_type == ContentType.QUIZ
    assert c.content[0].is_feed_card is True
    assert c.content[0].caption == "Quiz caption"
    assert c.content[0].title == "Quiz title"
    assert c.content[0].feed_card_type == FeedCardType.HIGHLIGHT
    assert c.content[0].extension.question_answer_details == "Details here"
    assert c.content[0].extension.external_link_text == "Learn more"
    assert c.content[0].extension.external_link_url == "https://www.figure1.com"
    assert c.content[0].extension.isi_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_embedded_content_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_text == "Full Prescribing Information, including Boxed WARNING"
    assert c.content[0].extension.feed_card_label == "Label"
    assert c.content[0].extension.feed_card_title == "Title"
    assert c.content[0].extension.colour == "236B84"
    assert c.content[0].extension.button_text == "Start Activity"
    assert c.content[0].features.comment_queue_enabled is False
    assert c.content[0].features.comments_enabled is True
    assert c.content[0].features.reactions_enabled is True
    assert c.content[0].features.save_enabled is True
    assert c.content[0].features.share_enabled is True
    assert c.content[0].features.zoom_enabled is True
    assert c.content[0].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[0].sponsored_content.job_code == "123"
    assert c.content[0].sponsored_content.sponsored_text == "Sponsored Content"
    assert len(c.content[0].media) == 1
    assert c.content[0].media[0].filename == "1.png"
    assert c.content[0].media[0].height == 1080
    assert c.content[0].media[0].width == 1920
    assert c.content[0].media[0].type == MediaType.IMAGE
    assert c.content[0].media[0].display_order == 0

    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuid)
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 3
    assert qo[0].text == "Option A"
    assert qo[0].is_answer is True
    assert qo[0].display_order == 0
    assert qo[1].text == "Option B"
    assert qo[1].is_answer is False
    assert qo[1].display_order == 1
    assert qo[2].text == "Option C"
    assert qo[2].is_answer is False
    assert qo[2].display_order == 2

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Tactic"
    assert cc[0].tactic_priority == 1

    # Update Quiz - question options unchanged
    response = client.put(f'/admin/v1/case/quiz/{case_uuid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Quiz caption updated",
        "title": "Quiz title updated",
        "media": [
            {"filename": "1.png", "height": 1080, "type": "image", "width": 1920},
            {"filename": "2.png", "height": 1080, "type": "image", "width": 1920},
        ],
        "question_answer_details": "Details updated",
        "question_options": [
            {"is_answer": True, "text": "Option A"},
            {"is_answer": False, "text": "Option B"},
            {"is_answer": False, "text": "Option C"}
        ],
        "external_link": {
            "external_link_url": "https://www.figure1.com/update",
            "external_link_text": "Learn more updated"
        },
        "features": {
            "comment_queue_enabled": True,
            "comments_enabled": False,
            "reactions_enabled": False,
            "save_enabled": False,
            "share_enabled": False,
            "zoom_enabled": False
        },
        "feed_card": {
            "feed_card_type": "highlight",
            "feed_card_label": "Label",
            "feed_card_title": "Title",
            "button_text": "Start Activity",
            "colour": "236B84"
        },
        "isi": {
            "isi_embedded_content_link": None,
            "isi_link": None,
            "isi_text": None
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "sponsored_content": {
            "disclosure_text": "Updated text",
            "job_code": "ABC",
            "sponsored_text": "Sponsored Content Updated"
        },
    })
    assert response.status_code == 200
    session.expire_all()

    assert c.content[0].caption == "Quiz caption updated"
    assert c.content[0].title == "Quiz title updated"
    assert c.content[0].extension.question_answer_details == "Details updated"
    assert c.content[0].extension.external_link_text == "Learn more updated"
    assert c.content[0].extension.external_link_url == "https://www.figure1.com/update"
    assert c.content[0].extension.isi_link is None
    assert c.content[0].extension.isi_embedded_content_link is None
    assert c.content[0].extension.isi_text is None
    assert c.content[0].features.comment_queue_enabled is True
    assert c.content[0].features.comments_enabled is False
    assert c.content[0].features.reactions_enabled is False
    assert c.content[0].features.save_enabled is False
    assert c.content[0].features.share_enabled is False
    assert c.content[0].features.zoom_enabled is False
    assert c.content[0].sponsored_content.disclosure_text == "Updated text"
    assert c.content[0].sponsored_content.job_code == "ABC"
    assert c.content[0].sponsored_content.sponsored_text == "Sponsored Content Updated"
    assert len(c.content[0].media) == 2
    assert c.content[0].media[0].filename == "1.png"
    assert c.content[0].media[0].height == 1080
    assert c.content[0].media[0].width == 1920
    assert c.content[0].media[0].type == MediaType.IMAGE
    assert c.content[0].media[0].display_order == 0
    assert c.content[0].media[1].filename == "2.png"
    assert c.content[0].media[1].height == 1080
    assert c.content[0].media[1].width == 1920
    assert c.content[0].media[1].type == MediaType.IMAGE
    assert c.content[0].media[1].display_order == 1

    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuid)
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 3
    assert qo[0].text == "Option A"
    assert qo[0].is_answer is True
    assert qo[0].display_order == 0
    assert qo[1].text == "Option B"
    assert qo[1].is_answer is False
    assert qo[1].display_order == 1
    assert qo[2].text == "Option C"
    assert qo[2].is_answer is False
    assert qo[2].display_order == 2


def test_quiz_series(client, headers, load_db, test_user, test_campaign, get_elasticsearch_client):
    session = load_db
    es = get_elasticsearch_client

    moderator_uid = test_user.get('userUid')
    # Create Quiz
    response = client.post(f'/admin/v1/case/quiz_series', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "heading": "Overarching quiz series banner",
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "feed_card": {
            "feed_card_type": "highlight",
            "feed_card_label": "Label",
            "feed_card_title": "Title",
            "button_text": "Start Activity",
            "colour": "236B84",
            "feed_card_media": {"filename": "feedcard.png", "height": 1080, "type": "image", "width": 1920}
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": 123,
            "sponsored_text": "Sponsored Content"
        },
        "questions": [
            {
                "caption": "This is the first question",
                "title": "Question 1",
                "external_link": {
                    "external_link_text": "Learn more",
                    "external_link_url": "https://www.figure1.com"
                },
                "isi": {
                    "isi_embedded_content_link": "https://www.figure1.com",
                    "isi_link": "https://www.figure1.com",
                    "isi_text": "Full Prescribing Information, including Boxed WARNING"
                },
                "media": [
                    {"filename": "1.png", "height": 1080, "type": "image", "width": 1920}
                ],
                "question_answer_details": "First question answer details",
                "question_options": [
                    {"is_answer": True, "text": "Q1 Option A"},
                    {"is_answer": False, "text": "Q1 Option B"},
                    {"is_answer": False, "text": "Q1 Option C"}
                ]
            },
            {
                "caption": "This is the second question",
                "title": "Question 2",
                "media": [
                    {"filename": "2.png", "height": 1080, "type": "image", "width": 1920}
                ],
                "question_answer_details": "Second question answer details",
                "question_options": [
                    {"is_answer": False, "text": "Q2 Option A"},
                    {"is_answer": True, "text": "Q2 Option B"}
                ]
            }
        ],
        "conclusion": {
            "caption": "This is the end of the quiz series",
            "external_link": {
                "external_link_text": "Learn more",
                "external_link_url": "https://www.figure1.com"
            },
            "isi": {
                "isi_embedded_content_link": "https://www.figure1.com",
                "isi_link": "https://www.figure1.com",
                "isi_text": "Full Prescribing Information, including Boxed WARNING"
            },
        }
    })
    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')
    content_uuids = response.json.get('content_uuids')

    es_doc = es.get(index=es_settings.cases_alias, id=case_uuid)
    es_c: ESCaseModel = ESCaseModel.parse_obj(es_doc.get("_source"))

    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_DRAFT
    assert c.is_paging_case is False
    assert c.case_type == CaseType.QUIZ_SERIES
    assert len(c.authors) == 1
    assert str(c.authors[0].user_uuid) == test_user.get('userUuid')
    assert len(c.content) == 3

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Tactic"
    assert cc[0].tactic_priority == 1
    # Content 1
    assert str(c.content[0].content_uuid) == content_uuids[0]
    assert c.content[0].content_type == ContentType.QUIZ_SERIES
    assert c.content[0].is_feed_card is True
    assert c.content[0].caption == "This is the first question"
    assert c.content[0].title == "Question 1"
    assert c.content[0].feed_card_type == FeedCardType.HIGHLIGHT
    assert c.content[0].extension.question_answer_details == "First question answer details"
    assert c.content[0].extension.external_link_text == "Learn more"
    assert c.content[0].extension.external_link_url == "https://www.figure1.com"
    assert c.content[0].extension.heading == "Overarching quiz series banner"
    assert c.content[0].extension.isi_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_embedded_content_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_text == "Full Prescribing Information, including Boxed WARNING"
    assert c.content[0].extension.feed_card_label == "Label"
    assert c.content[0].extension.feed_card_title == "Title"
    assert c.content[0].extension.colour == "236B84"
    assert c.content[0].extension.button_text == "Start Activity"
    assert c.content[0].features.comment_queue_enabled is False
    assert c.content[0].features.comments_enabled is True
    assert c.content[0].features.reactions_enabled is True
    assert c.content[0].features.save_enabled is True
    assert c.content[0].features.share_enabled is True
    assert c.content[0].features.zoom_enabled is True
    assert c.content[0].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[0].sponsored_content.job_code == "123"
    assert c.content[0].sponsored_content.sponsored_text == "Sponsored Content"
    # Feed card media should be stripped from content in ES doc
    assert len(es_c.contentItems[0].media) == 1
    assert len(c.content[0].media) == 2
    assert c.content[0].media[0].filename == "1.png"
    assert c.content[0].media[0].height == 1080
    assert c.content[0].media[0].width == 1920
    assert c.content[0].media[0].type == MediaType.IMAGE
    assert c.content[0].media[0].display_order == 0

    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuids[0])
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 3
    assert qo[0].text == "Q1 Option A"
    assert qo[0].is_answer is True
    assert qo[0].display_order == 0
    assert qo[1].text == "Q1 Option B"
    assert qo[1].is_answer is False
    assert qo[1].display_order == 1
    assert qo[2].text == "Q1 Option C"
    assert qo[2].is_answer is False
    assert qo[2].display_order == 2

    # Content 2
    assert str(c.content[1].content_uuid) == content_uuids[1]
    assert c.content[1].content_type == ContentType.QUIZ_SERIES
    assert c.content[1].is_feed_card is False
    assert c.content[1].caption == "This is the second question"
    assert c.content[1].title == "Question 2"
    assert c.content[1].feed_card_type is None
    assert c.content[1].extension.question_answer_details == "Second question answer details"
    assert c.content[1].extension.external_link_text is None
    assert c.content[1].extension.external_link_url is None
    assert c.content[1].extension.heading == "Overarching quiz series banner"
    assert c.content[1].extension.isi_link is None
    assert c.content[1].extension.isi_embedded_content_link is None
    assert c.content[1].extension.isi_text is None
    assert c.content[1].features.comment_queue_enabled is False
    assert c.content[1].features.comments_enabled is True
    assert c.content[1].features.reactions_enabled is True
    assert c.content[1].features.save_enabled is True
    assert c.content[1].features.share_enabled is True
    assert c.content[1].features.zoom_enabled is True
    assert c.content[1].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[1].sponsored_content.job_code == "123"
    assert c.content[1].sponsored_content.sponsored_text == "Sponsored Content"
    assert len(c.content[1].media) == 1
    assert c.content[1].media[0].filename == "2.png"
    assert c.content[1].media[0].height == 1080
    assert c.content[1].media[0].width == 1920
    assert c.content[1].media[0].type == MediaType.IMAGE
    assert c.content[1].media[0].display_order == 0

    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuids[1])
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 2
    assert qo[0].text == "Q2 Option A"
    assert qo[0].is_answer is False
    assert qo[0].display_order == 0
    assert qo[1].text == "Q2 Option B"
    assert qo[1].is_answer is True
    assert qo[1].display_order == 1

    # Content 3
    assert str(c.content[2].content_uuid) == content_uuids[2]
    assert c.content[2].content_type == ContentType.QUIZ_SUMMARY
    assert c.content[2].is_feed_card is False
    assert c.content[2].caption == "This is the end of the quiz series"
    assert c.content[2].title is None
    assert c.content[2].feed_card_type is None
    assert c.content[2].extension.external_link_text == "Learn more"
    assert c.content[2].extension.external_link_url == "https://www.figure1.com"
    assert c.content[2].extension.heading == "Overarching quiz series banner"
    assert c.content[2].extension.isi_link == "https://www.figure1.com"
    assert c.content[2].extension.isi_embedded_content_link == "https://www.figure1.com"
    assert c.content[2].extension.isi_text == "Full Prescribing Information, including Boxed WARNING"
    assert c.content[2].features.comment_queue_enabled is False
    assert c.content[2].features.comments_enabled is True
    assert c.content[2].features.reactions_enabled is True
    assert c.content[2].features.save_enabled is True
    assert c.content[2].features.share_enabled is True
    assert c.content[2].features.zoom_enabled is True
    assert c.content[2].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[2].sponsored_content.job_code == "123"
    assert c.content[2].sponsored_content.sponsored_text == "Sponsored Content"
    assert len(c.content[2].media) == 0


def test_state_transitions(client, headers, load_db, test_user, test_campaign, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    moderator_uid = test_user.get('userUid')
    campaign_uuid = str(test_campaign.campaign_uuid)
    response = client.put(f'/admin/v1/campaign/{campaign_uuid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "name": "Test State Transitions here",
        "client_name": "Updated Client",
        "preview_user_uids": [moderator_uid]
    })
    assert response.status_code == 200

    # Create Static Case
    response = client.post(f'/admin/v1/case/static', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': campaign_uuid,
        "caption": "Sample caption",
        "title": "Sample title",
        "media": [
            {"filename": "1.png", "height": 1080, "type": "image", "width": 1920}
        ],
        "external_link": {
            "external_link_url": "https://www.figure1.com",
            "external_link_text": "Learn more"
        },
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "feed_card": {
            "feed_card_type": "highlight",
            "feed_card_label": "Label",
            "feed_card_title": "Title",
            "button_text": "Start Activity",
            "colour": "236B84"
        },
        "isi": {
            "isi_embedded_content_link": "https://www.figure1.com",
            "isi_link": "https://www.figure1.com",
            "isi_text": "Full Prescribing Information, including Boxed WARNING"
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": "123",
            "sponsored_text": "Sponsored Content"
        }
    })
    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')
    content_uuid = response.json.get('content_uuid')

    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_DRAFT
    assert c.is_paging_case is False
    assert len(c.authors) == 1
    assert str(c.authors[0].user_uuid) == test_user.get('userUuid')
    assert len(c.content) == 1
    assert str(c.content[0].content_uuid) == content_uuid
    assert c.content[0].content_type == ContentType.CONTENT
    assert c.content[0].is_feed_card is True
    assert c.content[0].caption == "Sample caption"
    assert c.content[0].title == "Sample title"
    assert c.content[0].extension.external_link_text == "Learn more"
    assert c.content[0].extension.external_link_url == "https://www.figure1.com"
    assert c.content[0].extension.isi_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_embedded_content_link == "https://www.figure1.com"
    assert c.content[0].extension.isi_text == "Full Prescribing Information, including Boxed WARNING"
    assert c.content[0].features.comment_queue_enabled is False
    assert c.content[0].features.comments_enabled is True
    assert c.content[0].features.reactions_enabled is True
    assert c.content[0].features.save_enabled is True
    assert c.content[0].features.share_enabled is True
    assert c.content[0].features.zoom_enabled is True
    assert c.content[0].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[0].sponsored_content.job_code == "123"
    assert c.content[0].sponsored_content.sponsored_text == "Sponsored Content"
    assert len(c.content[0].media) == 1
    assert c.content[0].media[0].filename == "1.png"
    assert c.content[0].media[0].height == 1080
    assert c.content[0].media[0].width == 1920
    assert c.content[0].media[0].type == MediaType.IMAGE
    assert c.content[0].media[0].display_order == 0

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Tactic"
    assert cc[0].tactic_priority == 1

    response_2 = client.post(f'/admin/v1/case/static', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': campaign_uuid,
        "caption": "Sample caption 2",
        "title": "Sample title 2",
        "media": [
            {"filename": "1.png", "height": 1080, "type": "image", "width": 1920}
        ],
        "external_link": {
            "external_link_url": "https://www.figure1.com",
            "external_link_text": "Learn more"
        },
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "feed_card": {
            "feed_card_type": "highlight",
            "feed_card_label": "Label",
            "feed_card_title": "Title",
            "button_text": "Start Activity",
            "colour": "236B84"
        },
        "isi": {
            "isi_embedded_content_link": "https://www.figure1.com",
            "isi_link": "https://www.figure1.com",
            "isi_text": "Full Prescribing Information, including Boxed WARNING"
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": "123",
            "sponsored_text": "Sponsored Content"
        }
    })

    assert response_2.status_code == 200
    case_uuid_2 = response_2.json.get('case_uuid')

    # Set the state to review for both tactics
    response_2 = client.post(f'/admin/v1/case/{case_uuid_2}/review', headers=headers, json={
        'moderator_uid': moderator_uid
    })

    assert response_2.status_code == 200

    response = client.post(f'/admin/v1/case/{case_uuid}/review', headers=headers, json={
        'moderator_uid': moderator_uid
    })

    assert response.status_code == 200
    session.expire_all()
    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_REVIEW
    preview_topic = session.query(CampaignPreviewUser) \
        .filter(CampaignPreviewUser.campaign_uuid == campaign_uuid) \
        .first()
    fs_doc = _get_fs_doc(fs=fs, user_uid=moderator_uid)

    # When a tactic is set to SC_REVIEW, it should show up as a feed for the preview users
    assert str(preview_topic.topic_uuid) in fs_doc['feeds'].keys()

    # Now publish tactic
    response = client.post(f'/admin/v1/case/{case_uuid}/publish', headers=headers, json={
        'moderator_uid': moderator_uid
    })

    assert response.status_code == 200
    session.expire_all()
    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_APPROVED
    campaign = session.query(Campaign).get(test_campaign.campaign_uuid)
    assert campaign.state == CampaignState.ACTIVE
    fs_doc = _get_fs_doc(fs=fs, user_uid=moderator_uid)

    # There is still one tactic in review state, so the user should still have the feed.
    assert str(preview_topic.topic_uuid) in fs_doc['feeds'].keys()

    response = client.post(f'/admin/v1/case/{case_uuid_2}/publish', headers=headers, json={
        'moderator_uid': moderator_uid
    })
    assert response.status_code == 200

    fs_doc = _get_fs_doc(fs=fs, user_uid=moderator_uid)
    # Now no tactics are in review state, so the feed should be removed from the firestore document
    assert str(preview_topic.topic_uuid) not in fs_doc['feeds'].keys()

    # Archive the campaign
    response = client.post(f'/admin/v1/campaign/{str(campaign.campaign_uuid)}/archive', headers=headers, json={
        'moderator_uid': moderator_uid
    })

    assert response.status_code == 200
    session.expire_all()
    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_ARCHIVED
    campaign = session.query(Campaign).get(test_campaign.campaign_uuid)
    assert campaign.state == CampaignState.ARCHIVED

    # Non-existent case should return 404
    response = client.post(f'/admin/v1/case/{str(uuid.uuid4())}/review', headers=headers, json={
        'moderator_uid': moderator_uid
    })

    assert response.status_code == 404

    # Reviewing an archived case should result in an error
    response = client.post(f'/admin/v1/case/{case_uuid}/publish', headers=headers, json={
        'moderator_uid': moderator_uid
    })

    assert response.status_code == 500

    response = client.post(f'/admin/v1/case/{case_uuid}/publish', headers=headers, json={
        'moderator_uid': 'notvaliduid'
    })

    assert response.status_code == 404


def test_clinical_moments(client, headers, load_db, test_user, test_campaign):
    session = load_db
    moderator_uid = test_user.get('userUid')
    # Create Static Case
    response = client.post(f'/admin/v1/case/clinical_moments', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        'cme1_credits': 0.25,
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "slides": [
            {
                "button_text": "Test your knowledge now",
                "colour": "5A3D93",
                "content_type": "FEED_CARD",
                "feed_card_label": "Grand Rounds",
                "feed_card_media": {
                    "filename": "test.png",
                    "height": 1080,
                    "type": "image",
                    "width": 1920
                },
                "feed_card_title": "Chronic Myeloid Leukemia (CML)"
            },
            {
                "caption": "This is a clinical moments activity.",
                "content_type": "COVER",
                "feed_card_label": "Grand Rounds",
                "isi": {
                    "isi_embedded_content_link": "http://www.figure1.com",
                    "isi_link": "http://www.figure1.com",
                    "isi_text": "Full Prescribing Information, including Boxed WARNING"
                },
                "media": [
                    {
                        "filename": "test2.png",
                        "height": 2002,
                        "type": "image",
                        "width": 3000
                    }
                ],
                "title": "Chronic Myeloid Leukemia (CML)"
            },
            {
                "caption": "This is a quiz question",
                "content_type": "QUIZ",
                "question_answer_details": "Second question answer details",
                "question_options": [
                    {
                        "is_answer": True,
                        "text": "Option 1"
                    },
                    {
                        "is_answer": False,
                        "text": "Option 2"
                    }
                ],
                "title": "Question"
            },
            {
                "caption": "The end of the clinical moments",
                "content_type": "CONTENT",
                "external_link": {
                    "external_link_text": "Learn more",
                    "external_link_url": "https://www.figure1.com"
                },
                "title": "Conclusion"
            }
        ],
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": 123,
            "sponsored_text": "Sponsored Content"
        }
    })
    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')
    content_uuids = response.json.get('content_uuids')

    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_DRAFT
    assert c.is_paging_case is False
    assert c.case_type == CaseType.CLINICAL_MOMENTS
    assert c.cme1_credits == 0.25
    assert len(c.authors) == 1
    assert str(c.authors[0].user_uuid) == test_user.get('userUuid')
    assert len(c.content) == 4
    assert str(c.content[0].content_uuid) == content_uuids[0]

    assert c.content[0].content_type == ContentType.FEED_CARD
    assert c.content[0].is_feed_card is True
    assert c.content[0].feed_card_type == FeedCardType.HIGHLIGHT
    assert c.content[0].extension.feed_card_label == "Grand Rounds"
    assert c.content[0].extension.feed_card_title == "Chronic Myeloid Leukemia (CML)"
    assert c.content[0].title == "Chronic Myeloid Leukemia (CML)"
    assert c.content[0].extension.colour == "5A3D93"
    assert c.content[0].extension.button_text == "Test your knowledge now"
    assert c.content[0].features.comment_queue_enabled is False
    assert c.content[0].features.comments_enabled is True
    assert c.content[0].features.reactions_enabled is True
    assert c.content[0].features.save_enabled is True
    assert c.content[0].features.share_enabled is True
    assert c.content[0].features.zoom_enabled is True
    assert c.content[0].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[0].sponsored_content.job_code == "123"
    assert c.content[0].sponsored_content.sponsored_text == "Sponsored Content"
    assert len(c.content[0].media) == 1
    assert c.content[0].media[0].filename == "test.png"
    assert c.content[0].media[0].height == 1080
    assert c.content[0].media[0].width == 1920
    assert c.content[0].media[0].type == MediaType.IMAGE
    assert c.content[0].media[0].display_order == 0

    assert c.content[1].content_type == ContentType.COVER
    assert c.content[1].is_feed_card is False
    assert c.content[1].caption == "This is a clinical moments activity."
    assert c.content[1].title == "Chronic Myeloid Leukemia (CML)"
    assert c.content[1].extension.feed_card_label == "Grand Rounds"
    assert c.content[1].extension.isi_embedded_content_link == "http://www.figure1.com"
    assert c.content[1].extension.isi_link == "http://www.figure1.com"
    assert c.content[1].extension.isi_text == "Full Prescribing Information, including Boxed WARNING"
    assert len(c.content[1].media) == 1
    assert c.content[1].features.comments_enabled is True

    assert c.content[2].content_type == ContentType.QUIZ
    assert c.content[2].is_feed_card is False
    assert c.content[2].caption == "This is a quiz question"
    assert c.content[2].title == "Question"
    assert c.content[2].extension.question_answer_details == "Second question answer details"
    assert c.content[2].features.comments_enabled is False
    assert len(c.content[2].media) == 0
    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuids[2])
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 2
    assert qo[0].text == "Option 1"
    assert qo[0].is_answer is True
    assert qo[0].display_order == 0
    assert qo[1].text == "Option 2"
    assert qo[1].is_answer is False
    assert qo[1].display_order == 1

    assert c.content[3].content_type == ContentType.CONTENT
    assert c.content[3].is_feed_card is False
    assert c.content[3].caption == "The end of the clinical moments"
    assert c.content[3].title == "Conclusion"
    assert c.content[3].extension.external_link_text == "Learn more"
    assert c.content[3].extension.external_link_url == "https://www.figure1.com"
    assert c.content[3].features.comments_enabled is False
    assert len(c.content[3].media) == 0

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Tactic"
    assert cc[0].tactic_priority == 1


def test_cme(client, headers, load_db, test_user, test_campaign, get_elasticsearch_client):
    session = load_db
    es = get_elasticsearch_client

    moderator_uid = test_user.get('userUid')

    response = client.post(f'/admin/v1/case/cme', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        'cme1_credits': 0.25,
        'passing_score': 1,
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "slides": [
            {
                "colour": "5A3D93",
                "content_type": "FEED_CARD",
                "feed_card_type": "HIGHLIGHT",
                "feed_card_label": "CME",
                "heading": "Start activity to earn 0.25 Category 1 Credits",
                "feed_card_media": {
                    "filename": "test.png",
                    "height": 1080,
                    "type": "image",
                    "width": 1920
                },
                "feed_card_title": "Chronic Myeloid Leukemia (CML)"
            },
            {
                "button_text": "Take the CME pre-test",
                "caption": "Front matter text",
                "content_type": "CONTENT",
                "section": "FRONT_MATTER"
            },
            {
                "caption": "Pre-test question 1",
                "content_type": "QUIZ",
                "heading": "Pre-test",
                "question_options": [
                    {
                        "is_answer": False,
                        "text": "Option 1"
                    },
                    {
                        "is_answer": False,
                        "text": "Option 2"
                    }
                ],
                "section": "PRE_TEST"
            },
            {
                "button_text": "Start activity",
                "caption": "This is a CME activity.",
                "content_type": "COVER",
                "feed_card_label": "CME",
                "external_link": {
                    "external_link_text": "",
                    "external_link_url": ""
                },
                "heading": "Start activity to earn 0.25 Category 1 Credits",
                "media": [
                    {
                        "filename": "33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png",
                        "height": 2002,
                        "type": "image",
                        "width": 3000
                    }
                ],
                "section": "ACTIVITY",
                "title": "Chronic Myeloid Leukemia (CML)"
            },
            {
                "caption": "Activity content 1",
                "content_type": "CONTENT",
                "section": "ACTIVITY"
            },
            {
                "caption": "Activity content 2",
                "content_type": "CONTENT",
                "section": "ACTIVITY"
            },
            {
                "button_text": "Take the CME post-test",
                "caption": "Conclusion text",
                "content_type": "CONCLUSION",
                "section": "ACTIVITY"
            },
            {
                "caption": "Post-test question 1",
                "content_type": "QUIZ",
                "heading": "Post-test",
                "question_options": [
                    {
                        "is_answer": True,
                        "text": "Option A"
                    },
                    {
                        "is_answer": False,
                        "text": "Option B"
                    }
                ],
                "section": "POST_TEST"
            },
            {
                "caption": "Did you enjoy this CME Activity?",
                "content_type": "QUIZ",
                "heading": "Survey",
                "question_options": [
                    {
                        "is_answer": False,
                        "text": "Yes"
                    },
                    {
                        "is_answer": False,
                        "text": "No"
                    }
                ],
                "section": "SURVEY"
            }
        ],
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": 123,
            "sponsored_text": "Sponsored Content"
        }
    })
    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')
    content_uuids = response.json.get('content_uuids')

    es_doc = es.get(index=es_settings.cases_alias, id=case_uuid)
    es_c: ESCaseModel = ESCaseModel.parse_obj(es_doc.get("_source"))
    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()

    assert c.state == CaseState.SC_DRAFT
    assert c.is_paging_case is False
    assert c.case_type == CaseType.CME
    assert len(c.authors) == 1
    assert str(c.authors[0].user_uuid) == test_user.get('userUuid')
    assert len(c.content) == 9
    assert str(c.content[0].content_uuid) == content_uuids[0]
    assert c.passing_score == 1

    assert c.content[0].content_type == ContentType.FEED_CARD
    assert es_c.contentItems[0].contentType is not None
    assert c.content[0].is_feed_card is True
    assert es_c.contentItems[0].isFeedCard is True
    assert c.content[0].feed_card_type == FeedCardType.HIGHLIGHT
    assert c.content[0].extension.feed_card_label == "CME"
    assert es_c.contentItems[0].feedCardLabel == "CME"
    assert c.content[0].extension.feed_card_title == "Chronic Myeloid Leukemia (CML)"
    assert es_c.contentItems[0].feedCardTitle == "Chronic Myeloid Leukemia (CML)"
    assert c.content[0].extension.colour == "5A3D93"
    assert es_c.contentItems[0].colour is not None
    assert c.content[0].extension.heading == "Start activity to earn 0.25 Category 1 Credits"
    assert es_c.contentItems[0].heading == "Start activity to earn 0.25 Category 1 Credits"
    assert c.content[0].features.comment_queue_enabled is False

    assert c.content[0].features.comments_enabled is True
    assert c.content[0].features.reactions_enabled is True
    assert c.content[0].features.save_enabled is True
    assert c.content[0].features.share_enabled is True
    assert c.content[0].features.zoom_enabled is True
    assert c.content[0].sponsored_content.disclosure_text == "This case is sponsored"
    assert c.content[0].sponsored_content.job_code == "123"
    assert c.content[0].sponsored_content.sponsored_text == "Sponsored Content"
    assert len(c.content[0].media) == 1
    assert len(es_c.contentItems[0].media) == 0

    assert c.content[0].media[0].filename == "test.png"
    assert c.content[0].media[0].height == 1080
    assert c.content[0].media[0].width == 1920
    assert c.content[0].media[0].type == MediaType.IMAGE
    assert c.content[0].media[0].display_order == 0

    assert c.content[1].section == ContentSection.FRONT_MATTER
    assert c.content[1].content_type == ContentType.CONTENT
    assert c.content[1].caption == "Front matter text"
    assert c.content[1].extension.button_text == "Take the CME pre-test"

    assert c.content[2].section == ContentSection.PRE_TEST
    assert c.content[2].content_type == ContentType.QUIZ
    assert c.content[2].caption == "Pre-test question 1"
    assert c.content[2].extension.heading == "Pre-test"
    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuids[2])
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 2
    assert qo[0].text == "Option 1"
    assert qo[0].is_answer is False
    assert qo[0].display_order == 0
    assert qo[1].text == "Option 2"
    assert qo[1].is_answer is False
    assert qo[1].display_order == 1

    assert c.content[3].section == ContentSection.ACTIVITY
    assert c.content[3].content_type == ContentType.COVER
    assert c.content[3].caption == "This is a CME activity."
    assert c.content[3].extension.heading == "Start activity to earn 0.25 Category 1 Credits"
    assert c.content[3].features.comments_enabled is True

    assert c.content[4].section == ContentSection.ACTIVITY
    assert c.content[4].content_type == ContentType.CONTENT
    assert c.content[4].caption == "Activity content 1"

    assert c.content[5].section == ContentSection.ACTIVITY
    assert c.content[5].content_type == ContentType.CONTENT
    assert c.content[5].caption == "Activity content 2"

    assert c.content[6].section == ContentSection.ACTIVITY
    assert c.content[6].content_type == ContentType.CONCLUSION
    assert c.content[6].caption == "Conclusion text"
    assert c.content[6].extension.button_text == "Take the CME post-test"

    assert c.content[7].section == ContentSection.POST_TEST
    assert c.content[7].content_type == ContentType.QUIZ
    assert c.content[7].caption == "Post-test question 1"
    assert c.content[7].extension.heading == "Post-test"
    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuids[7])
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 2
    assert qo[0].text == "Option A"
    assert qo[0].is_answer is True
    assert qo[0].display_order == 0
    assert qo[1].text == "Option B"
    assert qo[1].is_answer is False
    assert qo[1].display_order == 1

    assert c.content[8].section == ContentSection.SURVEY
    assert c.content[8].content_type == ContentType.QUIZ
    assert c.content[8].caption == "Did you enjoy this CME Activity?"
    assert c.content[8].extension.heading == "Survey"
    qo = list(session.query(QuestionOption)
              .filter(QuestionOption.content_uuid == content_uuids[8])
              .order_by(QuestionOption.display_order)
              .all())
    assert len(qo) == 2
    assert qo[0].text == "Yes"
    assert qo[0].is_answer is False
    assert qo[0].display_order == 0
    assert qo[1].text == "No"
    assert qo[1].is_answer is False
    assert qo[1].display_order == 1

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Tactic"
    assert cc[0].tactic_priority == 1

    # Test slide deletion
    response = client.put(f'/admin/v1/case/cme/{case_uuid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        'cme1_credits': 0.25,
        'passing_score': 0,
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "slides": [
            {
                "colour": "5A3D93",
                "content_type": "FEED_CARD",
                "feed_card_type": "HIGHLIGHT",
                "feed_card_label": "CME",
                "heading": "Start activity to earn 0.25 Category 1 Credits",
                "feed_card_media": {
                    "filename": "test.png",
                    "height": 1080,
                    "type": "image",
                    "width": 1920
                },
                "feed_card_title": "Chronic Myeloid Leukemia (CML)"
            },
            {
                "button_text": "Take the CME pre-test",
                "caption": "Front matter text",
                "content_type": "CONTENT",
                "section": "FRONT_MATTER"
            }
        ],
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": 123,
            "sponsored_text": "Sponsored Content"
        }
    })
    print(response.data)
    assert response.status_code == 200
    session.expire_all()

    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert len(c.content) == 2


def test_cme_with_optional_cover_caption(client, headers, load_db, test_user, test_campaign, get_elasticsearch_client):
    moderator_uid = test_user.get('userUid')
    response = client.post(f'/admin/v1/case/cme', headers=headers, json={
        'moderator_uid': moderator_uid,
        'author_uid': moderator_uid,
        'campaign_uuid': str(test_campaign.campaign_uuid),
        'cme1_credits': 0.25,
        'passing_score': 1,
        "features": {
            "comment_queue_enabled": False,
            "comments_enabled": True,
            "reactions_enabled": True,
            "save_enabled": True,
            "share_enabled": True,
            "zoom_enabled": True
        },
        "settings": {
            "name": "New Tactic",
            "tactic_priority": 1
        },
        "slides": [
            {
                "colour": "5A3D93",
                "content_type": "FEED_CARD",
                "feed_card_type": "HIGHLIGHT",
                "feed_card_label": "CME",
                "heading": "Start activity to earn 0.25 Category 1 Credits",
                "feed_card_media": {
                    "filename": "test.png",
                    "height": 1080,
                    "type": "image",
                    "width": 1920
                },
                "feed_card_title": "Chronic Myeloid Leukemia (CML)"
            },
            {
                "button_text": "Take the CME pre-test",
                "caption": "Front matter text",
                "content_type": "CONTENT",
                "section": "FRONT_MATTER"
            },
            {
                "caption": "Pre-test question 1",
                "content_type": "QUIZ",
                "heading": "Pre-test",
                "question_options": [
                    {
                        "is_answer": False,
                        "text": "Option 1"
                    },
                    {
                        "is_answer": False,
                        "text": "Option 2"
                    }
                ],
                "section": "PRE_TEST"
            },
            {
                "button_text": "Start activity",
                "content_type": "COVER",
                "feed_card_label": "CME",
                "external_link": {
                    "external_link_text": "",
                    "external_link_url": ""
                },
                "heading": "Start activity to earn 0.25 Category 1 Credits",
                "media": [
                    {
                        "filename": "33468feea4872dbaab01b8f383ef83606c82d1dce0cf5393fb4044c026ef5071.png",
                        "height": 2002,
                        "type": "image",
                        "width": 3000
                    }
                ],
                "section": "ACTIVITY",
                "title": "Chronic Myeloid Leukemia (CML)"
            },
            {
                "caption": "Activity content 1",
                "content_type": "CONTENT",
                "section": "ACTIVITY"
            },
            {
                "caption": "Activity content 2",
                "content_type": "CONTENT",
                "section": "ACTIVITY"
            },
            {
                "button_text": "Take the CME post-test",
                "caption": "Conclusion text",
                "content_type": "CONCLUSION",
                "section": "ACTIVITY"
            },
            {
                "caption": "Post-test question 1",
                "content_type": "QUIZ",
                "heading": "Post-test",
                "question_options": [
                    {
                        "is_answer": True,
                        "text": "Option A"
                    },
                    {
                        "is_answer": False,
                        "text": "Option B"
                    }
                ],
                "section": "POST_TEST"
            },
            {
                "caption": "Did you enjoy this CME Activity?",
                "content_type": "QUIZ",
                "heading": "Survey",
                "question_options": [
                    {
                        "is_answer": False,
                        "text": "Yes"
                    },
                    {
                        "is_answer": False,
                        "text": "No"
                    }
                ],
                "section": "SURVEY"
            }
        ],
        "sponsored_content": {
            "disclosure_text": "This case is sponsored",
            "job_code": 123,
            "sponsored_text": "Sponsored Content"
        }
    })
    assert response.status_code == 200


def test_promo_card(client, headers, load_db, test_user, test_campaign):
    session = load_db
    moderator_uid = test_user.get('userUid')
    # Create Promo Card
    response = client.post(f'/admin/v1/case/promo_card', headers=headers, json={
        "button_text": "Click here",
        "button_url": "{{ root_url }}{{ profile_detail_path }}/" + test_user.get("userUuid"),
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Sample caption",
        "job_code": None,
        'moderator_uid': moderator_uid,
        "title": "Sample title",
        "features": {
            "dismiss_button": False,
            "dismiss_on_click": True,
            "show_in_mobile": False,
            "show_in_web": False,
        },
        "settings": {
            "name": "New Promo Card",
            "tactic_priority": 1
        }
    })

    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')
    content_uuid = response.json.get('content_uuid')

    c = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    assert c.state == CaseState.SC_DRAFT
    assert c.is_paging_case is False
    assert c.case_type == CaseType.PROMO_CARD
    assert len(c.authors) == 1
    assert str(c.authors[0].user_uuid) == test_user.get('userUuid')
    assert len(c.content) == 1
    assert str(c.content[0].content_uuid) == content_uuid
    assert c.content[0].content_type == ContentType.PROMO_CARD
    assert c.content[0].is_feed_card is False
    assert c.content[0].caption == "Sample caption"
    assert c.content[0].title == "Sample title"
    assert c.content[0].feed_card_type is None
    assert c.content[0].extension.external_link_text is None
    assert c.content[0].extension.external_link_url is None
    assert c.content[0].extension.isi_link is None
    assert c.content[0].extension.isi_embedded_content_link is None
    assert c.content[0].extension.isi_text is None
    assert c.content[0].extension.feed_card_label is None
    assert c.content[0].extension.feed_card_title is None
    assert c.content[0].extension.colour is None
    assert c.content[0].extension.button_text == "Click here"
    assert c.content[0].features.dismiss_button is False
    assert c.content[0].features.dismiss_on_click is True
    assert c.content[0].features.show_in_web is False
    assert c.content[0].features.show_in_mobile is False
    assert c.content[0].sponsored_content.disclosure_text is None
    assert c.content[0].sponsored_content.job_code is None
    assert c.content[0].sponsored_content.sponsored_text is None
    assert len(c.content[0].media) == 0

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Promo Card"
    assert cc[0].tactic_priority == 1

    pc = PromoCardDetail.firestore_detail(case_uuid=case_uuid, session=session)
    populated = populate_template(pc, user_uuid=test_user.get('userUuid'), case_uuid=case_uuid)
    assert populated['mobile']['buttonLink'] == f"figure1pro://app.figure1.com/user/detail/{test_user.get('userUuid')}"
    assert populated['web']['buttonLink'] == f"https://app.figure1.com/profile/{test_user.get('userUuid')}"


def test_create_promo_card_with_start_and_end_date(client, headers, load_db, test_user, test_campaign):
    session = load_db
    moderator_uid = test_user.get('userUid')
    # Create Promo Card with start and end dates
    response = client.post(f'/admin/v1/case/promo_card', headers=headers, json={
        "button_text": "Click here",
        "button_url": "{{ root_url }}{{ profile_detail_path }}/" + test_user.get("userUuid"),
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Sample caption",
        "job_code": None,
        'moderator_uid': moderator_uid,
        "title": "Sample title",
        "features": {},
        "settings": {
            "name": "New Promo Card",
            "tactic_priority": 1,
            "start_date": "2021-12-08",
            "end_date": "2021-12-31"
        }
    })

    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].name == "New Promo Card"
    assert cc[0].tactic_priority == 1
    assert cc[0].start_date.strftime('%Y-%m-%d') == "2021-12-08"
    assert cc[0].end_date.strftime('%Y-%m-%d') == "2021-12-31"

    # Start date cannot be later than end date
    response1 = client.post(f'/admin/v1/case/promo_card', headers=headers, json={
        "button_text": "Click here",
        "button_url": "{{ root_url }}{{ profile_detail_path }}/" + test_user.get("userUuid"),
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Sample caption",
        "job_code": None,
        'moderator_uid': moderator_uid,
        "title": "Sample title",
        "features": {},
        "settings": {
            "name": "New Promo Card",
            "tactic_priority": 1,
            "start_date": "2021-12-08",
            "end_date": "2020-12-31"
        }
    })

    assert response1.status_code == 500
    assert response1.json['error'] == "Start date cannot be later than end date"

    # If start_date is not set, the current date is assumed; If end_date is not set, end_date is set to Null
    response2 = client.post(f'/admin/v1/case/promo_card', headers=headers, json={
        "button_text": "Click here",
        "button_url": "{{ root_url }}{{ profile_detail_path }}/" + test_user.get("userUuid"),
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Sample caption",
        "job_code": None,
        'moderator_uid': moderator_uid,
        "title": "Sample title",
        "features": {},
        "settings": {
            "name": "New Promo Card",
            "tactic_priority": 1
        }
    })

    assert response2.status_code == 200
    case_uuid = response2.json.get('case_uuid')

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].start_date is not None
    assert cc[0].end_date is None

    response3 = client.post(f'/admin/v1/case/promo_card', headers=headers, json={
        "button_text": "Click here",
        "button_url": "{{ root_url }}{{ profile_detail_path }}/" + test_user.get("userUuid"),
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Sample caption",
        "job_code": None,
        'moderator_uid': moderator_uid,
        "title": "Sample title",
        "features": {},
        "settings": {
            "name": "New Promo Card",
            "tactic_priority": 1,
            "start_date": "2021-12-08"
        }
    })

    assert response3.status_code == 200
    case_uuid = response3.json.get('case_uuid')

    cc = list(session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all())
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].start_date.strftime('%Y-%m-%d') == "2021-12-08"
    assert cc[0].end_date is None


def test_set_date_range_for_a_given_tatic(client, headers, load_db, test_user, test_campaign):
    session = load_db
    moderator_uid = test_user.get('userUid')
    # Create Promo Card
    response = client.post(f'/admin/v1/case/promo_card', headers=headers, json={
        "button_text": "Click here",
        "button_url": "{{ root_url }}{{ profile_detail_path }}/" + test_user.get("userUuid"),
        'campaign_uuid': str(test_campaign.campaign_uuid),
        "caption": "Sample caption",
        "job_code": None,
        'moderator_uid': moderator_uid,
        "title": "Sample title",
        "features": {},
        "settings": {
            "name": "New Promo Card",
            "tactic_priority": 1
        }
    })

    assert response.status_code == 200
    case_uuid = response.json.get('case_uuid')

    cc = session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all()
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].start_date.strftime('%Y-%m-%d') is not None
    assert cc[0].end_date is None

    response1 = client.post(f'/admin/v1/case/{case_uuid}/set', headers=headers, json={
        "moderator_uid": moderator_uid,
        "start_date": "2022-12-13",
        "tactic_priority": 0
    })

    assert response1.status_code == 200

    session.expire_all()
    cc = session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all()
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].start_date.strftime('%Y-%m-%d') == "2022-12-13"

    response2 = client.post(f'/admin/v1/case/{case_uuid}/set', headers=headers, json={
        "moderator_uid": moderator_uid,
        "start_date": "2023-12-13",
        "end_date": "2023-12-31",
        "tactic_priority": 0
    })

    assert response2.status_code == 200

    session.expire_all()
    cc = session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all()
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].start_date.strftime('%Y-%m-%d') == "2023-12-13"
    assert cc[0].end_date.strftime('%Y-%m-%d') == "2023-12-31"

    response3 = client.post(f'/admin/v1/case/{case_uuid}/set', headers=headers, json={
        "moderator_uid": moderator_uid,
        "end_date": "2050-12-31",
        "tactic_priority": 0
    })

    assert response3.status_code == 200

    session.expire_all()
    cc = session.query(CampaignCase).filter(CampaignCase.case_uuid == case_uuid).all()
    assert len(cc) == 1
    assert cc[0].campaign_uuid == test_campaign.campaign_uuid
    assert cc[0].start_date.strftime('%Y-%m-%d') == "2023-12-13"
    assert cc[0].end_date.strftime('%Y-%m-%d') == "2050-12-31"
