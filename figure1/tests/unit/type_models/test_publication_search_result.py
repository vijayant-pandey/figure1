import pytest

from figure1.common.types import PublicationSearchResult, PublicationSummaryResult
from figure1.admin.moderation.tagging.mesh_on_demand import PublicationSearch


@pytest.fixture(scope='session')
def test_publication_search(monkeypatch):
    """
    Test the execution of the search including preparing the terms and sending them.
    :param monkeypatch:
    :return:
    """

    def return_search_result(url, params):
        """
        This overrides the _execute_search in PublicationSearch in order to return a search result without calling
        an external API. It takes the same arguments, but here they are checked to ensure they have been parsed
        and generated correctly.
        """
        assert params == {'db': 'pubmed',
                          'retmode': 'json',
                          'term': 'griseofulvin[MeSH Terms],Mycoses[MeSH Terms]'}

        assert url == 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'

        return {"header": {"type": "esearch", "version": "0.3"},
                "esearchresult": {"count": "1509", "retmax": "20", "retstart": "0",
                                  "idlist": ["34445992", "34436619", "34041831", "33998709", "33794219",
                                             "33769754", "33618899", "33141453", "33064847", "32901593",
                                             "32897584", "32862439", "32851760", "32729125", "32573255",
                                             "32538466", "32139093", "31343780", "31153545", "31042257"],
                                  "translationset": [{"from": "griseofulvin[MeSH Terms]",
                                                      "to": "\"griseofulvin\"[MeSH Terms]"},
                                                     {"from": ", Mycoses[MeSH Terms]",
                                                      "to": "\"mycoses\"[MeSH Terms]"}],
                                  "translationstack": [
                                      {"term": "\"griseofulvin\"[MeSH Terms]", "field": "MeSH Terms",
                                       "count": "3145", "explode": "Y"},
                                      {"term": "\"mycoses\"[MeSH Terms]", "field": "MeSH Terms",
                                       "count": "133251", "explode": "Y"}, "AND"],
                                  "querytranslation": "\"griseofulvin\"[MeSH Terms] AND \"mycoses\"[MeSH Terms]"}}

    monkeypatch.setattr(PublicationSearch, "_execute_search", return_search_result)
    search_result = PublicationSearch.search_terms(terms=['griseofulvin', 'Mycoses'])

    assert isinstance(search_result, PublicationSearchResult)
    assert len(search_result.pubMedIds) == 20
    assert search_result.resultCount == 1509
    assert search_result.maxReturn == 20
    return search_result


@pytest.fixture(scope='session')
def test_publication_summary_lookup(monkeypatch):
    def return_summary_result(url, params):
        assert params.get('id', '').find("34041831") >= 0
        assert params.get('id', '').find("334847") >= 0

        assert params.get('db') == 'pubmed'

        assert url == 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi'
        return {
            "header": {
                "type": "esummary", "version": "0.3"
            },
            "result": {
                "uids": ["34041831", "334847"],
                "34041831": {
                    "uid": "34041831",
                    "pubdate": "2021 Jul",
                    "epubdate": "2021 Jun 2",
                    "source": "Dermatol Ther",
                    "authors": [
                        {"name": "Kumar P",
                         "authtype": "Author",
                         "clusterid": ""},
                        {"name": "Pandhi D",
                         "authtype": "Author",
                         "clusterid": ""},
                        {"name": "Bhattacharya SN",
                         "authtype": "Author",
                         "clusterid": ""},
                        {"name": "Das S",
                         "authtype": "Author",
                         "clusterid": ""}
                    ],
                    "lastauthor": "Das S",
                    "title": "Trichoscopy as a monitoring tool in assessing "
                             "treatment response in 98 children with tinea"
                             " capitis: A prospective clinical study.",
                    "sorttitle": "trichoscopy as a monitoring tool in assessing "
                                 "treatment response in 98 children with tinea capitis"
                                 " a prospective clinical study",
                    "volume": "34", "issue": "4",
                    "pages": "e15010",
                    "lang": ["eng"],
                    "nlmuniqueid": "9700070",
                    "issn": "1396-0296",
                    "essn": "1529-8019",
                    "pubtype": ["Journal Article"],
                    "recordstatus": "PubMed - indexed for MEDLINE",
                    "pubstatus": "256",
                    "articleids": [
                        {"idtype": "pubmed",
                         "idtypen": 1,
                         "value": "34041831"},
                        {"idtype": "doi",
                         "idtypen": 3,
                         "value": "10.1111/dth.15010"},
                        {"idtype": "rid",
                         "idtypen": 8,
                         "value": "34041831"},
                        {"idtype": "eid",
                         "idtypen": 8,
                         "value": "34041831"}],
                    "history": [
                        {"pubstatus": "received",
                         "date": "2021/03/15 00:00"},
                        {"pubstatus": "accepted",
                         "date": "2021/05/24 00:00"},
                        {"pubstatus": "pubmed",
                         "date": "2021/05/28 06:00"},
                        {"pubstatus": "medline",
                         "date": "2021/08/24 06:00"},
                        {"pubstatus": "entrez",
                         "date": "2021/05/27 07:12"}],
                    "references": [],
                    "attributes": ["Has Abstract"],
                    "pmcrefcount": "",
                    "fulljournalname": "Dermatologic therapy",
                    "elocationid": "doi: 10.1111/dth.15010",
                    "doctype": "citation",
                    "srccontriblist": [],
                    "booktitle": "", "medium": "",
                    "edition": "",
                    "publisherlocation": "",
                    "publishername": "",
                    "srcdate": "", "reportnumber": "",
                    "availablefromurl": "",
                    "locationlabel": "",
                    "doccontriblist": [],
                    "docdate": "", "bookname": "",
                    "chapter": "",
                    "sortpubdate": "2021/07/01 00:00",
                    "sortfirstauthor": "Kumar P",
                    "vernaculartitle": ""},
                "334847": {"uid": "334847",
                           "error": "cannot get document summary"}}}

    monkeypatch.setattr(PublicationSearch, "_execute_search", return_summary_result)
    for summary_result in PublicationSearch.lookup_summary(pubmedIds=['34041831', '334847']):
        assert isinstance(summary_result, PublicationSummaryResult)
        assert 34041831 in summary_result.resultUids

        for summary in summary_result.results:
            if summary.pubMedId == 334847:
                assert summary.error is not None
                assert summary.title is None
                assert summary.journalName is None
            if summary.pubMedId == 34041831:
                assert summary.title is not None
                assert summary.journalName is not None
                assert summary.error is None
            yield summary
