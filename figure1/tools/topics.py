import csv
import logging
import os
import re
from typing import List, Any

from pydantic.types import UUID
from sqlalchemy.orm import Session

from figure1.admin.reference_data import sync_topics
from figure1.core import managed_session
from figure1.common.models.db import SpecialtyV2, Topic, FeedType, FeedKind

logger = logging.getLogger('upload_topics')


def _create_label(name=None):
    """
    Strip all whitespace characters and lowercase.
    """
    label = re.sub(r'\s+', repl="", string=name)
    return label.lower()


def _upsert_topic(name: str,
                  label: str,
                  display_order: int,
                  specialties: List[UUID],
                  session):
    ft = FeedType.create(kind=FeedKind.TOPIC,
                         name=name,
                         label=f"topic_{label}",
                         skip_commit=True,
                         session=session)
    Topic.create_or_update(feed_type_uuid=ft.feed_type_uuid,
                           name=name,
                           label=label,
                           specialty_uuids=specialties,
                           display_order=display_order,
                           hidden=False,
                           session=session).as_dict()


def _get_specialty_uuid(label: str,
                        session: Session) -> UUID:
    s = session.query(SpecialtyV2) \
        .filter(SpecialtyV2.label == label, SpecialtyV2.is_valid_case_tag.is_(True)) \
        .one_or_none()
    return s.specialty_uuid if s else None


def _handle_topic_line(data_line: List[Any],
                       display_order: int,
                       session: Session):
    name = data_line.pop(0)
    label = _create_label(name)

    specialty_uuids = []
    for specialty in [x for x in data_line if x]:
        specialty_label = _create_label(specialty)
        uuid = _get_specialty_uuid(label=specialty_label, session=session)
        if not uuid:
            logger.warning(f"Couldn't find uuid for {specialty_label}")
        else:
            specialty_uuids.append(uuid)

    if specialty_uuids:
        _upsert_topic(name=name,
                      label=label,
                      display_order=display_order,
                      specialties=specialty_uuids,
                      session=session)
        logger.info(f"Updated topic: {name}")


@managed_session
def load_topic_data(filename, session):
    """
    Loads topic data from a csv file.

    The expected csv structure is
      Column 0: <topic_name:str>
      Columns 1..n:  <mapped_specialties:str>

    Both FeedType and Topic entries are created for each topic.  If a topic label matches an existing topic, the
    specialties and display order of the topic are updated.

    Other notes:
        - Topics are marked as hidden=False
        - The display order is inferred from the row position in the csv
        - Once import is complete, a task is scheduled to sync topics to firestore
    """
    if os.path.isfile(filename):
        with open(filename, mode='r', newline='') as fn:
            reader = csv.reader(fn)
            for i, line in enumerate(reader):
                _handle_topic_line(data_line=line,
                                   display_order=i,
                                   session=session)
    else:
        return {"Error": f"Filename {filename} is not a file"}

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f'Failed to update topics: {e}')
        return {"Error": f"Failed to update topics: {e}"}

    sync_topics.delay()
    return {"Success": f"Topics updated"}
