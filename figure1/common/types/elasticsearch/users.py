from elasticsearch_dsl import Keyword, Document, Text, Boolean, Date, Object, Long, Nested, InnerDoc, Completion
from figure1.configuration import es_settings


class UserProfession(InnerDoc):
    professionName = Text()
    professionLabel = Text()
    professionUuid = Keyword()
    professionCategoryName = Text()
    professionCategoryLabel = Text()


class UserSpecialty(InnerDoc):
    specialtyName = Text()
    specialtyLabel = Text()
    specialtyUuid = Keyword()
    isValidInterest = Boolean()
    isValidCaseTag = Boolean()


class UserPrimarySpecialtyTree(InnerDoc):
    treeUuid = Keyword()
    treeName = Text()
    displayOrder = Long()
    onboardingDisplayName = Text()
    profileDisplayName = Text()
    caseCommentDisplayName = Text()
    profession = Object(UserProfession)
    specialty = Object(UserSpecialty)
    subspecialty = Object(UserSpecialty)


class UserPrimarySpecialty(InnerDoc):
    treeUuid = Keyword()
    onboardingDisplayName = Text()
    profileDisplayName = Text()
    caseCommentDisplayName = Text()
    isPrimary = Boolean()
    tree = Object(UserPrimarySpecialtyTree)


class UserNestedInterests(InnerDoc):
    interestUuid = Keyword()
    interestName = Text()


class UserGroups(InnerDoc):
    groupUuid = Keyword()


class UserVerificationHistory(InnerDoc):
    verificationEventInititator = Keyword()
    verificationEventDescription = Keyword()
    verificationEventUuid = Keyword()
    verificationEventInitiatorUsername = Keyword()
    verificationEventCreatedAt = Keyword()


class UserVerificationNPI(InnerDoc):
    npiNumber = Long()
    npiEnumerationDate = Keyword()
    npiLastUpdate = Keyword()


class UserVerificationLicense(InnerDoc):
    licenseNumber = Keyword()


class UserProfessionChangeRequest(InnerDoc):
    professionTreeUuid = Keyword()
    requestResolved = Boolean()


class UserVerificationInstitutionalEmail(InnerDoc):
    email = Keyword()


class UserVerificationModeratorNotes(InnerDoc):
    createdAt = Date()
    noteUuid = Keyword()
    moderatorUuid = Keyword()
    moderatorUid = Keyword()
    moderatorUsername = Keyword()
    moderatorName = Keyword()
    text = Text()


class UserVerificationModeratorTags(InnerDoc):
    userUuid = Keyword()
    tagUuid = Keyword()
    moderatorUuid = Keyword()
    tagName = Keyword()


class UserVerificationDocument(InnerDoc):
    verificationStatus = Keyword()
    verificationUuid = Keyword()
    verificationType = Keyword()
    verificationFlaggedForReview = Boolean()
    verificationHistory = Object(UserVerificationHistory)
    archivedVerificationUuid = Keyword()
    npi = Object(UserVerificationNPI)
    license = Object(UserVerificationLicense)
    professionChangeRequest = Object(UserProfessionChangeRequest)
    institutionalEmail = Object(UserVerificationInstitutionalEmail)
    verificationPhoto = Keyword(multi=True)
    verificationCreatedAt = Date()
    verificationUpdatedAt = Date()
    graduationYear = Keyword()
    schoolName = Text()
    schoolUuid = Keyword()


class ESUserDocument(Document):
    class Index:
        name = es_settings.users_alias

    userUuid = Keyword(required=True)
    userUid = Keyword()
    username = Keyword(fields={'text': Text()})
    userType = Keyword()
    fullName = Text()
    displayName = Text()
    firstName = Keyword(copy_to='fullName', fields={'text': Text()})
    lastName = Keyword(copy_to='fullName', fields={'text': Text()})
    activityCount = Long()
    approvedCaseCount = Long()
    approvedCommentCount = Long()
    groups = Object(UserGroups)
    email = Keyword(fields={'text': Text()})
    userCustomSchool = Text()
    userCustomSpecialty = Text()
    avatar = Keyword()
    userBio = Text()
    madeForYouSpecialties = Keyword(multi=True)
    primarySpecialty = Object(UserPrimarySpecialty)
    professionName = Text()
    userProfessionUuid = Keyword()
    specialtyName = Text()
    userSpecialtyUuid = Keyword()
    subspecialtyName = Keyword()
    userSubSpecialtyUuid = Keyword()
    userHiddenFromSearch = Boolean()
    verificationStatus = Keyword()
    verificationType = Keyword()
    verificationPhoto = Keyword(multi=True)
    verificationCreatedAt = Date()
    verificationUpdatedAt = Date()
    verificationFlaggedForReview = Boolean()
    verificationNotes = Object(UserVerificationModeratorNotes)
    verificationTags = Object(UserVerificationModeratorTags)
    institutionalEmail = Object(UserVerificationInstitutionalEmail)
    graduationDate = Keyword()
    npiNumber = Long()
    npiFirstName = Text()
    npiLastName = Text()
    npiDuplicatedBy = Keyword(multi=True)
    lastSeen = Date()
    caseComments = Keyword(multi=True)
    caseCommentsTopMeshTerms = Keyword(multi=True)
    caseCommentsTopSpecialties = Keyword(multi=True)
    caseReactions = Keyword(multi=True)
    caseReactionsTopMeshTerms = Keyword(multi=True)
    caseReactionsTopSpecialties = Keyword(multi=True)
    caseSaved = Keyword(multi=True)
    caseSavedTopMeshTerms = Keyword(multi=True)
    caseSavedTopSpecialties = Keyword(multi=True)
    caseDetailViews = Keyword(multi=True)
    caseDetailViewsTopMeshTerms = Keyword(multi=True)
    caseDetailViewsTopSpecialties = Keyword(multi=True)
    sponsoredContentDetailViews = Keyword(multi=True)
    userInterests = Keyword(multi=True)
    userSecondaryInterests = Keyword(multi=True)
    userInterestsProfession = Keyword(multi=True)
    userInterestSpecialty = Keyword(multi=True)
    interests = Nested(UserNestedInterests)
    verification = Object(UserVerificationDocument)
    archivedVerification = Object(UserVerificationDocument)
