import logging
import json
from operator import itemgetter
from typing import Dict
from typing import Optional
from pydantic import ValidationError

from figure1.common.types import FeedCardModel
from figure1.common.types import FeedCardDisplayModel
from figure1.common.types import UserAuthorModel


class FeedCard:

    @staticmethod
    def parse_authors(authors, is_anonymous=False):
        """
        If the datasource is elasticsearch, then is_anonymous=True is required to anonymize the authors.
        All authors data from elasticsearch are not anonymized even if the case is anonymous.
        :param authors:
        :param is_anonymous:
        :return: parsed_authors
        """
        parsed_authors = []
        for each_author in authors:
            parsed_authors.append(UserAuthorModel.parse_obj({**each_author, "is_anonymous": is_anonymous}).dict())

        return parsed_authors

    @staticmethod
    def feed_card(feed_item, user_uuid=None) -> Optional[Dict]:
        """
        Given an elasticsearch result, parse out fields into a document that is pushed to firestore.
        If a validation error is hit, returns None

        The only mandatory fields are:
        caseUuid

        For the feed_display_card
        feedCardType
        """
        hit = None
        if isinstance(feed_item, dict):
            if '_source' in feed_item:
                hit = feed_item.get('_source')
            if 'caseUuid' in feed_item:
                hit = feed_item
        if not hit:
            return None
        if hit.get('feedCardType') == 'end_of_feed':
            return hit
        if hit.get('feedCardType') == 'preview_feed':
            return hit
        try:
            is_anonymous, hit_authors = hit.get('isAnonymous'), hit.get('authors', [])
            hit.update({'authors': FeedCard.parse_authors(hit_authors, is_anonymous=is_anonymous)})
            feed_card_model = FeedCardModel.parse_obj(hit)
        except ValidationError as ve:
            logging.error("Validation failed with error %s for item %s", ve, json.dumps(hit))
            return None

        feed_card_model.score = feed_item.get("_score")
        feed_card_model.updateCount = sum(len(c.get('updates', [])) for c in hit.get('contentItems', []))
        feed_card_model.contentCount = len(hit.get("contentItems", []))

        media = hit.get('media', None)
        media_sorted_list = []
        if media:
            media_sorted_list = sorted(media, key=itemgetter('displayOrder'))
            feed_card_model.media = media_sorted_list

        if user_uuid:
            feed_card_model.isSaved = str(user_uuid) in hit.get('userSaved', [])
            for k in hit.get('reactions', {}).keys():
                if user_uuid in hit.get('reactions', {}).get(k, []):
                    feed_card_model.userReactions = [k]
                    break

        feed_cards = [c for c in hit.get('contentItems', []) if c.get('isFeedCard')]

        if not feed_cards:
            if feed_card_model.contentCount == 1:
                try:
                    fc = hit['contentItems'][0]
                except IndexError:
                    logging.error("Failed get content item")
                    return feed_card_model.dict()
            else:
                logging.error(f'No content was found for case {hit.get("caseUuid")} with a feed card')
                return feed_card_model.dict()
        else:
            fc = feed_cards[0]

        try:
            feed_card_display = FeedCardDisplayModel.parse_obj(fc)
        except ValidationError as ve:
            logging.error("Validation failed with error %s for item %s", ve, json.dumps(feed_item))
            return None

        return {**feed_card_model.dict(exclude={'features'}), **feed_card_display.dict()}
