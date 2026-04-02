from pydantic import validator, Field

from figure1.common.helpers import GroupManagement, UserDocument
from figure1.common.models.db import Groups
from figure1.core import FirestoreSyncBase
from figure1.common.types import GroupModel
from figure1.core import celery_app, TaskBase


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.sync_single_group')
def sync_single_group_task(self, group_uuid):
    sync_single_group(group_uuid, self.session)


def sync_single_group(group_uuid, session):
    FirestoreGroups(group_uuid=group_uuid).firestore_write(session=session)
    FirestoreReferenceGroups(group_uuid=group_uuid).firestore_write(session=session, merge=True)


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.sync_single_group_member')
def sync_single_group_member_task(self, group_uuid, user_uuid):
    sync_single_group_member(group_uuid, user_uuid, self.session)


def sync_single_group_member(group_uuid, user_uuid, session):
    FirestoreGroupMember(group_uuid=group_uuid, user_uuid=user_uuid).firestore_write(session=session)
    FirestoreGroups(group_uuid=group_uuid).firestore_update_members_count(session=session)
    FirestoreReferenceGroups(group_uuid=group_uuid).firestore_write(session=session, merge=True)


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.delete_single_group')
def delete_single_group_task(self, group_uuid):
    delete_single_group(group_uuid)


def delete_single_group(group_uuid):
    FirestoreGroups(group_uuid=group_uuid).firestore_reset()
    FirestoreReferenceGroups(group_uuid=group_uuid).firestore_reset()


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.delete_single_group_member')
def delete_single_group_member_task(self, group_uuid, user_uuid):
    delete_single_group_member(group_uuid, user_uuid, self.session)


def delete_single_group_member(group_uuid, user_uuid, session):
    FirestoreGroupMember(group_uuid=group_uuid, user_uuid=user_uuid).firestore_reset()
    FirestoreGroups(group_uuid=group_uuid).firestore_update_members_count(session=session)
    FirestoreReferenceGroups(group_uuid=group_uuid).firestore_write(session=session, merge=True)


class FirestoreGroups(FirestoreSyncBase):
    """
    Handles syncing group to firestore
    """
    groupUuid: str = Field(alias='group_uuid')

    @validator('groupUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @property
    def firestore_doc_reference(self):
        return self.fs_client \
            .collection('groupsDB') \
            .document(self.groupUuid)

    def generate_firestore_document(self, session=None):
        return GroupManagement.get_group(group_uuid=self.groupUuid, session=session) \
            .dict(exclude={"groupMembers", "groupVisibleMembers", "groupFilters"})

    def firestore_update_members_count(self, session=None):
        group_dict = self.generate_firestore_document(session)
        self.firestore_doc_reference.update({'membersCount': group_dict['membersCount']})

    def firestore_reset(self, **kwargs):
        self.firestore_doc_reference.delete()


class FirestoreReferenceGroups(FirestoreSyncBase):
    """
    Handles syncing groups to firestore referenceDB
    """
    groupUuid: str = Field(alias='group_uuid')

    @validator('groupUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @property
    def firestore_doc_reference(self):
        return self.fs_client \
            .collection('referenceData') \
            .document('groups')

    def generate_firestore_document(self, session=None):
        group_dict = GroupManagement.get_group(group_uuid=self.groupUuid, session=session) \
            .dict(exclude={"groupMembers", "groupVisibleMembers", "groupFilters"})
        group_dict["isActive"] = group_dict.pop("groupActive")

        return {self.groupUuid: group_dict}

    def firestore_reset(self, **kwargs):
        doc_dict = self.firestore_doc_reference.get().to_dict()

        if self.groupUuid in doc_dict:
            del doc_dict[self.groupUuid]

        self.firestore_doc_reference.set(doc_dict, merge=False)


class FirestoreGroupMember(FirestoreSyncBase):
    """
    Handles syncing group member to firestore
    """
    groupUuid: str = Field(alias='group_uuid')
    userUuid: str = Field(alias='user_uuid')

    @validator('groupUuid', 'userUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @property
    def firestore_doc_reference(self):
        return self.fs_client \
            .collection('groupsDB') \
            .document(self.groupUuid) \
            .collection('members') \
            .document(self.userUuid)

    def generate_firestore_document(self, session=None):
        return GroupManagement.get_group_member_by_user_uuid_as_dict(group_uuid=self.groupUuid,
                                                                     user_uuid=self.userUuid,
                                                                     session=session)

    def firestore_reset(self, **kwargs):
        self.firestore_doc_reference.delete()
