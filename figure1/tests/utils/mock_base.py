

class MockBase:
    def __init__(self):
        self.called = False
        self.calls = []
        self.call_count = 0

    def assert_called_with(self, **kwargs):
        assert kwargs in self.calls

    def assert_not_called(self):
        assert not self.calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
