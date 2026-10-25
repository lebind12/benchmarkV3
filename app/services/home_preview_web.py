"""Search discovery is untrusted; original-source verification precedes publication."""

import ipaddress
import re
import socket
import time
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from app.schemas.home_preview import PreviewPayload, clock
from app.services.home_preview import missing
from app.services.home_preview_policy import KST, utcnow

ALLOWED_HOSTS = {
    "liverpoolfc.com",
    "brightonandhovealbion.com",
    "mancity.com",
    "manutd.com",
    "arsenal.com",
    "chelseafc.com",
    "tottenhamhotspur.com",
    "uefa.com",
    "premierleague.com",
    "sportsmole.co.uk",
    "tntsports.co.uk",
    "racingpost.com",
    "betfair.com",
}
ALIASES = {
    40: "Liverpool",
    51: "Brighton",
    42: "Arsenal",
    50: "Manchester City",
    33: "Manchester United",
    49: "Chelsea",
    47: "Tottenham",
}


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []
        self.dates = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attrs.get("property", attrs.get("name", "")) in (
            "article:published_time",
            "article:modified_time",
            "datePublished",
            "dateModified",
            "date",
        ):
            self.dates.append(attrs.get("content", ""))
        if tag == "time" and attrs.get("datetime"):
            self.dates.append(attrs["datetime"])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)
        if self.in_title:
            self.title.append(text)


def normalized(value):
    return " ".join(unescape(value).split())


def allowed_url(url, *, grounding=False):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("unapproved_source_url")
    host = (parsed.hostname or "").lower()
    allowed = any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOSTS)
    if grounding and host == "vertexaisearch.cloud.google.com":
        allowed = True
    if not allowed:
        raise ValueError("unapproved_source_host")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("nonpublic_source_address")


def fetch_page(url):
    # Allowlisted public hosts only, validated on every redirect; no ambient proxy credentials.
    current = url
    deadline = time.monotonic() + 12
    with httpx.Client(
        timeout=8,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "BenchmarkPreview/1.0"},
    ) as client:
        for _ in range(4):
            if time.monotonic() >= deadline:
                raise ValueError("source_deadline")
            allowed_url(current, grounding=True)
            with client.stream(
                "GET", current, timeout=max(0.1, min(8, deadline - time.monotonic()))
            ) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers["location"])
                    continue
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", ""):
                    raise ValueError("unsupported_source_content")
                chunks = []
                length = 0
                for chunk in response.iter_bytes():
                    if time.monotonic() >= deadline:
                        raise ValueError("source_deadline")
                    length += len(chunk)
                    if length > 512 * 1024:
                        raise ValueError("source_too_large")
                    chunks.append(chunk)
                html = b"".join(chunks).decode("utf-8", errors="replace")
                parser = PageText()
                parser.feed(html)
                # JSON-LD publication dates are metadata, never executable instructions.
                parser.dates.extend(
                    re.findall(r'"date(?:Published|Modified)"\s*:\s*"([^"<>]+)"', html)
                )
                return {
                    "url": current,
                    "text": normalized(" ".join(parser.parts)),
                    "title": normalized(" ".join(parser.title))[:180],
                    "dates": parser.dates,
                    "digest": sha256(html.encode()).hexdigest(),
                }
        raise ValueError("too_many_source_redirects")


