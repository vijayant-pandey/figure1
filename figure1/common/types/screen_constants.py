from enum import Enum

UNKNOWN_SCREEN = "unknownScreen"


class ProfileUpdateSections(Enum):
    PROFILE_EMAIL_UPDATE = "emailUpdated"
    PROFILE_BASIC_INFO_UPDATE = "basicProfileUpdated"
    PROFILE_EXPERIENCE_UPDATE = "profileExperience"
    PROFILE_EDUCATION_UPDATE = "profileEducation"
    PROFILE_AFFILIATIONS_UPDATE = "profileAffiliations"
    PROFILE_INTERESTS_UPDATE = "profileInterests"

    @staticmethod
    def list():
        return list(map(lambda c: c.value, ProfileUpdateSections))


class RegistrationSections(Enum):
    REGISTRATION_STARTED = "registrationStarted"
    REGISTRATION_USERNAME = "registrationUsername"
    REGISTRATION_SPECIALTY_SELECTIONS = "registrationSpecialtySelections"
    REGISTRATION_TOPIC_SELECTED = "registrationTopicsSelected"
    REGISTRATION_NOTIFICATION_CHOICE_SELECTED = "verifyNotificationChoiceCompleted"

    REGISTRATION_NPI = "registrationNPISelected"
    REGISTRATION_MED_LICENSE = "registrationMedLicenseSelected"
    REGISTRATION_BADGE = "registrationBadgeSelected"

    REGISTRATION_NPI_COMPLETED = "registrationNPIDetailsCompleted"
    REGISTRATION_MED_LICENSE_COMPLETED = "registrationMedLicenseDetailsCompleted"
    REGISTRATION_BADGE_COMPLETED = "registrationBadgeDetailsCompleted"

    REGISTRATION_BADGE_UPLOADED = "registrationPictureUploaded"
    REGISTRATION_INSTITUTIONAL_EMAIL_COMPLETED = "registrationInstitutionalEmailCompleted"
    REGISTRATION_COMPLETED = "registrationCompleted"

    @staticmethod
    def sync_only_list():
        return list(map(lambda c: c.value, RegistrationSections))


class CasePostingScreens(Enum):
    NEW_CASE_POST = "newCasePost"
    NEW_PAGING_CASE = "newPagingCasePost"
    CASE_CREATED = "caseCreated"
    DRAFT_SAVED = "draftSaved"
    CASE_UPDATED = "caseUpdated"
    CASE_SUBMITTED_FOR_MODERATION = "caseSubmittedForModeration"

    @staticmethod
    def draft_list():
        return list(map(lambda c: c.value, CasePostingScreens))
