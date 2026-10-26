"""Forecast coverage: distinct web publishers plus one API-Football prediction."""

from urllib.parse import urlsplit


def forecast_source_keys(payload):
    sources = {row["id"]: row for row in payload["sources"]}
    web = set()
    api = set()
    for row in payload["external"]["predictions"].get("data") or []:
        source = sources.get(row["source_id"])
        if not source or not source.get("url"):
            continue
        url = urlsplit(source["url"])
        host = (url.hostname or "").removeprefix("www.")
        if source["kind"] == "web":
            web.add("bbc.com" if host == "bbc.co.uk" else host)
        elif (
            source["kind"] == "api"
            and host == "v3.football.api-sports.io"
            and url.path == "/predictions"
        ):
            api.add("api-football")
    return web, api
