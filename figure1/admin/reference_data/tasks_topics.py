from figure1.common.elasticsearch import get_topic_top_cases
from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.helpers import FeedCard
from figure1.common.models.db import Topic


def _get_top_cases(specialty_uuids):
    for feed_item in get_topic_top_cases(specialty_uuid_filters=specialty_uuids):
        fc = FeedCard.feed_card(feed_item=feed_item)
        if fc:
            yield fc


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.sync_topics')
def sync_topics(self, clean=None):
    firestore_data = []
    hidden_firestore_data = []
    doc = self.fs_client.collection('referenceData').document('topics')
    doc_old = self.fs_client.collection('b_referenceData').document('topics')

    for topic in Topic.get_all_topics_as_dict(session=self.session):
        if topic.get('hidden'):
            hidden_firestore_data.append({
                "uuid": topic.get('feedTypeUuid'),
                "name": topic.get('name'),
                "label": topic.get('label'),
                'displayOrder': topic.get('displayOrder'),
                "titleCases": list(_get_top_cases(topic.get('specialtyUuids')))
            })
        else:
            firestore_data.append({
                "uuid": topic.get('feedTypeUuid'),
                "name": topic.get('name'),
                "label": topic.get('label'),
                'displayOrder': topic.get('displayOrder'),
                "titleCases": list(_get_top_cases(topic.get('specialtyUuids')))
            })
    doc.set({
        "all": firestore_data,
        "hidden": hidden_firestore_data
    }, merge=False)
    doc_old.set({
        "all": firestore_data,
        "hidden": hidden_firestore_data
    }, merge=False)
