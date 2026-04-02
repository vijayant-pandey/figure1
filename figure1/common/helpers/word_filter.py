import logging
from re import Pattern, IGNORECASE, compile
from figure1.exceptions import FoundNotAllowedWord
from figure1.common.models.db import LessBlockedUsernames
from figure1.common.models.db import BlockedUsernames

logger = logging.getLogger(__name__)


class WordMatcher:
    """
    Forbidden words are not allowed anywhere in the string.
    Disallowed words are only allowed as part of a word, they are not allowed on their own.
    """
    forbidden_word_list = []
    disallowed_word_list = []
    forbidden_search_re = None
    disallowed_word_re = None
    number_map = [
        ('1', 'l'),
        ('3', 'e'),
        ('5', 's'),
        ('0', 'o')]

    @classmethod
    def _load_forbidden_words(cls):
        for word in BlockedUsernames.q.all():
            if word.forbidden_usernames not in cls.forbidden_word_list:
                cls.forbidden_word_list.append(word.forbidden_usernames)

    @classmethod
    def _load_disallowed_words(cls):
        for word in LessBlockedUsernames.q.all():
            if word.less_forbidden_usernames not in cls.disallowed_word_list:
                cls.disallowed_word_list.append(word.less_forbidden_usernames)

    @classmethod
    def regenerate_regex(cls):
        if not cls.forbidden_word_list:
            cls._load_forbidden_words()
        cls.forbidden_search_re = compile("|".join(cls.forbidden_word_list), IGNORECASE)
        if not cls.disallowed_word_list:
            cls._load_disallowed_words()
        cls.disallowed_word_re = compile(r'\b(?:' + "|".join(cls.disallowed_word_list) + r')\b', IGNORECASE)

    @classmethod
    def get_forbidden_word_regex(cls) -> Pattern:
        if not cls.forbidden_search_re:
            cls.regenerate_regex()
        return cls.forbidden_search_re

    @classmethod
    def get_disallowed_word_regex(cls) -> Pattern:
        if not cls.disallowed_word_re:
            cls.regenerate_regex()
        return cls.disallowed_word_re

    @staticmethod
    def replace_numbers(full_string):
        """
        Replace any numbers that are commonly used as letters with the letters
        :param full_string: Search this string for numbers commonly used as letters
        :type full_string: str
        :return: String with potential numbers replaced
        :rtype: str
        """
        for tup in WordMatcher.number_map:
            if tup[0] in full_string:
                logger.error("Found %s in string", tup[0])
                full_string = full_string.replace(tup[0], tup[1])
        return full_string

    @staticmethod
    def find_blocked_word_in_string(word_string) -> None:
        """
        Try to find a word in the string passed in with the following rules:
        1) If a word is in the forbidden_words list, it cannot be part of any word in addition to matching a word
        2) If a word is in the disallowed list, it may be part of a word, but cannot be used on its own.

        :param word_string: The string that may contain the word
        :type word_string: str

        :return: Raises FoundNotAllowedWord if a disallowed word is found, otherwise returns None
        :raises: FoundNotAllowedWord
        :rtype: None
        """

        forbidden_re = WordMatcher.get_forbidden_word_regex()
        sub_number_string = WordMatcher.replace_numbers(word_string)

        search_match = forbidden_re.search(word_string)
        if search_match:
            for m in search_match.regs:
                logger.error("Word %s matched a word in the forbidden list", word_string[m[0]:m[1]])
                raise FoundNotAllowedWord(word=word_string[m[0]:m[1]])

        search_match = forbidden_re.search(sub_number_string)
        if search_match:
            for m in search_match.regs:
                logger.error("Word %s matched a word in the forbidden list after number substitution",
                             sub_number_string[m[0]:m[1]])
                raise FoundNotAllowedWord(word=sub_number_string[m[0]:m[1]])

        disallowed_re = WordMatcher.get_disallowed_word_regex()

        search_match = disallowed_re.search(word_string)
        if search_match:
            for m in search_match.regs:
                logger.error("Word %s matched a word in the disallowed list", word_string[m[0]:m[1]])
                raise FoundNotAllowedWord(word=word_string[m[0]:m[1]])

        search_match = disallowed_re.search(sub_number_string)
        if search_match:
            for m in search_match.regs:
                logger.error("Word %s matched a word in the disallowed list after number substitution",
                             sub_number_string[m[0]:m[1]])
                raise FoundNotAllowedWord(word=sub_number_string[m[0]:m[1]])
