class _Any(object):
    """
    A helper object for assertions that compares equal to everything.
    """

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __repr__(self):
        return '<ANY>'


ANY = _Any()
