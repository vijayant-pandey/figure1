class GroupException(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 406)
        self.msg = kwargs.get('msg', 'group error')
        self.group_name = kwargs.get('group_name', '')
        self.group_label = kwargs.get('group_label', '')
        self.group_uuid = kwargs.get('group_uuid', '')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class GroupNotFound(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'group not found')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class GroupMemberNotFound(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'error, member is not part of the group')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class GroupUploadError(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 501)
        self.msg = kwargs.get('msg', 'error uploading a case')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class DuplicateGroupName(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 409)
        self.msg = kwargs.get('msg', 'Duplicate group name exists')
        self.group_name = kwargs.get('group_name', '')

    def __str__(self):
        return f"Failed to create group with name {self.group_name}: {self.msg}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg, 'error': self.msg}


class InvalidGroupMembersFile(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.msg = kwargs.get('msg', 'Invalid group members file')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class InvalidGroupType(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.msg = kwargs.get('msg', 'Invalid group type')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class GroupInactive(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.msg = kwargs.get('msg', 'Group is not active')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class UserError(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'User not found')
        self.user_uuid = kwargs.get('user_uuid', '')
        self.user_uid = kwargs.get('user_uid', '')
        self.username = kwargs.get('username', '')
        self.email = kwargs.get('email', '')
        self.ratio = kwargs.get('ratio', '')

    def __str__(self):
        return f"Failed to find user with UID {self.user_uid} or uuid {self.user_uuid}: {self.msg}"

    def __repr__(self):
        return f"Raised error {self.msg} - return code {self.rc}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg, 'error': self.msg}


class DuplicateUser(UserError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 409)
        self.msg = kwargs.get('msg', 'Duplicate user exists')
        self.user_uuid = kwargs.get('user_uuid', '')
        self.user_uid = kwargs.get('user_uid', '')

    def __str__(self):
        return f"Failed to create user with UID {self.user_uid}: {self.msg}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg, 'error': self.msg}


class UserNotFound(UserError):
    def __str__(self):
        return f"General user error - {self.msg}"


class UsernameValidation(UserError):
    def __str__(self):
        return f" Username can not be used! - {self.msg}: {self.username} :{self.rc}: {self.ratio}"


class UserUIDNotFound(UserNotFound):
    def __str__(self):
        return f"Failed to find user with UID {self.user_uid}: {self.msg}"


class UserUUIDNotFound(UserNotFound):
    def __str__(self):
        return f"Failed to find user with UUID {self.user_uuid}: {self.msg}"


class UserUsernameNotFound(UserNotFound):
    def __str__(self):
        return f"Failed to find user with username {self.username}: {self.msg}"


class UserEmailNotFound(UserNotFound):
    def __str__(self):
        return f"Failed to find user with email {self.email}: {self.msg}"


class UserDeleted(UserError):
    def __str__(self):
        return f"User {self.user_uid} has been deleted: {self.msg}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg, 'error': self.msg}


class InvalidUserType(UserError):
    def __str__(self):
        return f"Invalid user type: {self.msg}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg, 'error': self.msg}


class InvalidOnboardingState(UserError):
    def __str__(self):
        return f"Invalid onboarding state: {self.msg}"


class InsufficientPermissions(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.pop('return_code', 403)
        self.msg = kwargs.pop('msg', 'Insufficient permissions.')

    def __str__(self):
        return f"Permission denied: {self.msg}"


class UserIsNotInvited(UserError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f"The user is not invited: {self.msg}"


class GroupUUIDNotFound(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.pop('return_code', 404)
        self.msg = kwargs.pop('msg', 'Group not found.')
        self.group_uuid = kwargs.pop('group_uuid', '')

    def __str__(self):
        return f"Failed to find group with UUID {self.group_uuid}: {self.msg}"


class GroupFilterUUIDNotFound(GroupException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.pop('return_code', 404)
        self.msg = kwargs.pop('msg', 'Group filter not found.')
        self.group_filter_uuid = kwargs.pop('group_filter_uuid', '')

    def __str__(self):
        return f"Failed to find group filter with UUID {self.group_filter_uuid}: {self.msg}"
