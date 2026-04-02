from alembic import op
import sqlalchemy as sa

from sortedcontainers import SortedDict
from random import randint

from .file_utils import find_project_root


def required_alembic_revision():
    """
    Determines the current required version number based on the alembic revision files found in source.
    """
    alembic_revisions = find_project_root() / "alembic" / "versions"

    revisions = SortedDict()
    for file in alembic_revisions.glob('*.py'):
        name_components = file.name.split('_')
        datetime = int(name_components[0] + name_components[1])
        version = name_components[2]
        revisions[datetime] = version

    if len(revisions) == 0:
        return None

    return revisions.popitem()[1]


def update_enum(enum_name: str,
                new_values: list,
                table: str,
                column: str,
                mapping_dict: dict = None):
    """
    Updates an enum type and migrates an existing column to this type.
    A mapping_dict can optionally be provided to handle updating existing rows.
    :param enum_name: The name of the enum type to update
    :param new_values: The new values which the enum should contain
    :param table:  The name of the table which contains this enum as a column
    :param column: The name of the column which uses this enum
    :param mapping_dict: A dict of the mapping changes to execute
    :return: None
    """
    enum_name_tmp = enum_name + "_tmp"

    # Temporarily rename old enum
    op.execute(f'ALTER TYPE {enum_name} RENAME TO {enum_name_tmp}')

    # Create new enum
    create_enum(enum_name=enum_name, values=new_values)

    # Run mappings
    if mapping_dict:
        for k, v in mapping_dict.items():
            op.execute(f"UPDATE {table} SET {column}='{v}' WHERE {column}='{k}'")

    # Switch column
    op.execute(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE {enum_name} USING {column}::text::{enum_name}')

    # Remove old enum
    delete_enum(enum_name=enum_name_tmp)


def create_enum(enum_name: str, values: list):
    new_enum = sa.Enum(*values, name=enum_name)
    new_enum.create(op.get_bind())


def delete_enum(enum_name: str):
    op.execute(f'DROP TYPE {enum_name}')
