"""
Returns MeSH keywords and publications retrieved from the google healthcare api
"""

import re
import logging
import requests
from typing import Tuple, Optional, Iterator
from figure1.common.models.db import Content, PublicMeshConcepts, PublicMesh, PublicMeshTerms, CaseMeshTerms, \
    PublicMeshConceptTerms
from figure1.common.types import Locale, \
    MeshModel, \
    MeshTermsModel, \
    MeshConceptModel, \
    PublicationSearchResult, \
    PublicationSummaryResult
from figure1.core.firebase import HealthCareApi
from figure1.common.utils import split_list_to_smaller_lists

logger = logging.getLogger(__name__)


class MeshError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class PublicationSearchOverloaded(Exception):
    pass


class MeshLookup(object):
    root_mesh_url = 'https://id.nlm.nih.gov'
    hc_client: HealthCareApi = None

    def __init__(self):
        MeshLookup.get_hc_client()

    @classmethod
    def get_hc_client(cls):
        if cls.hc_client is None:
            cls.hc_client = HealthCareApi()
        return cls.hc_client

    def _get_mesh_data(self, code):
        url = f'{self.root_mesh_url}/mesh/{code}.json'
        r = requests.get(url=url)
        return r.json()

    def _return_mesh_model(self, code) -> MeshModel:
        resp = self._get_mesh_data(code)
        mesh_model = MeshModel.parse_obj(resp)
        return mesh_model

    def _get_code_from_url(self, url):
        term = url.split('/')[-1].split('.')[0]
        return term

    def parse_term(self, code) -> MeshTermsModel:
        term = self._get_mesh_data(code)
        return MeshTermsModel.parse_obj(term)

    def parse_concept_terms(self, code) -> MeshConceptModel:
        concept = self._get_mesh_data(code)
        return MeshConceptModel.parse_obj(concept)

    def get_mesh_object(self, code) -> MeshModel:
        return self._return_mesh_model(code)

    def get_generic_mesh_data(self, code):
        return self._get_mesh_data(code=code)

    def get_mesh_codes(self, text):
        if self.hc_client is None:
            logger.error("Created google client on mesh code lookup, should have been created earlier")
            MeshLookup.get_hc_client()
        if self.hc_client.is_disabled():
            logger.critical("Unable to fetch mesh terms, Google API is disabled")
            return StopIteration

        for mesh_code, mesh_type in self.hc_client.analyze_text(text=text):
            yield mesh_code, mesh_type


