from datetime import datetime, timedelta, timezone
from figure1.configuration import es_settings
from figure1.feeds.sponsored_content import SponsoredContent
from figure1.common.models.db import SpecialtyTreeV2, User
from figure1.common.helpers import UserDocument
from figure1.common.types import CaseType
from figure1.store import UserSponsoredContentStore


def _target_campaign_tactic(tactic_started=True,
                            tactic_ended=True,
                            target_tree_uuid=None,
                            tactic_id=None,
                            case_type=CaseType.STATIC):
    cmp_settings = {'campaignState': "ACTIVE"}
    if tactic_started:
        cmp_settings.update({'startDate': str(datetime.now(tz=timezone.utc))})
    else:
        cmp_settings.update({'startDate': str(datetime.now(tz=timezone.utc) + timedelta(days=1))})

    if tactic_ended:
        cmp_settings.update({'endDate': str(datetime.now(tz=timezone.utc))})
    else:
        cmp_settings.update({'endDate': str(datetime.now(tz=timezone.utc) + timedelta(days=10))})

    if target_tree_uuid:
        cmp_settings.update({'treeTargets': target_tree_uuid})
    return {
        "doc": {
            "contentItems": [
                {"isFeedCard": True}
            ],
            "tacticID": tactic_id,
            "caseState": "SC_APPROVED",
            "campaignSettings": cmp_settings,
            "caseType": case_type.name.lower()
        },
        "doc_as_upsert": True
    }


def test_inject(load_db, get_elasticsearch_client):
    es = get_elasticsearch_client

    user_uuid = "test_user_uuid"
    sp = UserSponsoredContentStore(user_uuid=user_uuid)
    usc = SponsoredContent(user_uuid=user_uuid)
    usc.test_mode = True
    sp.write_sponcon_list(['sp1', 'sp2', 'sp3', 'sp4', 'sp5', 'sp6', 'sp7'])

    q = usc.generate_tactic_query()

    # Run this query against elasticsearch, this just ensures the generated query is valid, we don't care about the
    # return, however declaring r shows the output if any if there is an error.
    r = es.search(index=es_settings.cases_alias, body=q)

    result_set = usc.inject_id_only(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'], skip_first_insert=True)
    a = sp.get_next_item()
    assert result_set[0] != 'sp1'
    assert 'sp1' in result_set
    assert 'sp2' in result_set
    assert 'sp3' in result_set


def test_tactic_tree_targeting(test_physician_user, load_db, get_elasticsearch_client):
    """
    Given a targeted tactic
    It should:
    - not appear before the startdate has passed
    - not appear after the enddate has passed
    - appear after the startdate has passed and before the enddate has passed
    - not appear if it's an unsupported case type
    It should not:
    - appear if the target tree data does not match
    :param test_user:
    :param load_db:
    :param get_elasticsearch_client:
    :return:
    """
    session = load_db
    es = get_elasticsearch_client
    u = User.get_user_by_uuid(user_uuid=test_physician_user.get("userUuid"), raise_exception=True, session=session)

    ud = UserDocument.get_user_target_data(user_uid=test_physician_user.get("userUid"), session=session)

    non_targeted_user_specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.specialty_uuid.not_in(ud.get("targetTree")),
                SpecialtyTreeV2.specialty_v2_uuid.isnot(None)) \
        .first()
    ob = non_targeted_user_specialty.as_object()

    non_targetted_body = _target_campaign_tactic(tactic_started=True,
                                                 tactic_ended=False,
                                                 tactic_id='not_targeted',
                                                 target_tree_uuid=ob.treeUuid)

    targeted_body = _target_campaign_tactic(tactic_started=True,
                                            tactic_ended=False,
                                            tactic_id='targeted',
                                            target_tree_uuid=ud.get("targetTree")[0])

    targeted_not_started = _target_campaign_tactic(tactic_started=False,
                                                   tactic_ended=False,
                                                   tactic_id='targeted_not_started',
                                                   target_tree_uuid=ud.get("targetTree")[0])

    targeted_ended = _target_campaign_tactic(tactic_started=True,
                                             tactic_ended=True,
                                             tactic_id='targeted_ended',
                                             target_tree_uuid=ud.get("targetTree")[0])

    targeted_promo_card = _target_campaign_tactic(tactic_started=True,
                                                  tactic_ended=False,
                                                  tactic_id='targeted',
                                                  target_tree_uuid=ud.get("targetTree")[0],
                                                  case_type=CaseType.PROMO_CARD)

    es.update(index=es_settings.cases_alias, body=non_targetted_body, id='nottargeted', refresh='wait_for')
    es.update(index=es_settings.cases_alias, body=targeted_body, id='targeted', refresh='wait_for')
    es.update(index=es_settings.cases_alias, body=targeted_not_started, id='targeted_not_started', refresh='wait_for')
    es.update(index=es_settings.cases_alias, body=targeted_ended, id='targeted_ended', refresh='wait_for')
    es.update(index=es_settings.cases_alias, body=targeted_promo_card, id='targeted_promo_card', refresh='wait_for')

    usc = SponsoredContent(user_uuid=test_physician_user.get("userUuid"))

    q = usc.generate_tactic_query()
    r = es.search(index=es_settings.cases_alias, body=q)
    hitlist = [x.get('_id') for x in r.get('hits', {}).get('hits')]
    assert 'targeted' in hitlist
    assert 'not_targeted' not in hitlist
    assert 'targeted_ended' not in hitlist
    assert 'targeted_not_started' not in hitlist
    assert 'targeted_promo_card' not in hitlist
