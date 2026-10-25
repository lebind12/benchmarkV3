"""Original-page cause/occurrence checks for the final maximum four absentees only."""

import re
import time
import unicodedata
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from urllib.parse import urlsplit

import httpx

from app.schemas.home_preview import PreviewPayload, clock
from app.services.home_preview_policy import utcnow
from app.services.home_preview_web import fetch_page, normalized

CAUSES = {
    "hamstring": ("햄스트링 부상", r"hamstring"),
    "groin": ("사타구니 부상", r"groin"),
    "thigh": ("허벅지 부상", r"thigh"),
    "knee": ("무릎 부상", r"knee"),
    "acl": ("무릎 십자인대 부상", r"cruciate|\bacl\b"),
    "ankle": ("발목 부상", r"ankle"),
    "calf": ("종아리 부상", r"calf"),
    "achilles": ("아킬레스건 부상", r"achilles"),
    "muscle": ("근육 부상", r"muscle|muscular"),
    "hip": ("엉덩이 부상", r"\bhip\b"),
    "foot": ("발 부상", r"\bfoot\b"),
    "shin": ("정강이 부상", r"shin"),
    "shoulder": ("어깨 부상", r"shoulder"),
    "illness": ("질병으로 결장", r"illness|virus|infection"),
    "red_card": ("퇴장 징계", r"red card|sent off|sending.off"),
    "yellow_cards": (
        "경고 누적 징계",
        r"yellow cards|booking accumulation|accumulation of bookings",
    ),
}


def folded(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    ).casefold()


def targets_from(payload):
    selected = (payload["analysis"].get("key_absences") or {}).get("data") or []
    counts, targets, seen = {}, [], set()
    registry = {
        (row["team_id"], row.get("player_id")): row
        for row in payload["facts"]["injuries"]["data"] or []
    }
    for pick in selected:
        key = (pick["team_id"], pick["player_id"])
        if key in seen or key not in registry or registry[key].get("status_conflict"):
            continue
        counts[key[0]] = counts.get(key[0], 0) + 1
        if counts[key[0]] > 2:
            continue
        seen.add(key)
        targets.append(registry[key])
    return targets[:4]


def occurrence(candidate, page, target, published, now):
    day, month = candidate.get("occurred_on"), candidate.get("occurred_month")
    if not day and not month:
        return None, None
    quote = normalized(candidate.get("occurrence_quote", ""))
    if not quote or len(quote.split()) > 20 or folded(quote) not in folded(page["text"]):
        return None, None
    # An article timestamp, predicted return date or a bare date is never an incident date.
    if not re.search(
        r"suffered|sustained|injured|picked up|forced off|sent off|received|since|ruptured|tore",
        quote,
        re.IGNORECASE,
    ):
        return None, None
    if re.search(r"return|back (?:on|in)|expected (?:on|in)|due back", quote, re.IGNORECASE):
        return None, None
    name = target.get("importance_evidence", {}).get("recognition_name") or target["player_name"]
    surname = folded(name).split()[-1]
    if len(surname) < 4 or surname not in folded(quote):
        return None, None
    try:
        stamp = date.fromisoformat(day or (month + "-01"))
    except (ValueError, TypeError):
        return None, None
    if (
        day
        and month
        or not now.date() - timedelta(days=730) <= stamp <= min(now.date(), published.date())
    ):
        return None, None
    full_month = stamp.strftime("%B")
    short_month = stamp.strftime("%b")
    if day:
        patterns = [
            re.escape(stamp.isoformat()),
            rf"\b{stamp.day}\s+(?:{full_month}|{short_month})\s+{stamp.year}\b",
            rf"\b(?:{full_month}|{short_month})\s+{stamp.day},?\s+{stamp.year}\b",
        ]
    else:
        patterns = [
            re.escape(stamp.strftime("%Y-%m")),
            rf"\b(?:{full_month}|{short_month})\s+{stamp.year}\b",
        ]
    if not any(re.search(pattern, quote, re.IGNORECASE) for pattern in patterns):
        relative = None
        lower = quote.casefold()
        if day and not re.search(r"next|weeks? ago|last month|last year", lower):
            if "yesterday" in lower or "last night" in lower:
                relative = published.date() - timedelta(days=1)
            elif "today" in lower:
                relative = published.date()
            else:
                for weekday, name in enumerate(
                    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
                ):
                    if re.search(rf"\b{name}\b", lower):
                        delta = (published.weekday() - weekday) % 7
                        if delta == 0 and "last " + name in lower:
                            delta = 7
                        relative = published.date() - timedelta(days=delta)
                        break
        if relative != stamp:
            return None, None
    return (stamp.isoformat(), None) if day else (None, stamp.strftime("%Y-%m"))


