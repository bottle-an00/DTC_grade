import base64
import json
import urllib.request


def encode_share_url(url: str) -> str:
    """Encode a sharing URL into a Microsoft Graph shareId, per
    https://learn.microsoft.com/en-us/graph/api/shares-get -- base64url of
    the raw URL bytes, "u!" prefix, padding stripped."""
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").rstrip("=")
    return "u!" + encoded


def _resolve_share_item(share_url: str, access_token: str, timeout: float) -> dict:
    """Resolve a sharing link (file or folder) to its driveItem metadata via
    the Graph Shares API -- this only touches metadata (id, name, webUrl,
    parentReference), never the protected file content."""
    share_id = encode_share_url(share_url)
    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_workbook_id(share_url: str, access_token: str, timeout: float = 30) -> str:
    """Resolve a OneDrive/SharePoint sharing link to its driveItem id."""
    return _resolve_share_item(share_url, access_token, timeout)["id"]


def list_folder_files(folder_url: str, access_token: str, timeout: float = 30) -> list[dict]:
    """List the .xlsx files directly inside a OneDrive/SharePoint folder,
    given the folder's sharing link. Metadata only (id/name/webUrl) -- lets
    a human pick which file to process without re-copying a per-file link
    every time a new version lands in the same, stable folder."""
    folder_item = _resolve_share_item(folder_url, access_token, timeout)
    drive_id = folder_item["parentReference"]["driveId"]
    folder_id = folder_item["id"]

    request = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))

    return [
        {"id": item["id"], "name": item["name"], "webUrl": item.get("webUrl")}
        for item in data.get("value", [])
        if item.get("name", "").lower().endswith(".xlsx")
    ]
