import enum
import re
from typing import Optional


def stringify_uuid(uuid) -> Optional[str]:
    return str(uuid) if uuid else None


def force_lower_case(value):
    if isinstance(value, str):
        return value.lower()
    return value


def convert_enum(value):
    if hasattr(value, 'name'):
        return value.name.lower()
    return value.lower()


def remove_extra_whitespaces(value):
    if value and isinstance(value, str):
        return re.sub(r'\s+', ' ', value)

    return value