def verified_candidate(candidate, page, payload, *, now, aliases=None):
    fixture = payload["fixture"]
    kind = candidate.get("kind")
    quote = normalized(candidate.get("quote", ""))
    if (
        kind not in ("injury", "prediction", "odds")
        or not quote
        or len(quote.split()) > 20
        or quote.casefold() not in page["text"].casefold()
    ):
        raise ValueError("unverified_quote")
    if (
        candidate.get("fixture_id") != fixture["external_id"]
        or candidate.get("home_id") != fixture["home"]["external_id"]
        or candidate.get("away_id") != fixture["away"]["external_id"]
    ):
        raise ValueError("source_fixture_mismatch")
    match_date = clock(fixture["kickoff_at"]).astimezone(KST).date()
    if candidate.get("match_date") != match_date.isoformat():
        raise ValueError("source_match_date")
    aliases = aliases or {}
    home = (
        aliases.get(fixture["home"]["external_id"])
        or ALIASES.get(fixture["home"]["external_id"])
        or fixture["home"]["name"]
    )
    away = (
        aliases.get(fixture["away"]["external_id"])
        or ALIASES.get(fixture["away"]["external_id"])
        or fixture["away"]["name"]
    )
    if not all(name.casefold() in page["text"].casefold() for name in (home, away)):
        raise ValueError("source_teams_not_found")
    # Require a visible fixture date rather than trusting a generated match_date field.
    month = match_date.strftime("%B")
    short = match_date.strftime("%b")
    day = match_date.day
    patterns = [
        rf"\b{day}\s+(?:{month}|{short})\b",
        rf"\b(?:{month}|{short})\s+{day}\b",
        re.escape(match_date.isoformat()),
    ]
    if not any(re.search(pattern, page["text"], re.IGNORECASE) for pattern in patterns):
        raise ValueError("source_date_not_found")
    dates = []
    for date in page["dates"]:
        try:
            parsed = clock(date)
            if parsed.tzinfo is not None:
                dates.append(parsed)
        except ValueError:
            pass
    if (
        not dates
        or max(dates) > now
        or max(dates) >= clock(fixture["kickoff_at"])
        or min(dates) < now - timedelta(days=7)
    ):
        raise ValueError("unverified_publication_time")
    low = quote.casefold()
    if kind == "injury":
        if (
            candidate.get("team_id")
            not in (fixture["home"]["external_id"], fixture["away"]["external_id"])
            or not candidate.get("player_name")
            or candidate["player_name"].casefold() not in low
        ):
            raise ValueError("injury_player_mismatch")
        if re.search(r"not (?:ruled out|unavailable)", low):
            raise ValueError("negated_injury_status")
        markers = (
            r"ruled out|will be without|out:|unavailable"
            if candidate.get("availability") == "out"
            else r"doubtful|questionable|could miss|may miss"
        )
        if candidate.get("availability") not in ("out", "doubtful") or not re.search(markers, low):
            raise ValueError("unverified_injury_status")
        data = {
            "team_id": candidate["team_id"],
            "player_name": candidate["player_name"],
            "availability": candidate["availability"],
            "detail": "원문 결장 확인"
            if candidate["availability"] == "out"
            else "원문 출전 불확실",
            "impact": "출전 변수",
            "source_ids": [],
        }
    elif kind == "prediction":
        h, a = candidate.get("home_goals"), candidate.get("away_goals")
        if (
            type(h) is not int
            or type(a) is not int
            or not 0 <= h <= 30
            or not 0 <= a <= 30
            or not all(name.casefold() in low for name in (home, away))
            or not re.search(r"we say|predict|prediction", low)
        ):
            raise ValueError("unverified_prediction")
        if not re.search(
            rf"{re.escape(home)}\s+{h}\s*[-–:]\s*{a}\s+{re.escape(away)}", quote, re.IGNORECASE
        ):
            raise ValueError("unverified_predicted_score")
        winner = fixture["home"]["name"] if h > a else fixture["away"]["name"]
        data = {
            "source_id": "",
            "outlook": "무승부 전망" if h == a else f"{winner} 우세 전망",
            "summary": f"원문 예상 스코어 {fixture['home']['name']} {h}–{a} {fixture['away']['name']}",
        }
    else:
        if (
            candidate.get("market") != "1x2_90min"
            or not re.search(r"90[ -]?(?:minute|min)|regular time", low)
            or not all(name.casefold() in low for name in (home, away))
        ):
            raise ValueError("unverified_odds_market")
        raw = candidate.get("original_values") or {}
        if set(raw) != {"home", "draw", "away"} or not all(
            isinstance(value, str) and value in quote for value in raw.values()
        ):
            raise ValueError("unverified_odds_values")
        labels = {"home": re.escape(home), "draw": r"(?:the\s+)?draw", "away": re.escape(away)}
        if not all(
            re.search(labels[side] + r"\s+" + re.escape(value), quote, re.IGNORECASE)
            for side, value in raw.items()
        ):
            raise ValueError("odds_selection_labels")
        values = {}
        for side, value in raw.items():
            price = float(Fraction(value)) + 1 if "/" in value else float(value)
            if not 1 < price < 10000:
                raise ValueError("invalid_decimal_odds")
            values[side] = price
        bookmaker = candidate.get("bookmaker", "")
        if (
            not bookmaker
            or bookmaker.casefold()
            not in (page["title"] + " " + page["url"] + " " + quote).casefold()
        ):
            raise ValueError("unverified_bookmaker")
        data = dict(
            source_id="",
            bookmaker=bookmaker,
            market="1x2_90min",
            format="decimal",
            **values,
            collected_at=now.isoformat(),
        )
    return data, min(dates).isoformat(), quote