def verified_cause(candidate, page, payload, target, *, now, aliases=None):
    if (
        candidate.get("player_id") != target["player_id"]
        or candidate.get("team_id") != target["team_id"]
    ):
        raise ValueError("cause_player_mismatch")
    code = candidate.get("reason_code")
    quote = normalized(candidate.get("quote", ""))
    if (
        code not in CAUSES
        or not quote
        or len(quote.split()) > 20
        or folded(quote) not in folded(page["text"])
    ):
        raise ValueError("cause_unverified_quote")
    canonical = (
        target.get("importance_evidence", {}).get("recognition_name") or target["player_name"]
    )
    names = [canonical, target["player_name"]]
    surname = folded(canonical).split()[-1]
    if not any(
        re.search(rf"(?<!\w){re.escape(folded(name))}(?!\w)", folded(quote)) for name in names
    ) and not (
        len(surname) >= 4 and re.search(rf"(?<!\w){re.escape(surname)}(?!\w)", folded(quote))
    ):
        raise ValueError("cause_player_not_in_quote")
    team_name = (aliases or {}).get(target["team_id"], "")
    if not team_name or folded(team_name) not in folded(page["text"]):
        raise ValueError("cause_team_not_in_page")
    if not re.search(CAUSES[code][1], quote, re.IGNORECASE) or re.search(
        r"(?:no|not an?|without) (?:a )?(?:hamstring|groin|thigh|knee|muscle|ankle|hip|foot|calf) (?:injury|problem)",
        quote,
        re.IGNORECASE,
    ):
        raise ValueError("cause_type_not_verified")
    dates = []
    for value in page["dates"]:
        try:
            stamp = clock(value)
            if stamp.tzinfo is not None:
                dates.append(stamp)
        except (ValueError, TypeError):
            pass
    if (
        not dates
        or min(dates) < now - timedelta(days=7)
        or max(dates) > now
        or max(dates) >= clock(payload["fixture"]["kickoff_at"])
    ):
        raise ValueError("cause_unverified_publication")
    api = target["detail"].casefold()
    if "red card" in api and code != "red_card" or "yellow" in api and code != "yellow_cards":
        raise ValueError("cause_api_conflict")
    specific = {
        key for key, (_, pattern) in CAUSES.items() if re.search(pattern, api, re.IGNORECASE)
    }
    compatible = {"muscle", "hamstring", "groin", "thigh", "calf"}
    if (
        specific
        and code not in specific
        and not (specific <= compatible and code in compatible)
        and not (specific == {"knee"} and code == "acl")
    ):
        raise ValueError("cause_api_conflict")
    if code in ("red_card", "yellow_cards"):
        fixture = payload["fixture"]
        day = clock(fixture["kickoff_at"]).date()
        opponent = next(
            (
                aliases.get(fixture[side]["external_id"], "")
                for side in ("home", "away")
                if fixture[side]["external_id"] != target["team_id"]
            ),
            "",
        )
        if (
            not opponent
            or folded(opponent) not in folded(page["text"])
            or not re.search(
                rf"{day.day}\s+{day.strftime('%B')}|{day.strftime('%B')}\s+{day.day}|{day.isoformat()}",
                page["text"],
                re.IGNORECASE,
            )
        ):
            raise ValueError("cause_suspension_fixture_unverified")
    occurred_on, occurred_month = occurrence(candidate, page, target, min(dates), now)
    return {
        "code": code,
        "label": CAUSES[code][0],
        "occurred_on": occurred_on,
        "occurred_month": occurred_month,
    }, min(dates).isoformat()


