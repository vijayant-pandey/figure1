from typing import Optional, List, Union
from pydantic import BaseModel, Field, validator
import re


class MeshNote(BaseModel):
    """
    Several different fields use this structure such as label, scopeNote and some others
    """
    language: Optional[str] = Field(alias='@language')
    value: Optional[str] = Field(alias='@value')


class MeshModel(BaseModel):
    """
    Handles the response from the mesh identifier.
    """
    preferredTerm: Optional[str] = Field(alias='preferredTerm')
    preferredConcept: Optional[str] = Field(alias='preferredConcept')
    meshId: Optional[str] = Field(alias='identifier')
    label: Optional[MeshNote]

    @validator('preferredTerm', 'preferredConcept', pre=True)
    def validate_url(cls, value):
        if not value:
            return
        code = value.split('/')[-1]
        if re.match(r'^[ATM]\d+$', code):
            return code
        else:
            raise ValueError("No valid mesh code found")


class MeshTermsModel(BaseModel):
    active: Optional[bool] = True
    preferredLabel: Optional[MeshNote] = Field(alias='prefLabel')
    alternateLabel: Optional[MeshNote] = Field(alias='altLabel')


class MeshConceptModel(BaseModel):
    preferredTerm: Optional[str]
    terms: Optional[Union[List, str]] = Field(alias='term')
    scopeNote: Optional[MeshNote]

    @validator('terms', pre=True)
    def parse_term(cls, value):
        def _parse_code_from_url(url):
            code = url.split('/')[-1]
            if re.match(r'^[ATM]\d+$', code):
                return code
            else:
                raise ValueError('Failed to find valid code in url')

        if not value:
            return
        if isinstance(value, list):
            return [_parse_code_from_url(x) for x in value]
        if isinstance(value, str):
            return [_parse_code_from_url(value)]
        raise ValueError("Invalid value passed")

    @validator('preferredTerm', pre=True)
    def parse_preferred_term(cls, value):
        v = cls.parse_term(value)
        return v[0]


class PublicationSearchResult(BaseModel):
    resultCount: Optional[int] = Field(alias='count')
    maxReturn: Optional[int] = Field(alias='retmax')
    resultStart: Optional[int] = Field(alias='retstart')
    pubMedIds: Optional[List[str]] = Field(alias='idlist', regex=r'[0-9]*')

    def __init__(self, **kwargs):
        """
        Override the pydantic init call to collapse the structure for search results
        :param kwargs:
        """
        search_results = kwargs.get('esearchresult', {})
        kwargs.update({**search_results})
        super().__init__(**kwargs)


class PublicationSummary(BaseModel):
    pubMedId: int = Field(alias='uid')
    journalName: Optional[str] = Field(alias='fulljournalname')
    title: Optional[str] = Field(alias='title')
    error: Optional[str]


class PublicationSummaryResult(BaseModel):
    resultUids: Optional[List[int]] = Field(alias='uids')
    results: Optional[List[PublicationSummary]]

    def __init__(self, **kwargs):
        """
        Override the init call so we can sanitize the result from the search
        :param kwargs:
        """
        result_uids = kwargs.get("result", {})
        kwargs.update({**result_uids})
        kwargs.update({'results': []})
        for k, v in kwargs.get("result", {}).items():
            if k == 'uids':
                continue
            kwargs['results'].append(v)

        super().__init__(**kwargs)
