from pathlib import Path


def find_file(file_name='alembic.ini', file_path=Path('.')):
    """
    Recursively moves up the directory structure looking for file_name
    :param file_name: the name of the alembic.ini file
    :param file_path: the path to check
    :return: pathlib.Path to the specified file
    """
    path = file_path.absolute() / file_name
    if path.exists() and path.is_file():
        return str(path.absolute())

    if '/' == str(file_path.absolute()):
        raise FileNotFoundError('Couldn\'t find {}...'.format(file_name))

    return find_file(file_name, file_path.absolute().parent)


def find_project_root():
    """
    Determine's the project root directory and returns it as a Path object
    :return: pathlib.Path to the project root
    """
    return Path(find_file('config.ini')).parent
