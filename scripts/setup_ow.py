"""
Set up

Run via `nox -s setup_ow`
"""

import os
import sys

import django
import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jhe.settings")
# avoid debug logging
os.environ["DEBUG"] = ""

ow_url, admin_email, admin_password = sys.argv[1:]

django.setup()

from core.models import JheSetting


def ow_access_token():
    print(f"Getting access token for {admin_email} from {ow_url}")
    r = requests.post(
        f"{ow_url}/api/v1/auth/login",
        data={"username": admin_email, "password": admin_password},
    )
    r.raise_for_status()
    return r.json()["access_token"]


token = ow_access_token()

s = requests.Session()
s.headers["Authorization"] = f"Bearer {token}"

# delete any pre-existing keys for JHE,
# issue new one
r = s.get(
    f"{ow_url}/api/v1/developer/api-keys",
)
r.raise_for_status()
keys = r.json()
for key in keys:
    if key["name"] == "JHE":
        print(f"Deleting {key}")
        r = s.delete(f"{ow_url}/api/v1/developer/api-keys/{key['id']}")
        r.raise_for_status()

# issue new ow api key
r = s.post(
    f"{ow_url}/api/v1/developer/api-keys",
    json={"name": "JHE"},
)
r.raise_for_status()
api_key = r.json()["key"]

# store key in settings, enable ow polling
for key, value_type, value in [
    ("ow.api_url", "string", ow_url),
    ("ow.api_key", "string", api_key),
    ("module.ow", "bool", True),
]:
    setting, _ = JheSetting.objects.update_or_create(
        key=key,
        defaults={"value_type": value_type},
    )

    setting.set_value(value_type, value)
    setting.save()
