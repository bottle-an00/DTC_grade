import os

import truststore

# Corporate networks often TLS-intercept with a self-signed proxy root that
# Windows trusts but Python's bundled cert list doesn't. Routing TLS
# verification through the OS store (already trusted, since the browser
# login flow works) avoids "self-signed certificate in certificate chain"
# failures without disabling verification.
truststore.inject_into_ssl()

import msal  # noqa: E402 -- must import after inject_into_ssl() patches ssl

# Microsoft Graph Command Line Tools -- Microsoft's own public, multi-tenant
# client ID meant for exactly this kind of delegated, admin-consent-free
# script login (https://learn.microsoft.com/en-us/troubleshoot/azure/active-directory/verify-first-party-apps-sign-in).
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["Files.Read", "Chat.ReadWrite"]
TOKEN_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".dtc_grade_msal_cache.json")


def _load_cache(cache_path: str) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache.deserialize(f.read())
    return cache


def _save_cache(cache: msal.SerializableTokenCache, cache_path: str) -> None:
    if cache.has_state_changed:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(cache.serialize())


def get_access_token(app=None, cache_path: str = TOKEN_CACHE_PATH) -> str:
    """Silently reuse a cached sign-in when possible; otherwise open an
    interactive Microsoft login (once) and cache the result for next time."""
    cache = _load_cache(cache_path)
    if app is None:
        app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        result = app.acquire_token_interactive(SCOPES)

    _save_cache(cache, cache_path)

    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "Microsoft 로그인에 실패했습니다"))
    return result["access_token"]
