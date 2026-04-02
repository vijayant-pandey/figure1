from figure1.common.models.db import Case
from figure1.tests.utils import *
from figure1.common.models.validator import Validate
from figure1.common.elasticsearch import add_or_update_case
import uuid


def create_channel(app, headers):
    client = app.test_client()
    channel = PromotionTestModels.create_channel()
    response = client.post('/explorer/v1/promotion/channel', json=channel, headers=headers)
    assert response.status_code == 200
    assert response.json
    return response.json


def create_promotion(app, headers):
    client = app.test_client()
    channel = create_channel(app, headers)
    v = Validate()
    promotion = PromotionTestModels.create_promotion(channel_uuid=channel['channel_uuid'])
    promotion_resp = client.post('/explorer/v1/promotion', json=promotion, headers=headers)
    assert promotion_resp.status_code == 200
    assert v.validate(promotion_resp.json, 'explorer_promotion') is None
    return promotion_resp.json


def get_promotion(app, headers, promotion_uuid):
    client = app.test_client()
    v = Validate()
    pr = client.get('/explorer/v1/promotion/' + promotion_uuid, headers=headers)
    assert pr.status_code == 200
    assert v.validate(pr.json, 'explorer_promotion') is None
    return pr.json


def add_case(app, headers, promotion_uuid, case_uuid):
    client = app.test_client()
    promotion = client.get('/explorer/v1/promotion/' + promotion_uuid, headers=headers)
    assert promotion.status_code == 200
    assert promotion.json
    promotion_json = promotion.json
    case = PromotionTestModels.case_model(promotion_uuid=promotion_uuid, case_uuid=case_uuid)
    promotion_json['cases'].append(case)
    attach_case = client.post('/explorer/v1/promotion', json=promotion_json, headers=headers)
    assert attach_case.status_code == 200


def delete_promotion(app, headers, promotion_uuid):
    client = app.test_client()
    del_pr = client.delete('/explorer/v1/promotion/' + promotion_uuid, headers=headers)
    assert del_pr.status_code == 200


def delete_channel(app, headers, channel_uuid):
    client = app.test_client()
    del_ch = client.delete('/explorer/v1/promotion/channel/' + channel_uuid, headers=headers)
    # Returning 400 indicates this channel is in use by another promotion. This is expected behaviour
    assert del_ch.status_code in [200, 400]


def test_create_promotion(app, headers):
    pr = create_promotion(app, headers)
    v = Validate()
    assert v.validate(pr, 'explorer_promotion') is None
    delete_promotion(app, headers, promotion_uuid=pr['promotion_uuid'])
    delete_channel(app, headers, channel_uuid=pr['channel_uuid'])


def test_attach_case(app, headers, load_db):
    pr = create_promotion(app, headers)
    case = load_db.query(Case).filter(Case.state == 'APPROVED').first()
    add_or_update_case(case_uuid=str(case.case_uuid), session=load_db)
    v = Validate()
    add_case(app, headers, case_uuid=case.case_uuid, promotion_uuid=pr['promotion_uuid'])
    case_pr = get_promotion(app, headers, promotion_uuid=pr['promotion_uuid'])
    assert len(case_pr['cases']) == 1
    assert v.validate(case_pr, 'explorer_promotion') is None
    delete_promotion(app, headers, promotion_uuid=pr['promotion_uuid'])
    delete_channel(app, headers, channel_uuid=pr['channel_uuid'])
