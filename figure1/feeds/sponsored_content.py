import logging
import json
from figure1.store import UserSponsoredContentStore
from elasticsearch.exceptions import NotFoundError
from elasticsearch.helpers import scan
from figure1.configuration import es_settings
from figure1.core import es
from typing import List, Optional, Dict

case_alias = es_settings.cases_alias
users = es_settings.users_alias
logger = logging.getLogger('figure1.sponsoredContent')


def get_all_sponsored_content():
    sp = SponsoredContent()
    q = sp.generate_base_query()
    e = scan(es, query=q, _source=False, scroll="5m", index=case_alias, size=1000)
    for result in e:
        yield result.get("_id")


class SponsoredContentTargets:
    """
    If a caseUuid is passed, other entries are ignored and the targeting criteria is taken from the elasticsearch
    document.
    Otherwise,
    """
    countryUuids = []
    targetTreeUuids = []
    isVerified = None
    campaignSettings = {}

    def __init__(self, countryUuids=None, targetTreeUuids=None, isVerified=None, caseUuid=None):
        if caseUuid:
            self.caseUuid = caseUuid
            self._get_campaign_settings()
        else:
            self.countryUuids = self._validate(countryUuids)
            self.targetTreeUuids = self._validate(targetTreeUuids)
            if isVerified is True or isVerified is False:
                self.isVerified = isVerified
            else:
                self.isVerified = None

    def _validate(self, f):
        if not f:
            return
        if not isinstance(f, list):
            return [f]
        return f

    def _get_base_query(self):
        return {
            "query": {
                "bool": {
                    "must": [
                    ],
                    "should": [
                    ]
                }
            }
        }

    def _add_country_terms(self):
        if not self.countryUuids:
            return {}
        return {
            "terms": {
                "countryUuid.keyword": self.countryUuids
            }
        }

    def _add_target_tree_uuids(self):
        if not self.targetTreeUuids:
            return {}

        return {
            "terms": {
                "primarySpecialty.treeUuid.keyword": self.targetTreeUuids
            }
        }

    def _add_secondary_target_tree_uuids(self):
        if not self.targetTreeUuids:
            return {}
        return {
            "terms": {
                "secondarySpecialties": self.targetTreeUuids
            }
        }

    def _add_verified_filter(self):
        if not self.isVerified:
            return {}

        return {
            "term": {
                "isVerified": self.isVerified
            }
        }

    def _get_campaign_settings(self):
        if self.caseUuid:
            case_doc = es.get(index="newcases", id=self.caseUuid)
            if not case_doc.get("found"):
                return
            self.campaign_settings = case_doc.get("_source", {}).get("campaignSettings")
            self.targetTreeUuids = self.campaign_settings.get("treeTargets", [])
            self.countryUuids = self.campaign_settings.get("countryTargets", [])
            self.isVerified = self.campaign_settings.get("verificationTarget", False)

    def get_targeted_users_query(self):
        """
        Returns an empty dict if no parameters are found or passed in
        :return:
        """
        q = self._get_base_query()
        is_empty = True
        country_search = self._add_country_terms()
        if country_search:
            is_empty = False
            q["query"]["bool"]["must"].append(country_search)
        primary_target = self._add_target_tree_uuids()
        if primary_target:
            is_empty = False
            q["query"]["bool"]["must"].append(primary_target)
        secondary_target = self._add_secondary_target_tree_uuids()
        if secondary_target:
            is_empty = False
            q["query"]["bool"]["should"].append(secondary_target)
        verified = self._add_verified_filter()
        if verified:
            is_empty = False
            q["query"]["bool"]["must"].append(verified)
        if is_empty:
            return {}
        return q

    def get_user_uids(self):
        """
        Returns a generator of tuples of the form (user_uuid, user_uid). Only users with a uid are returned.
        :return:
        """
        q = self.get_targeted_users_query()
        if not q:
            return []
        total_count = 0
        e = scan(es, query=q, _source_includes="userUid", scroll="5m", index=users, size=1000)
        for result in e:
            if result.get("_source").get("userUid"):
                total_count += 1
                yield result.get("_id"), result.get("_source").get("userUid")


