from figure1.common.models.db import SpecialtyTreeV2, Campaign
from figure1.common.types import CampaignState


def test_create_update_campaign(client, headers, load_db, test_user, test_country):
    session = load_db
    moderator_uid = test_user.get('userUid')

    specialty = session.query(SpecialtyTreeV2).first()

    # Create
    response = client.post(f'/admin/v1/campaign', headers=headers, json={
        'moderator_uid': moderator_uid,
        "name": "Test Campaign",
        "client_name": "Client",
    })
    assert response.status_code == 200

    campaign_uuid = response.json.get('campaign_uuid')
    c = session.query(Campaign) \
        .filter(Campaign.campaign_uuid == campaign_uuid) \
        .one()

    assert c.name == "Test Campaign"
    assert c.state == CampaignState.DRAFT
    assert c.client_name == "Client"
    assert len(c.target_countries) == 0
    assert len(c.target_specialties) == 0
    assert len(c.target_languages) == 0

    # Update
    response = client.put(f'/admin/v1/campaign/{campaign_uuid}', headers=headers, json={
        'moderator_uid': moderator_uid,
        "name": "Updated Name",
        "client_name": "Updated Client",
        "preview_user_uids": [moderator_uid],
        "target_country_uuids": [str(test_country.country_uuid)],
        "target_specialty_uuids": [str(specialty.specialty_uuid), None],
        "target_languages": ["lang1", "lang2"],
        "target_verification": True,
        "is_sponsored": True,
    })

    assert response.status_code == 200

    session.refresh(c)
    assert c.name == "Updated Name"
    assert c.state == CampaignState.DRAFT
    assert c.client_name == "Updated Client"
    assert len(c.preview_users)
    assert str(c.preview_users[0].user_uuid) == test_user.get('userUuid')
    assert len(c.target_countries) == 1
    assert c.target_countries[0].country_uuid == test_country.country_uuid
    assert len(c.target_specialties) == 1
    assert c.target_specialties[0].tree_uuid == specialty.specialty_uuid
    assert len(c.target_languages) == 2
    assert c.target_languages[0].language == "lang1"
    assert c.target_languages[1].language == "lang2"
    assert c.target_verification
    assert c.is_sponsored

    # Update state to active
    response = client.post(f'/admin/v1/campaign/{campaign_uuid}/state', headers=headers, json={
        'moderator_uid': moderator_uid,
        "state": "active",
    })
    assert response.status_code == 200

    session.refresh(c)

    assert c.state == CampaignState.ACTIVE

    # Update state to archived
    response = client.post(f'/admin/v1/campaign/{campaign_uuid}/state', headers=headers, json={
        'moderator_uid': moderator_uid,
        "state": "archived",
    })
    assert response.status_code == 200

    session.refresh(c)

    assert c.state == CampaignState.ARCHIVED
