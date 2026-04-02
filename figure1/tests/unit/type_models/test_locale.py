import pytest

from figure1.common.types import Locale


@pytest.mark.parametrize('language', ['en_us', 'EN_US', 'PT_PT', 'pt_pt', 'pt', 'en', 'es'])
def test_supported_language(language):
    assert Locale.is_supported(language) is not False


@pytest.mark.parametrize('language', ['ens', 'US', 'P', 'asd', 'JP', 'BR'])
def test_not_supported_language(language):
    assert Locale.is_supported(language) is False


@pytest.mark.parametrize('language, output_code', [('en_us', 'EN_US'),
                                                   ('EN_US', 'EN_US'),
                                                   ('PT_PT', 'PT_PT'),
                                                   ('pt_pt', 'PT_PT'),
                                                   ('pt', 'PT_PT'),
                                                   ('en', 'EN_US'),
                                                   ('es', 'ES_ES')])
def test_get_language_from_code(language, output_code):
    locale = Locale.get_from_code(language)
    assert isinstance(locale, Locale)
    assert locale.code == output_code


@pytest.mark.parametrize('language, output_code', [('esf', 'EN_US'),
                                                   ('dff', 'EN_US'),
                                                   ('443', 'EN_US'),
                                                   ('%4', 'EN_US'),
                                                   ('-', 'EN_US'),
                                                   ('ffsd', 'EN_US'),
                                                   ('f', 'EN_US')])
def test_get_unsupported_language_from_code(language, output_code):
    locale = Locale.get_from_code(language)
    assert isinstance(locale, Locale)
    assert locale.code == output_code


@pytest.mark.parametrize('language, output_code', [('en_us', 'EN_US'),
                                                   ('EN_US', 'EN_US'),
                                                   ('PT_PT', 'PT_PT'),
                                                   ('pt_pt', 'PT_PT'),
                                                   ('pt', 'PT_PT'),
                                                   ('en', 'EN_US'),
                                                   ('es', 'ES_ES')])
def test_supported_language_search_filter(language, output_code):
    filter = Locale.get_lang_code_filter(allow_languages=language)
    assert isinstance(filter, list)
    assert filter[0] == output_code
