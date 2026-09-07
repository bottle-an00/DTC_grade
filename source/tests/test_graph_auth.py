import pytest

from tools.graph_auth import get_access_token


class FakeApp:
    def __init__(self, accounts=None, silent_result=None, interactive_result=None):
        self._accounts = accounts or []
        self._silent_result = silent_result
        self._interactive_result = interactive_result
        self.interactive_called = False

    def get_accounts(self):
        return self._accounts

    def acquire_token_silent(self, scopes, account):
        return self._silent_result

    def acquire_token_interactive(self, scopes):
        self.interactive_called = True
        return self._interactive_result


def test_get_access_token_reuses_a_silent_result_without_going_interactive(tmp_path):
    app = FakeApp(accounts=[{"username": "me"}], silent_result={"access_token": "SILENT_TOKEN"})

    token = get_access_token(app=app, cache_path=str(tmp_path / "cache.json"))

    assert token == "SILENT_TOKEN"
    assert app.interactive_called is False


def test_get_access_token_falls_back_to_interactive_when_no_account_or_silent_result(tmp_path):
    app = FakeApp(accounts=[], interactive_result={"access_token": "INTERACTIVE_TOKEN"})

    token = get_access_token(app=app, cache_path=str(tmp_path / "cache.json"))

    assert token == "INTERACTIVE_TOKEN"
    assert app.interactive_called is True


def test_get_access_token_raises_with_the_graph_error_description(tmp_path):
    app = FakeApp(accounts=[], interactive_result={"error_description": "user cancelled"})

    with pytest.raises(RuntimeError, match="user cancelled"):
        get_access_token(app=app, cache_path=str(tmp_path / "cache.json"))
