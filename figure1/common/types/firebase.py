import random
import time
from enum import Enum


class FirebaseAction(Enum):
    SET = 1,
    DELETE = 2,
    DELETE_COLLECTION = 3


class FirebaseFeedID(object):
    # This is copied nearly verbatim except for some small changes to avoid
    # importing numpy

    # Modeled after base64 web-safe chars, but ordered by ASCII.
    PUSH_CHARS = ('-0123456789'
                  'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                  '_abcdefghijklmnopqrstuvwxyz')

    def __init__(self):

        # Timestamp of last push, used to prevent local collisions if you
        # pushtwice in one ms.
        self.lastPushTime = 0

        # We generate 72-bits of randomness which get turned into 12
        # characters and appended to the timestamp to prevent
        # collisions with other clients.  We store the last characters
        # we generated because in the event of a collision, we'll use
        # those same characters except "incremented" by one.
        self.lastRandChars = []

    def next_id(self):
        now = int(time.time() * 1000)
        duplicateTime = (now == self.lastPushTime)
        self.lastPushTime = now
        timeStampChars = []

        for i in range(7, -1, -1):
            timeStampChars.append(self.PUSH_CHARS[now % 64])
            now = int(now / 64)
        timeStampChars.reverse()
        if now:
            raise ValueError('We should have converted the entire timestamp.')

        uid = ''.join(timeStampChars)
        #
        if not duplicateTime:
            self.lastRandChars = []
            for i in range(12):
                self.lastRandChars.insert(i, int(random.random() * 64))
        else:
            # If the timestamp hasn't changed since last push, use the
            # same random number, except incremented by 1.
            for i in range(11, -1, -1):
                if self.lastRandChars[i] == 63:
                    self.lastRandChars[i] = 0
                else:
                    break
            self.lastRandChars[i] += 1

        for i in range(12):
            uid += self.PUSH_CHARS[self.lastRandChars[i]]

        if len(uid) != 20:
            raise ValueError('Length should be 20.')
        return uid