class MeshDataAPI(MeshLookup):

    def __init__(self, case_uuid, session):
        super().__init__()
        if session:
            self.session = session
        else:
            raise MeshError("No session passed to mesh data api")
        self.case_uuid = case_uuid

    def __repr__(self):
        return f'MeshDataAPI<case_uuid={self.case_uuid}>'

    def _get_text(self, case_uuid=None, text=None):

        if text:
            return re.sub(r'[^A-z0-9]+', ' ', text)

        if case_uuid is None:
            raise ValueError("Case uuid is required if text is not passed")

        for c in self.session.query(Content) \
                .filter(Content.case_uuid == case_uuid, Content.deleted_at.is_(None)) \
                .all():
            content_caption = ""
            if c.caption is None:
                continue
            if c.translation:
                for t in c.translation:
                    if t.target_language == Locale.EN_US.code:
                        if t.caption:
                            content_caption = t.caption
            else:
                content_caption = c.caption
            return re.sub(r'[^A-z0-9]+', ' ', content_caption)
        return None

    @staticmethod
    def fix_alternate_label(mesh_term):
        """
        If a mesh terms uses an alternate, usually last term first, then comma, then the first term ( Arrest, Cardiac
        instead of Cardiac Arrest for example.)
        Unfortunately, this means that it won't be found, so this just switch the terms if there is a comma, otherwise
        the original term is returned.

        """
        label_match = re.match(r'([a-zA-Z0-9]+)\s*,\s*([a-zA-Z0-9]+)', mesh_term)
        if label_match:
            return f'{label_match.group(2)} {label_match.group(1)}'
        else:
            return mesh_term

    @staticmethod
    def lookup_mesh_term(mesh_term, alternate=True, match_type='exact'):
        """
        Try to find a match for a mesh term.
        See https://id.nlm.nih.gov/mesh/swagger/ui for details
        Returns an empty list if no results, or a list of dicts with the form
        {'resource': 'Term Url',
         'label': 'Term Label'}

         If alternate is set to True, then attempt to correct the alternate label, this means that if there is a comma,
         flip the terms around and remove the comma so Arrest, Heart becomes Heart Arrest.

         match_type defaults to 'exact', but can also be 'contains' or 'startswith'
        """

        match_type = 'exact'
        limit = 1
        if alternate is True:
            label = MeshDataAPI.fix_alternate_label(mesh_term)
        else:
            label = mesh_term
        resp = requests.get(url='https://id.nlm.nih.gov/mesh/lookup/term',
                            params=dict(match_type=match_type, limit=limit, label=label),
                            headers=dict(accept='application/json'))
        return resp.json()

    def get_mesh_data_for_case(self, mesh_text=None, case_uuid=None) -> Tuple[MeshTermsModel, ...]:
        if mesh_text:
            text = self._get_text(text=mesh_text)
        elif case_uuid:
            text = self._get_text(case_uuid=case_uuid)
        else:
            text = self._get_text(case_uuid=self.case_uuid)
        logger.debug("Submitting text %s", text)
        if not text:
            raise MeshError('No text found for case')
        for mesh_term, mesh_type in self.get_mesh_codes(text=text):
            logger.debug("Yielding mesh term %s", mesh_term)
            yield mesh_term, mesh_type

    def _add_concept(self, concept_id):
        """
        Adds a new concept and any new terms required and joins the terms with the concepts through a joining table
        """
        if PublicMeshConcepts.q.get(concept_id):
            logger.debug("Concept %s exists, nothing to do", concept_id)
            return
        else:
            concept = self.parse_concept_terms(concept_id)
            logger.debug("Got concept %s", concept.dict())
            self._add_term(concept.preferredTerm)
            if concept.terms:
                for t in concept.terms:
                    self._add_term(t)

        mesh_concept = PublicMeshConcepts()
        mesh_concept.mesh_concept_id = concept_id

        mesh_concept.scope_note = concept.scopeNote.value if concept.scopeNote else None
        self.session.add(mesh_concept)

        self.session.flush()
        preferred_concept_term = PublicMeshConceptTerms()
        preferred_concept_term.mesh_concept_id = concept_id
        preferred_concept_term.mesh_term_id = concept.preferredTerm
        preferred_concept_term.mesh_preferred_term_id = concept.preferredTerm
        self.session.add(preferred_concept_term)
        if concept.terms:
            for term in concept.terms:
                concept_term = PublicMeshConceptTerms()
                concept_term.mesh_concept_id = concept_id
                concept_term.mesh_term_id = term
                concept_term.mesh_preferred_term_id = concept.preferredTerm
                self.session.add(concept_term)
        self.session.flush()

    def _add_term(self, term_id):
        """
        If the term does not exist, then add it.
        """
        if PublicMeshTerms.q.get(term_id):
            logger.debug("Term %s exists, nothing to do", term_id)
            return
        else:
            term = self.parse_term(term_id)
            logger.debug("Got term %s from term_id %s", term.dict(), term_id)
            t = PublicMeshTerms()
            t.mesh_term_id = term_id
            if term.preferredLabel:
                t.preferred_label = term.preferredLabel.value
            else:
                logger.error("No preferred label populated")
                return
            if term.alternateLabel:
                t.alternate_label = term.alternateLabel.value
            self.session.add(t)
            self.session.flush()
            logger.debug("Added term %s to database", term_id)

    def add_term(self, term, alternate=True, attempts=0) -> Optional[str]:
        """Add a new term

        When called, this function assumes the term table has been checked and immediately executes a search. If
        the term is found, the code for it is returned, otherwise None is returned.

        :param term: Mesh term to search for
        :type term: str

        :param alternate: If alternate is True, an attempt is made to correct the term, if false, use the term as is.
        :type alternate: bool

        :param attempts: This is a recursion catch, if attempts increments to 2, the function just exits.
        :param attempts: int

        :return: The term code matching the term or None
        :rtype: Optional[str]
        """
        if attempts > 1:
            logger.error("Max recursion depth reached searching for term %s", term)
            return None

        resp = MeshDataAPI.lookup_mesh_term(term, alternate=alternate)
        if isinstance(resp, list) and len(resp) == 1:
            term_resource = resp[0].get('resource', None)
            if term_resource:
                term_code = self._get_code_from_url(term_resource)
                if term_code:
                    self._add_term(term_code)
                    logger.info("Added term code %s", term_code)
                    return term_code
                else:
                    logger.error("No term code found in url %s", term_resource)
            else:
                logger.error("No resource found in return %s", resp)
        else:
            logger.error("No results found for search %s", term)
            attempts += 1
            return self.add_term(term, alternate=False, attempts=attempts)
        return None

    def parse_mesh_data(self):
        """
        Add mesh terms to the database if needed, link to cases.
        """
        logger.info("Fetching mesh data for case %s", self.case_uuid)
        for mesh_code, mesh_type in self.get_mesh_data_for_case():
            logger.debug("Handling mesh code %s", mesh_code)
            mesh_entry = PublicMesh.q.get(mesh_code)
            if not mesh_entry:
                logger.debug("No mesh entry for %s", mesh_code)
                msh = self.get_mesh_object(mesh_code)
                logger.debug("Adding concept from model %s", msh.dict())
                self._add_concept(msh.preferredConcept)

                mesh_entry = PublicMesh()
                mesh_entry.preferredTerm = msh.preferredTerm
                mesh_entry.preferredConcept = msh.preferredConcept
                mesh_entry.mesh_id = mesh_code
                self.session.add(mesh_entry)

            case_mesh_link = CaseMeshTerms()
            case_mesh_link.case_uuid = self.case_uuid
            case_mesh_link.mesh_term_id = mesh_entry.preferredTerm
            case_mesh_link.mesh_id = mesh_code
            case_mesh_link.deleted_at = None
            case_mesh_link.mesh_term_type = mesh_type
            self.session.merge(case_mesh_link)
            self.session.flush()


