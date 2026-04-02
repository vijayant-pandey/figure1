import logging

import requests
from pydantic import ValidationError
from pydantic import BaseModel, validator, Field, root_validator
from typing import Optional, List
from datetime import date
from figure1.common.types import SpecialtyTreeModel
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.models.db import SpecialtyTaxonomyMap
from figure1.exceptions.verification import NPIAPIError, InvalidAPIResponse

logger = logging.getLogger('figure1.npi.api')


class NPIResponseItemSummary(BaseModel):
    """
    An abridged version of NPIResponseItem, intended to be passed to clients
    """
    firstName: Optional[str] = Field(alias='first_name')
    lastName: Optional[str] = Field(alias='last_name')
    npiNumber: int = Field(alias='number')
    specialty: Optional[SpecialtyTreeModel]

    @validator('firstName', 'lastName', pre=True)
    def capitalize(cls, value):
        return value.capitalize() if value else None

    @root_validator(pre=True)
    def handle_properties(cls, values):
        basic = values.get('basic')
        if basic:
            values['first_name'] = basic.first_name
            values['last_name'] = basic.last_name
        return values


class NPIResponseSummary(BaseModel):
    """
    An abridged version of NPIResponse, intended to be passed to clients
    """
    resultCount: int
    results: List[NPIResponseItemSummary]


class NPIRequest(BaseModel):
    """
    Models a request to the NPI API
    """
    address_purpose: Optional[str]
    city: Optional[str]
    country_code: Optional[str]
    enumeration_type: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    number: Optional[str]
    organization_name: Optional[str]
    postal_code: Optional[str]
    state: Optional[str]
    taxonomy_description: Optional[str]
    use_first_name_alias: Optional[str]


class NPIResponseTaxonomy(BaseModel):
    """
    Models data returned from the NPI API
    """
    code: Optional[str]
    desc: Optional[str]
    license: Optional[str]
    primary: bool
    state: Optional[str]

    def get_specialty_from_code(self) -> Optional[SpecialtyTreeModel]:
        if not self.code:
            return None
        specialty_tree_uuid = SpecialtyTaxonomyMap.q.filter(SpecialtyTaxonomyMap.taxonomy_code == self.code) \
            .one_or_none()
        if specialty_tree_uuid:
            tree = SpecialtyTreeV2.q.filter(SpecialtyTreeV2.specialty_uuid == specialty_tree_uuid.specialty_tree_uuid,
                                            SpecialtyTreeV2.specialty_type == 'tree') \
                .one_or_none()
            if tree:
                return tree.as_object()
        return None


class NPIResponseBasic(BaseModel):
    """
    Models data returned from the NPI API
    """
    first_name: Optional[str]
    middle_name: Optional[str]
    last_name: Optional[str]
    gender: Optional[str]
    enumeration_date: date
    last_updated: date
    deactivation_date: Optional[date]
    reactivation_date: Optional[date]


class NPIResponseAddress(BaseModel):
    """
    Models data returned from the NPI API
    """
    postal_code: Optional[str]
    address_1: Optional[str]
    address_2: Optional[str]
    address_purpose: Optional[str]
    city: Optional[str]
    country_code: Optional[str]
    state: Optional[str]


class NPIResponseItem(BaseModel):
    """
    Models data returned from the NPI API
    """
    number: int
    basic: NPIResponseBasic
    addresses: List[NPIResponseAddress]
    taxonomies: List[NPIResponseTaxonomy]
    enumeration_type: Optional[str]


class NPIResponse(BaseModel):
    """
    Models data returned from the NPI API
    """
    result_count: int
    results: List[NPIResponseItem]

    def to_summary(self) -> NPIResponseSummary:
        summary_results = []
        count = 0
        if self.results:
            for r in self.results:
                if r.enumeration_type == 'NPI-2':
                    continue

                specialty_object = None
                for taxonomy in r.taxonomies:
                    specialty_object = taxonomy.get_specialty_from_code()
                    if specialty_object:
                        break
                result = NPIResponseItemSummary.parse_obj(r)
                result.specialty = specialty_object
                summary_results.append(result)
                count += 1
        return NPIResponseSummary(
            resultCount=count,
            results=summary_results
        )


class NpiAPI:
    @staticmethod
    def get_info(npi_request: NPIRequest) -> NPIResponse:
        """
        Fetches data from the NPI API and returns the response object
        :raises ValueError, NPIAPIError:
        :param npi_request: NPIRequest
        :return: NPIResponse
        """
        params = npi_request.dict(exclude_none=True)
        params['version'] = '2.1'

        r = requests.get('https://npiregistry.cms.hhs.gov/api', params=params)

        if r.status_code != 200:
            logger.error(f"NPI API returned non-200 status code {r.status_code}")
            raise NPIAPIError(return_code=r.status_code, npi=params.get('number'))

        try:
            response = r.json()
        except ValueError as ve:
            logger.error("Failed to decode response %s", ve)
            raise

        if response.get('Errors'):
            logger.error(f"NPI request for '%s' failed with %s", params, response.get('Errors'))
            raise NPIAPIError()

        try:
            return NPIResponse.parse_obj(response)
        except ValidationError as ve:
            logging.error("Validation failed with error %s", ve)
            raise InvalidAPIResponse(npi=params.get('number'))