class WebPreviewEvidence:
    def __init__(self, discovery, *, fetcher=fetch_page, aliases=None, clock=utcnow):
        self.discovery = discovery
        self.fetcher = fetcher
        self.aliases = aliases
        self.clock = clock

    def __call__(self, snapshot, *, now):
        result = deepcopy(snapshot)
        usage = {"model_requests": 1, "web_verified_sources": 0}
        verification = []
        try:
            candidates, grounding, tokens = self.discovery(deepcopy(snapshot), now=now)
            usage["search_tokens"] = tokens
            queries = grounding.get("webSearchQueries") or []
            usage["search_queries"] = len(queries)
            html = (grounding.get("searchEntryPoint") or {}).get("renderedContent")
            urls = {
                chunk["web"]["uri"]
                for chunk in grounding.get("groundingChunks", [])
                if isinstance(chunk.get("web"), dict) and chunk["web"].get("uri")
            }
            if len(queries) > 6 or not html or len(html) > 32768:
                raise ValueError("unusable_grounding_metadata")
            pages = {}
            accepted = set()
            deadline = time.monotonic() + 50
            for candidate in candidates[:8]:
                if len(pages) >= 4 or time.monotonic() >= deadline:
                    break
                kind = candidate.get("kind")
                block = (
                    result["facts"]["injuries"]
                    if kind == "injury"
                    else result["external"]["odds"]
                    if kind == "odds"
                    else result["external"]["predictions"]
                )
                if block["status"] == "available":
                    continue
                url = candidate.get("url")
                parsed_url = urlsplit(url) if isinstance(url, str) else None
                signed_google_redirect = bool(
                    parsed_url
                    and parsed_url.scheme == "https"
                    and parsed_url.hostname == "vertexaisearch.cloud.google.com"
                    and parsed_url.path.startswith("/grounding-api-redirect/")
                    and queries
                )
                if url not in urls and not signed_google_redirect:
                    continue
                try:
                    page = (
                        pages.setdefault(url, self.fetcher(url)) if url not in pages else pages[url]
                    )
                    if page["url"] in accepted:
                        continue
                    checked = self.clock()
                    data, published_at, quote = verified_candidate(
                        candidate, page, result, now=checked, aliases=self.aliases
                    )
                    sid = "web-" + sha256(page["url"].encode()).hexdigest()[:16]
                    source = {
                        "id": sid,
                        "fixture_id": result["fixture"]["external_id"],
                        "kind": "web",
                        "title": page["title"] or page["url"],
                        "url": page["url"],
                        "published_at": published_at,
                        "retrieved_at": checked.isoformat(),
                    }
                    if kind == "injury":
                        data["source_ids"] = [sid]
                    else:
                        data["source_id"] = sid
                    result["sources"].append(source)
                    block.update(
                        status="partial" if kind == "injury" else "available",
                        reason="insufficient_sample" if kind == "injury" else None,
                        as_of=checked.isoformat(),
                        source_ids=[sid],
                        data=[data],
                    )
                    accepted.add(page["url"])
                    verification.append(
                        {
                            "source_id": sid,
                            "quote": quote,
                            "page_sha256": page["digest"],
                            "checked_at": checked.isoformat(),
                        }
                    )
                except (ValueError, KeyError, TypeError, httpx.HTTPError, OSError):
                    continue
            if accepted:
                result["as_of"] = max(source["retrieved_at"] for source in result["sources"])
                result["search_suggestions"] = {
                    "provider": "google",
                    "rendered_content": html,
                    "queries": queries,
                }
            for block in (
                result["facts"]["injuries"],
                result["external"]["predictions"],
                result["external"]["odds"],
            ):
                if block["data"] is None and block["status"] != "error":
                    block.update(status="unverified", reason="source_unverified")
            usage["web_verified_sources"] = len(accepted)
            usage["_evidence"] = verification
        except (ValueError, KeyError, TypeError, httpx.HTTPError, OSError):
            if result["external"]["predictions"]["data"] is None:
                result["external"]["predictions"] = {
                    **missing("upstream_failed"),
                    "status": "error",
                }
        return PreviewPayload.model_validate(result).root, usage
