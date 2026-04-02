import enum


class StandaloneEmailKind(enum.Enum):
    CONTACT_SUPPORT = "contact_support"
    RESET_PASSWORD = "reset_password"
    LOGIN_LINK = "login_link"