class PublicationSearch:
    search_endpoint = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    summary_endpoint = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi'
    retmode = 'json'

    @staticmethod
    def _execute_search(url, params):
        resp = requests.get(url=url, params=params)
        if resp.status_code == 429:
            logger.error("Search rate limited - retry in 5 seconds")
            raise PublicationSearchOverloaded
        logger.debug("Search response %s", resp.json())
        logger.info("Search rate limit remaining: %s", resp.headers.get('x-ratelimit-remaining', 0))
        return resp.json()

    @classmethod
    def search_terms(cls, terms=None, db='pubmed', field='MeSH Terms') -> PublicationSearchResult:
        """Search pubmed for mesh terms

        Given a list of mesh terms, looks for them in the pubmed database. See
        https://pubmed.ncbi.nlm.nih.gov/help/#search-tags for valid field names/tags.

        :param terms: List of mesh terms to search for
        :type terms: list

        :param db: Search this database, defaults to pubmed
        :type db: str

        :param field: The field to search, usually the default is what you want. [Currently ignored, do not use]
        :type field: str

        :return: Returns a populated PublicationSearchResult model
        :rtype: PublicationSearchResult
        :raises PublicationSearchOverloaded: Retry in 5 seconds if this exception is raised
        """

        if not terms:
            raise ValueError("Terms to search for are mandatory")

        if not isinstance(terms, list):
            logger.error("Terms must be a list")
            raise ValueError("Terms must be a list")

        search_terms = ','.join([f'{t}' for t in terms])

        params = dict(db=db, retmode=cls.retmode, term=search_terms)

        search_result = PublicationSearch._execute_search(url=cls.search_endpoint, params=params)

        return PublicationSearchResult.parse_obj(search_result)

    @classmethod
    def lookup_summary(cls, pubmedIds=None, db='pubmed') -> Iterator[PublicationSummaryResult]:
        """
        Looks up pubmed ids to fetch the title and other data as requested.

        :param pubmedIds:
        :type pubmedIds: list

        :param db:
        :type db: str

        :return: Returns a populated PublicationSummaryResult model or a Value error if the arguments are wrong
        :rtype: PublicationSummaryResult
        """

        if not pubmedIds:
            raise ValueError('No pubmed identifiers passed')

        if not isinstance(pubmedIds, list):
            raise ValueError('Pubmed id must be a list')

        deduplicated_list = list(set(pubmedIds))
        for lookup_list in split_list_to_smaller_lists(deduplicated_list, chunk_size=499):
            search_terms = ','.join(lookup_list)
            params = dict(db=db, retmode=cls.retmode, id=search_terms)
            search_result = PublicationSearch._execute_search(url=cls.summary_endpoint, params=params)
            yield PublicationSummaryResult.parse_obj(search_result)
