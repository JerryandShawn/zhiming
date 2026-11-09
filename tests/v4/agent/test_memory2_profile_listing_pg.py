"""About Me sections are listed for the new web page exactly as the single-row view returns them."""

from .test_memory2_profile_web_pg import accepted, change
from .test_memory2_profile_web_pg import profile_web as profile_web  # noqa: F401  (pytest fixture)
from .test_memory2_routes_pg import HEADERS


def test_listing_matches_view_and_drops_deleted_rows(web):
    repo, client = web
    assert client.get("/api/memory2/profile", headers=HEADERS).json() == []
    item, _ = accepted(repo, client)
    listed = client.get("/api/memory2/profile", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    view = client.get(f"/api/memory2/profile/{item['id']}", headers=HEADERS).json()
    assert listed.json() == [view]
    assert client.get("/api/memory2/profile", params={"subject_id": "nobody"}, headers=HEADERS).status_code == 404
    assert change(client, item, "delete", key="delete-listed").status_code == 200
    assert client.get("/api/memory2/profile", headers=HEADERS).json() == []
