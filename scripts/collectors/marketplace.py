"""collectors/marketplace.py — VS Code Marketplace gallery API + OpenVSX (keyless)."""
import json
import urllib.parse
import urllib.request

from util import json_get, make_item

GALLERY = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"


def collect_vscode(search: str = "claude", limit: int = 10) -> list[dict]:
    """VS Code Marketplace gallery API (keyless [verified])."""
    body = json.dumps({"filters": [{"criteria": [{"filterType": 10, "value": search}],
                                    "pageNumber": 1, "pageSize": limit, "sortBy": 4}],
                       "flags": 914})
    req = urllib.request.Request(
        GALLERY, data=body.encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json;api-version=3.0-preview.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    out = []
    for f in data.get("results", []):
        for ext in f.get("extensions", []):
            pub = (ext.get("publisher") or {}).get("publisherName", "")
            name = ext.get("extensionName", "")
            stats = ext.get("statistics") or []
            eng = next((f"{s.get('value')} installs" for s in stats
                        if s.get("statisticName") == "install"), "")
            out.append(make_item("vscode.marketplace", f"{pub}.{name}",
                                 f"https://marketplace.visualstudio.com/items?itemName={pub}.{name}",
                                 engagement=eng))
    return out


def collect_openvsx(query: str = "claude", limit: int = 10) -> list[dict]:
    data = json_get(
        f"https://open-vsx.org/api/-/search?query={urllib.parse.quote(query)}"
        f"&size={limit}&sort=timestamp")
    out = []
    for ext in data.get("extensions", []):
        out.append(make_item("openvsx", f"{ext.get('namespace')}.{ext.get('name')}",
                             ext.get("url", ""),
                             engagement=f"{ext.get('downloadCount', 0)} downloads",
                             published=ext.get("timestamp", "")))
    return out

