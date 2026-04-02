import os
import csv
import logging
from figure1.common.models.db import BlockedUsernames, LessBlockedUsernames
from figure1.core import managed_session

logger = logging.getLogger(__name__)


@managed_session
def load_bad_words(filename, session):
    if os.path.isfile(filename):
        with open(filename, mode='r', newline='') as fn:
            reader = csv.reader(fn)
            next(reader)
            for line in reader:
                if line[0]:
                    forbidden_word = line[0]
                    BlockedUsernames.usernames(session=session, forbidden_usernames=forbidden_word)
                else:
                    logger.info("No forbidden words on line %s", line)
                if line[1]:
                    disallowed_word = line[1]
                    LessBlockedUsernames.usernames(session=session, less_forbidden_usernames=disallowed_word)
                else:
                    logger.info("No disallowed words on line %s", line)
        return {"Error": f"Filename {filename} is not a file"}
    return
