import json

from tools.resolve_workbook import encode_share_url, list_folder_files, resolve_workbook_id


def test_encode_share_url_matches_the_documented_graph_shares_format():
    # https://learn.microsoft.com/en-us/graph/api/shares-get -- base64url of
    # the URL, "u!" prefix, no padding.
    encoded = encode_share_url("https://example.com/file")
    assert encoded.startswith("u!")
    assert "=" not in encoded


def test_resolve_workbook_id_calls_the_shares_endpoint_and_returns_the_item_id(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"id": "ITEM_ID_123"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("tools.resolve_workbook.urllib.request.urlopen", fake_urlopen)

    item_id = resolve_workbook_id("https://example.com/file", "TOKEN_ABC", timeout=30)

    assert item_id == "ITEM_ID_123"
    assert captured["auth"] == "Bearer TOKEN_ABC"
    assert "/shares/" in captured["url"]
    assert "/driveItem" in captured["url"]
    assert captured["timeout"] == 30


def test_list_folder_files_resolves_the_folder_then_lists_xlsx_children(monkeypatch):
    requests_made = []

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self._body

    responses = [
        json.dumps({"id": "FOLDER_ID", "parentReference": {"driveId": "DRIVE_ID"}}).encode("utf-8"),
        json.dumps(
            {
                "value": [
                    {"id": "FILE_1", "name": "model_a.xlsx", "webUrl": "https://x/model_a.xlsx"},
                    {"id": "FILE_2", "name": "model_b.XLSX", "webUrl": "https://x/model_b.xlsx"},
                    {"id": "FOLDER_3", "name": "subfolder"},
                    {"id": "FILE_4", "name": "notes.txt"},
                ]
            }
        ).encode("utf-8"),
    ]

    def fake_urlopen(request, timeout):
        requests_made.append(request.full_url)
        return FakeResponse(responses[len(requests_made) - 1])

    monkeypatch.setattr("tools.resolve_workbook.urllib.request.urlopen", fake_urlopen)

    files = list_folder_files("https://example.com/folder", "TOKEN_ABC", timeout=30)

    assert "/shares/" in requests_made[0]
    assert "DRIVE_ID" in requests_made[1] and "FOLDER_ID" in requests_made[1] and "/children" in requests_made[1]
    assert files == [
        {"id": "FILE_1", "name": "model_a.xlsx", "webUrl": "https://x/model_a.xlsx"},
        {"id": "FILE_2", "name": "model_b.XLSX", "webUrl": "https://x/model_b.xlsx"},
    ]
