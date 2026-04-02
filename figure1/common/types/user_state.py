import abc
import logging
from enum import Enum

from figure1.configuration import app_settings


def _has_valid_specialty(user) -> bool:
    """
    Returns True if the user's primary specialty contains a specialty valid for proceeding through onboarding.

    This may be False if a specialty is not set, or if the one set is an 'unmapped specialty' that requires the user to
    provide a more specific specialty.  This is intended to handle legacy users.

    Some profession categories do not require a specialty and are also considered valid.
    :param user:
    :return:
    """
    categories_without_specialties = ['Other HCP', 'Other Student']
    unmapped_specialties = ['otherspecialist']

    primary_specialty = user.primary_specialty
    if not primary_specialty:
        return False
    elif primary_specialty.tree.profession.profession_category in categories_without_specialties:
        return True
    elif not primary_specialty.tree.specialty_v2_uuid:
        return False
    elif primary_specialty.tree.specialty.label in unmapped_specialties \
            and not primary_specialty.tree.subspecialty_uuid:
        return False
    else:
        return True


class OnboardingStateBase:
    @staticmethod
    @abc.abstractmethod
    def has_required_data(user) -> bool:
        """
        Returns True if the user has the data required to move to the next OnboardingState
        """
        pass


class CountryState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        return user.user_profile.country_uuid


class USAInformationState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        return user.first_name and \
               user.last_name and \
               _has_valid_specialty(user)


class InformationState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        return user.first_name and \
               user.last_name and \
               _has_valid_specialty(user)


class GradDateState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        if user.is_student:
            return user.user_profile.graduation_date is not None

        return True


class VerificationState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        return user.user_verification is not None


class ConfirmationState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        return user.user_verification is not None


class UsernameState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        return user.username


class CompletedState(OnboardingStateBase):
    @staticmethod
    def has_required_data(user) -> bool:
        return True


class OnboardingState(Enum):
    COUNTRY = "country"
    USA_INFORMATION = "usa_information"
    INFORMATION = "information"
    VERIFICATION = "verification"
    CONFIRMATION = "confirmation"
    USERNAME = "username"
    COMPLETED = "completed"
    GRAD_DATE = "grad_date"

    def has_required_data(self, user):
        if self == OnboardingState.COUNTRY and CountryState.has_required_data(user):
            return True
        elif self == OnboardingState.USA_INFORMATION and USAInformationState.has_required_data(user):
            return True
        elif self == OnboardingState.INFORMATION and InformationState.has_required_data(user):
            return True
        elif self == OnboardingState.GRAD_DATE and GradDateState.has_required_data(user):
            return True
        elif self == OnboardingState.VERIFICATION and VerificationState.has_required_data(user):
            return True
        elif self == OnboardingState.CONFIRMATION and ConfirmationState.has_required_data(user):
            return True
        elif self == OnboardingState.USERNAME and UsernameState.has_required_data(user):
            return True
        elif self == OnboardingState.COMPLETED and CompletedState.has_required_data(user):
            return True
        else:
            return False
