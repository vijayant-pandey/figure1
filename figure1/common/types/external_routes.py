from typing import Optional
from jinja2 import Environment
from pydantic import BaseModel, HttpUrl, root_validator, AnyUrl
from figure1.configuration import app_settings

template_env = Environment()


class Figure1Url(AnyUrl):
    allowed_schemes = {'figure1pro', 'https'}


class WebAppRoutes(BaseModel):
    """
    This is taken from pro-web-client/src/constants/routes.js in the pro-web-client repository

    Each of the urls are run through the jinja2 template engine before being returned, anything in the model can be
    used as part of the template.

    caseUuid is the case to point to for detail views
    userUuid is the user to whom this is being displayed, this populates user profile links
    targetUserUuid is a different user from the one being displayed, used to direct users to another profile

    """
    caseUuid: Optional[str]
    userUuid: Optional[str]

    root_url: Figure1Url = app_settings.external_webapp_url
    sign_in: Figure1Url = "{{root_url}}/login"
    sign_up: Figure1Url = "{{root_url}}/registration/new"

    home: Figure1Url = "{{root_url}}/home"

    cme_home: Figure1Url = "{{ root_url }}/cme"

    cme_link: Figure1Url = "{{root_url }}/cme/{{ caseUuid }}"

    clinical_moments_home: Figure1Url = "{{ root_url }}/clinical-moments"

    clinical_moments_link: Figure1Url = "{{ root_url }}/clinical-moments/{{ caseUuid }}"

    profile_detail_path: str = "/profile"
    profile_detail: Figure1Url = "{{ root_url }}{{ profile_detail_path }}/{{ userUuid }}"

    case_detail_path: str = "/cases"
    case_detail: Figure1Url = "{{ root_url }}{{ case_detail_path }}/{{ caseUuid }}"

    @root_validator()
    def generate_templates(cls, values):
        """
        Populate any templates, the template variables must be part of the model
        :param values:
        :return:
        """
        for v in values:
            tmpl = template_env.from_string(str(values[v]))
            values[v] = tmpl.render(values)
        return values


class MobileAppRoutes(WebAppRoutes):
    root_url: Figure1Url = app_settings.external_mobileapp_url

    home: Figure1Url = "{{root_url}}/feed/rfy"

    profile_detail_path: str = "/user/detail"

    profile_detail: Figure1Url = "{{ root_url }}{{ profile_detail_path }}/{{ userUuid }}"

    case_detail: Figure1Url = "{{ root_url }}{{ case_detail_path }}/{{ caseUuid }}"
