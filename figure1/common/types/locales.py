import enum

from pydantic import BaseModel, Field
from typing import Any, Dict, List


class LocaleModel(BaseModel):
    code: str
    name: str
    languageShortName: str = Field(alias='language_short_name')
    languageCode: str = Field(alias='language_code')


class Locale(enum.Enum):
    EN_US = LocaleModel(code='EN_US',
                        name='English - United States',
                        language_short_name='English',
                        language_code='EN')
    ES_ES = LocaleModel(code='ES_ES',
                        name='Spanish - Spain (Traditional)',
                        language_short_name='Spanish',
                        language_code='ES')
    PT_PT = LocaleModel(code='PT_PT',
                        name='Portuguese - Portugal',
                        language_short_name='Portuguese',
                        language_code='PT')

    def __repr__(self):
        return self.value.json()

    @staticmethod
    def _get_supported(code):

        """
        Given a language code or other code, return the Locale object if supported otherwise return false.
        """
        if isinstance(code, Locale):
            return True
        if isinstance(code, str):
            for k in Locale.__members__:
                if Locale[k].language_code.lower() == code.lower():
                    return Locale[k]
                if Locale[k].code.lower() == code.lower():
                    return Locale[k]
        return False

    @staticmethod
    def is_supported(code):
        if Locale._get_supported(code):
            return True
        return False

    @property
    def code(self):
        return self.value.code

    @property
    def name(self):
        return self.value.name

    @property
    def language_short_name(self):
        return self.value.languageShortName

    @property
    def language_code(self):
        return self.value.languageCode

    def as_dict(self) -> Dict[str, Any]:
        return self.value.dict()

    @staticmethod
    def get_from_code(code) -> 'Locale':
        """
        Given either a language_code ('EN') or a locale code ('ES_ES'), return a Locale instance. If no match is found,
        a Locale instance populated with english is returned.
        If a Locale instance is passed, it is simply returned as is.
        :param code: language_code('EN'), a locale code ('ES_ES'), or a Locale instance
        :return: Locale instance
        """
        locale = Locale._get_supported(code)
        return locale if locale else Locale.EN_US

    @staticmethod
    def get_lang_code_filter(allow_languages=None) -> List:
        """
        This returns a list of language codes suitable for filtering with elasticsearch.

        :param allow_languages: Accepts a list of either strings(allow_languages=['es', 'pt']) or Locale objects
        :return: Always returns a list, if no match is found, then a list with EN_US is returned

        """
        if not allow_languages:
            return list(Locale.EN_US.code.upper())

        filter_list = set()
        if isinstance(allow_languages, list):
            for lang in allow_languages:
                loc_lang = Locale.get_from_code(lang)
                filter_list.add(loc_lang.code.upper())

        if isinstance(allow_languages, str):
            lang = Locale.get_from_code(allow_languages)
            filter_list.add(lang.code.upper())

        if isinstance(allow_languages, Locale):
            filter_list.add(allow_languages.code.upper())

        if not filter_list:
            filter_list.add(Locale.EN_US.code.upper())

        return list(filter_list)