class SponsoredContent:
    test_mode = False
    is_valid = False
    sponsoredContentInsertRate = 3
    sponsored_config = {}

    def __repr__(self):
        return "SponsoredContent<is_valid:%r,sponsored_config:%r>" % (self.is_valid, self.sponsored_config)

    def __init__(self, user_uuid=None, countryUuids=None, target_tree_uuids=None, is_verified=None):
        """
        Pass either a user_uuid or pass in each of the targeting parameters. If a user_uuid is passed, the other
        parameters are ignored.

        :param user_uuid: A single user_uuid, does not accept a list
        :param countryUuids: A single stringified uuid or a list
        :param target_tree_uuids: A single tree uuid or a list
        :param is_verified: boolean
        """

        if user_uuid:
            self.sponcon = UserSponsoredContentStore(user_uuid=user_uuid)
            self.user_uuid = user_uuid
            self.sponsored_config = self.sponcon.get_user_target()

        else:
            if countryUuids:
                self.sponsored_config.update({'targetCountry': countryUuids})
            if target_tree_uuids:
                self.sponsored_config.update({'targetTree': target_tree_uuids})
            if is_verified:
                self.sponsored_config.update({'isVerified': is_verified})
        if self.sponsored_config:
            self.is_valid = True

    def _date_order_decay(self):
        return {
            "nested": {
                "path": "campaignSettings",
                "query": {
                    "function_score": {
                        "linear": {
                            "campaignSettings.startDate": {
                                "scale": "1d",
                                "decay": 0.9
                            }
                        }
                    }
                }
            }
        }

    def _priority_score(self):
        return {
            "nested": {
                "path": "campaignSettings",
                "query": {
                    "function_score": {
                        "functions": [
                            {
                                "field_value_factor": {
                                    "field": "campaignSettings.campaignPriority",
                                    "factor": 1,
                                    "modifier": "none",
                                    "missing": 1
                                }
                            },
                            {
                                "field_value_factor": {
                                    "field": "campaignSettings.tacticPriority",
                                    "factor": 1,
                                    "modifier": "none",
                                    "missing": 1
                                }
                            }
                        ],
                        "max_boost": 10,
                        "score_mode": "sum",
                        "boost_mode": "sum"
                    }
                }
            }
        }

    def _filter_has_feed_card(self):
        return {
            "nested": {
                "path": "contentItems",
                "query": {
                    "term": {
                        "contentItems.isFeedCard": {
                            "value": True
                        }
                    }
                }
            }
        }

    def _filter_tactic_state(self, state='SC_APPROVED'):
        return {
            "term": {
                "caseState": {
                    "value": state
                }
            }
        }

    def _filter_verified_state(self, verified=True):
        return {
            "bool": {
                "should": [
                    {
                        "nested": {
                            "path": "campaignSettings",
                            "query": {
                                "term": {
                                    "campaignSettings.verificationTarget": verified
                                }
                            }
                        }
                    },
                    {
                        "bool": {
                            "must_not": {
                                "nested": {
                                    "path": "campaignSettings",
                                    "query": {
                                        "exists": {
                                            "field": "campaignSettings.verificationTarget"
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }

    def _filter_region(self, targetCountryUuid):
        if not isinstance(targetCountryUuid, list):
            targetCountryUuid = [targetCountryUuid]

        return {
            "bool": {
                "should": [
                    {
                        "nested": {
                            "path": "campaignSettings",
                            "query": {
                                "terms": {
                                    "campaignSettings.countryTargets": targetCountryUuid
                                }
                            }
                        }
                    },
                    {
                        "bool": {
                            "must_not": {
                                "nested": {
                                    "path": "campaignSettings",
                                    "query": {
                                        "exists": {
                                            "field": "campaignSettings.countryTargets"
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }

    def _filter_tactic_start(self, relative_start_date="now/d"):
        """
        The tactic start date is a must match - this works because the start date should always be filled in for an
        approved tactic.
        :param relative_start_date:
        :return:
        """
        return {
            "nested": {
                "path": "campaignSettings",
                "query": {
                    "range": {
                        "campaignSettings.startDate": {
                            "lte": relative_start_date
                        }
                    }
                }
            }
        }

    def _filter_tactic_end(self, relative_end_date="now/d"):
        """
        This has to be a filter because we have to account for an empty end date.
        :param relative_end_date:
        :return:
        """
        return {
            "bool": {
                "should": [
                    {
                        "nested": {
                            "path": "campaignSettings",
                            "query": {
                                "range": {
                                    "campaignSettings.endDate": {
                                        "gt": "now/d"
                                    }
                                }
                            }
                        }
                    },
                    {
                        "bool": {
                            "must_not": {
                                "nested": {
                                    "path": "campaignSettings",
                                    "query": {
                                        "exists": {
                                            "field": "campaignSettings.endDate"
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }

    def _filter_campaign_state(self, campaign_state="ACTIVE"):
        return {
            "nested": {
                "path": "campaignSettings",
                "query": {
                    "term": {
                        "campaignSettings.campaignState": {
                            "value": campaign_state
                        }
                    }
                }
            }
        }

    def _filter_professions(self) -> Optional[Dict]:
        target_tree_filter = {
            "nested": {
                "path": "campaignSettings",
                "query": {
                    "terms": {
                        "campaignSettings.treeTargets": self.sponsored_config.get("targetTree")
                    }
                }
            }
        }
        if self.sponsored_config.get("targetTree"):
            return target_tree_filter
        return None

    def _filter_case_type(self, caseType="promo_card"):
        return {
            "term": {
                "caseType": caseType
            }
        }

    def _generate_base_query(self):
        tactic_query = {
            "query": {
                "bool": {
                    "filter": [
                        self._filter_tactic_state(),
                        self._filter_campaign_state(),
                        self._filter_tactic_end(),
                        # self._filter_verified_state(verified=self.user_sponsored_config.get("targetIsVerified")),
                    ],
                    "must": [
                        self._filter_tactic_start(),
                    ],
                    "should": [
                        self._date_order_decay(),
                        self._priority_score()
                    ]
                }
            }
        }

        if self._filter_professions():
            tactic_query['query']['bool']['must'].append(self._filter_professions())

        if self.sponsored_config.get("targetCountry"):
            tactic_query['query']['bool']['filter'].append(
                self._filter_region(targetCountryUuid=self.sponsored_config.get("targetCountry")))

        return tactic_query

    def generate_base_query(self):
        """
        Filters out promo cards, returns all other valid sponsored content
        """
        tactic_query = self._generate_base_query()
        tactic_query["query"]["bool"].update({"must_not": [self._filter_case_type()]})
        return tactic_query

    def get_valid_promo_cards_query(self):
        tactic_query = self._generate_base_query()
        tactic_query["query"]["bool"]["filter"].append(self._filter_case_type())
        return tactic_query

    def generate_tactic_query(self):
        tactic_query = self._generate_base_query()
        tactic_query["query"]["bool"]["filter"].append(self._filter_has_feed_card())
        tactic_query["query"]["bool"].update({"must_not": [self._filter_case_type()]})
        return tactic_query

    def get_promo_card_ids(self):
        tactic_query = self.get_valid_promo_cards_query()
        tactic_query.update({"_source": False})
        results = es.search(index=es_settings.cases_alias, body=tactic_query)
        return [x.get("_id") for x in results.get("hits", {}).get("hits", [])]

    def get_tactics(self):
        if self.is_valid is False:
            logger.error("User does not have valid targetting data")
        tactic_query = self.generate_tactic_query()
        tactic_query.update({"_source": ["caseUuid",
                                         "title",
                                         "campaignSettings.campaignPriority",
                                         "campaignSettings.tacticPriority",
                                         "caseState"]})
        logger.info("Tactic query %s", json.dumps(tactic_query))
        return es.search(index=es_settings.cases_alias, body=tactic_query)

    def get_cme_ids(self):
        if self.is_valid is False:
            logger.error("User does not have valid targeting data")
        tactic_query = self._generate_base_query()
        tactic_query["query"]["bool"]["filter"].append(self._filter_case_type(caseType='cme'))
        results = scan(es,
                       query=tactic_query,
                       _source=False,
                       scroll="1m",
                       index=es_settings.cases_alias, size=500)
        for case_uuid in results:
            yield case_uuid.get("_id")

    def regenerate_sponsored_content(self, force=False):
        if self.is_valid is False:
            logger.error("User does not have valid targetting data")
        sp = self.get_tactics()
        item_list = []
        for item in sp.get('hits', {}).get('hits', []):
            item_list.append(item.get('_source', {}).get('caseUuid'))
        self.sponcon.write_sponcon_list(items=item_list)
        return True

    def inject_id_only(self, result_list, skip_first_insert=True) -> List:
        """
        This function injects sponsored content ids into the result list, but does not resolve them.
        :param result_list:
        :param skip_first_insert:
        :return: List of IDs with the content injected
        """
        result = []
        injected_content = []
        for i, r in enumerate(result_list):
            if not i % (self.sponsoredContentInsertRate - 1):
                if skip_first_insert and i == 0:
                    logger.debug("Skipping first item when set")
                else:
                    sp_item = self.sponcon.get_next_item()
                    logger.debug("Adding sponsored content item %s", sp_item)
                    if self.test_mode:
                        result.append(sp_item)
                    elif sp_item:
                        if sp_item in injected_content:
                            logger.debug("Served items %s", injected_content)
                            logger.info("Content item %s already served", sp_item)
                        else:
                            logger.debug("Injected sponsored content item %s", sp_item)
                            injected_content.append(sp_item)
                            result.append(sp_item)
                    else:
                        logger.debug("Sponsored content queue is %s", self.sponcon.get_sponcon_full_queue())
                        logger.info("No sponsored content item found")
            result.append(r)
        return result