class WebAbsenceCauses:
    def __init__(self, discovery, *, fetcher=fetch_page, aliases=None, clock=utcnow):
        self.discovery, self.fetcher, self.aliases, self.clock = (
            discovery,
            fetcher,
            aliases or {},
            clock,
        )

    def __call__(self, payload, *, now):
        result = deepcopy(payload)
        targets = targets_from(result)
        if not targets:
            return result, {"model_requests": 0, "cause_search_requests": 0}
        usage = {
            "model_requests": 1,
            "cause_search_requests": 1,
            "cause_targets": len(targets),
            "cause_verified": 0,
            "cause_rejections": [],
            "_evidence": [],
        }
        for target in targets:
            target["cause"] = {
                "status": "unverified",
                "reason": "source_unverified",
                "as_of": None,
                "source_ids": [],
                "data": None,
            }
        known = {(row["team_id"], row["player_id"]): row for row in targets}
        seen = set()
        pages = {}
        try:
            candidates, grounding, tokens = self.discovery(
                deepcopy(result), targets=deepcopy(targets), now=now
            )
            usage["cause_search_tokens"] = tokens
            queries = grounding.get("webSearchQueries") or []
            usage["search_queries"] = len(queries)
            usage["search_query_overrun"] = len(queries) > 4
            html = (grounding.get("searchEntryPoint") or {}).get("renderedContent")
            if len(queries) > 20 or not html or len(html) > 32768:
                raise ValueError("unusable_grounding")
            urls = {
                row["web"]["uri"]
                for row in grounding.get("groundingChunks", [])
                if isinstance(row.get("web"), dict) and row["web"].get("uri")
            }
            deadline = time.monotonic() + 30
            attempts = 0
            for candidate in candidates[:8]:
                key = (candidate.get("team_id"), candidate.get("player_id"))
                if key not in known or key in seen:
                    continue
                url = candidate.get("url", "")
                parsed = urlsplit(url)
                if url not in urls and not (
                    parsed.scheme == "https"
                    and parsed.hostname == "vertexaisearch.cloud.google.com"
                    and parsed.path.startswith("/grounding-api-redirect/")
                    and queries
                ):
                    continue
                if time.monotonic() >= deadline:
                    break
                try:
                    if url not in pages:
                        if attempts >= 4:
                            break
                        attempts += 1
                        pages[url] = self.fetcher(url)
                    page = pages[url]
                    checked = self.clock()
                    data, published = verified_cause(
                        candidate, page, result, known[key], now=checked, aliases=self.aliases
                    )
                    sid = "web-cause-" + sha256(page["url"].encode()).hexdigest()[:16]
                    if not any(row["id"] == sid for row in result["sources"]):
                        result["sources"].append(
                            {
                                "id": sid,
                                "fixture_id": result["fixture"]["external_id"],
                                "kind": "web",
                                "title": page["title"] or page["url"],
                                "url": page["url"],
                                "published_at": published,
                                "retrieved_at": checked.isoformat(),
                            }
                        )
                    known[key]["cause"] = {
                        "status": "available",
                        "reason": None,
                        "as_of": checked.isoformat(),
                        "source_ids": [sid],
                        "data": data,
                    }
                    seen.add(key)
                    result["as_of"] = max(result["as_of"], checked.isoformat())
                    usage["_evidence"].append(
                        {
                            "source_id": sid,
                            "player_id": key[1],
                            "team_id": key[0],
                            "quote": candidate["quote"],
                            "occurrence_quote": candidate.get("occurrence_quote"),
                            "page_sha256": page["digest"],
                            "checked_at": checked.isoformat(),
                        }
                    )
                except (ValueError, KeyError, TypeError, httpx.HTTPError, OSError) as exc:
                    code = str(exc) if isinstance(exc, ValueError) else ""
                    reason = (
                        "unverified_quote"
                        if "quote" in code or "player" in code
                        else "unverified_publication"
                        if "publication" in code
                        else "conflicting_cause"
                        if "conflict" in code
                        else "unverified_cause"
                        if code.startswith("cause_")
                        else "original_unavailable"
                    )
                    usage["cause_rejections"] = sorted(set(usage["cause_rejections"]) | {reason})
                    continue
            if seen:
                suggestion = {"provider": "google", "rendered_content": html, "queries": queries}
                if result["search_suggestions"] is None:
                    result["search_suggestions"] = suggestion
                else:
                    result["search_suggestions_extra"] = [suggestion]
        except (ValueError, KeyError, TypeError, httpx.HTTPError, OSError) as exc:
            usage["cause_search_failed"] = True
            usage["cause_failure_type"] = type(exc).__name__
            if isinstance(exc, ValueError) and str(exc) in (
                "incomplete_model_response",
                "empty_model_response",
                "invalid_cause_discovery_response",
                "unusable_grounding",
            ):
                usage["cause_failure_code"] = str(exc)
        usage["cause_verified"] = len(seen)
        # This is the actual completion of the last generative research step, never backdated.
        result["generated_at"] = self.clock().isoformat()
        return PreviewPayload.model_validate(result).root, usage
