"""Original-page cause/occurrence checks for the final maximum four absentees only."""

import re
import time
import unicodedata
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from hashlib import sha256
from urllib.parse import urlsplit

import httpx

from app.schemas.home_preview import PreviewPayload, clock
from app.services.home_preview_policy import utcnow
from app.services.home_preview_web import fetch_page, normalized, registered_article_url

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


def publication_info(page, *, now, kickoff, max_age=30):
    days, stamps = [], []
    for value in page["dates"]:
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                days.append(date.fromisoformat(value))
            else:
                stamp = clock(value)
                if stamp.tzinfo is not None:
                    stamps.append(stamp)
                    days.append(stamp.date())
        except (ValueError, TypeError):
            pass
    if (
        not days
        or min(days) < now.date() - timedelta(days=max_age)
        or max(days) > min(now.date(), kickoff.date())
        or any(stamp > now or stamp >= kickoff for stamp in stamps)
    ):
        raise ValueError("cause_unverified_publication")
    published_day = min(days)
    exact = min((stamp for stamp in stamps if stamp.date() == published_day), default=None)
    # Midnight is an internal calendar anchor, never exposed as a publication time.
    anchor = exact or datetime.combine(published_day, day_time.min, tzinfo=UTC)
    return anchor, exact.isoformat() if exact else None, published_day.isoformat()


def claim_context(candidate, page, target, *, claim):
    primary = candidate.get("quote" if claim == "cause" else "occurrence_quote") or ""
    extra = candidate.get("cause_quotes" if claim == "cause" else "occurrence_quotes") or []
    supplied = [primary] + (extra[:3] if isinstance(extra, list) else [])
    quotes = list(
        dict.fromkeys(
            value
            for value in supplied
            if isinstance(value, str)
            and value
            and len(value.split()) <= 20
            and folded(normalized(value)) in folded(page["text"])
        )
    )
    if not quotes:
        raise ValueError("cause_unverified_quote")
    canonical = (
        target.get("importance_evidence", {}).get("recognition_name") or target["player_name"]
    )
    names = [canonical, target["player_name"]]
    surname = folded(canonical).split()[-1]

    def named(value):
        low = folded(value)
        return any(
            re.search(rf"(?<!\w){re.escape(folded(name))}(?!\w)", low) for name in names
        ) or (len(surname) >= 4 and re.search(rf"(?<!\w){re.escape(surname)}(?!\w)", low))

    passages = page.get("passages") or []
    located = []
    for index, passage in enumerate(passages):
        heading = passage["heading"]
        # A multi-player article heading does not bind every paragraph to each player.
        bound_heading = (
            heading
            if passage["heading_level"] >= 2
            or not re.search(r"\band\b|&|\bupdates\b", heading, re.IGNORECASE)
            else ""
        )
        context = normalized(bound_heading + " " + passage["text"])
        if any(folded(normalized(quote)) in folded(context) for quote in quotes):
            located.append((index, passage, context))
    # A redundant poor excerpt must not invalidate a different original passage
    # which independently binds this player to the claimed injury type.
    if claim == "cause":
        pattern = CAUSES.get(candidate.get("reason_code"), ("", r"(?!)"))[1]
        for index, passage, context in located:
            supporting = [q for q in quotes if folded(normalized(q)) in folded(context)]
            if named(context) and re.search(pattern, context, re.IGNORECASE) and supporting:
                return context, supporting, [index]
    # Occurrence evidence may need several fragments of the same paragraph.
    for index, passage, context in located:
        if named(context) and all(folded(normalized(q)) in folded(context) for q in quotes):
            return context, quotes, [index]
    # Multiple paragraphs under one explicitly named player section may be combined.
    headings = {
        item[1]["heading"]
        for item in located
        if item[1]["heading_level"] >= 2 and named(item[1]["heading"])
    }
    for heading in headings:
        group = [item for item in located if item[1]["heading"] == heading]
        context = normalized(" ".join(item[2] for item in group))
        if all(folded(normalized(quote)) in folded(context) for quote in quotes):
            return context, quotes, [item[0] for item in group]
    # A multi-player article can join passages only when each explicitly names this player.
    group = [item for item in located if named(item[1]["text"])]
    context = normalized(" ".join(item[2] for item in group))
    if group and all(folded(normalized(quote)) in folded(context) for quote in quotes):
        return context, quotes, [item[0] for item in group]
    legacy = normalized(" ".join(quotes))
    if not passages and named(legacy):
        return legacy, quotes, []
    raise ValueError("cause_player_not_in_quote")


def occurrence(candidate, page, target, published, now):
    day, month = candidate.get("occurred_on"), candidate.get("occurred_month")
    if not day and not month:
        return None, None
    try:
        quote, _, _ = claim_context(candidate, page, target, claim="occurrence")
    except ValueError:
        return None, None
    # An article timestamp, predicted return date or a bare date is never an incident date.
    if not re.search(
        r"suffered|sustained|injured|aggravat|recurr|picked up|forced off|substitut|withdrawn|sent off|received|since|ruptured|tore|date of injury|injury date",
        quote,
        re.IGNORECASE,
    ):
        return None, None

    def incident_position(position):
        prefix = quote[max(0, position - 120) : position]
        actions = list(
            re.finditer(
                r"return\w*|due back|expected(?: to)? (?:return|back)|back (?:on|in)|suffer\w*|sustain\w*|injured|aggravat\w*|recurr\w*|forced off|substitut\w*|withdrawn|since|picked up",
                prefix,
                re.IGNORECASE,
            )
        )
        return not actions or not re.match(
            r"return|due back|expected|back ", actions[-1].group(), re.IGNORECASE
        )

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
            rf"\b{stamp.day}\s+(?:{full_month}|{short_month})\.?\s+{stamp.year}\b",
            rf"\b(?:{full_month}|{short_month})\.?\s+{stamp.day},?\s+{stamp.year}\b",
        ]
    else:
        patterns = [
            re.escape(stamp.strftime("%Y-%m")),
            rf"\b(?:{full_month}|{short_month})\.?\s+{stamp.year}\b",
        ]
    exact_matches = [
        match for pattern in patterns for match in re.finditer(pattern, quote, re.IGNORECASE)
    ]
    if exact_matches and not any(incident_position(match.start()) for match in exact_matches):
        return None, None
    if not exact_matches:
        # Year-less day/month in a current incident report is anchored to its publication year.
        yearless = [
            rf"\b{stamp.day}(?:st|nd|rd|th)?\s+(?:{full_month}|{short_month})(?!\s+\d{{4}})\b",
            rf"\b(?:{full_month}|{short_month})\.?\s+{stamp.day}(?:st|nd|rd|th)?(?!,?\s+\d{{4}})\b",
        ]
        if (
            day
            and stamp.year == published.year
            and (published.date() - stamp).days <= 90
            and any(
                incident_position(match.start())
                for pattern in yearless
                for match in re.finditer(pattern, quote, re.IGNORECASE)
            )
        ):
            return stamp.isoformat(), None
        relative = None
        lower = quote.casefold()
        if day and not re.search(r"next|weeks? ago|last month|last year", lower):
            if any(
                incident_position(match.start())
                for match in re.finditer(r"yesterday|last night", lower)
            ):
                relative = published.date() - timedelta(days=1)
            elif any(
                incident_position(match.start()) for match in re.finditer(r"\btoday\b", lower)
            ):
                relative = published.date()
            else:
                for weekday, name in enumerate(
                    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
                ):
                    if any(
                        incident_position(match.start())
                        for match in re.finditer(rf"\b{name}\b", lower)
                    ):
                        delta = (published.weekday() - weekday) % 7
                        if delta == 0 and "last " + name in lower:
                            delta = 7
                        relative = published.date() - timedelta(days=delta)
                        break
        if relative != stamp:
            return None, None
    return (stamp.isoformat(), None) if day else (None, stamp.strftime("%Y-%m"))


def verified_cause(candidate, page, payload, target, *, now, aliases=None, occurrence_page=None):
    if (
        candidate.get("player_id") != target["player_id"]
        or candidate.get("team_id") != target["team_id"]
    ):
        raise ValueError("cause_player_mismatch")
    code = candidate.get("reason_code")
    if code not in CAUSES:
        raise ValueError("cause_type_not_verified")
    quote, _, _ = claim_context(candidate, page, target, claim="cause")
    team_name = (aliases or {}).get(target["team_id"], "")
    if not team_name or folded(team_name) not in folded(page["text"]):
        raise ValueError("cause_team_not_in_page")
    if not re.search(CAUSES[code][1], quote, re.IGNORECASE) or re.search(
        r"(?:no|not an?|without) (?:a )?(?:hamstring|groin|thigh|knee|muscle|ankle|hip|foot|calf) (?:injury|problem)",
        quote,
        re.IGNORECASE,
    ):
        raise ValueError("cause_type_not_verified")
    published, published_at, _ = publication_info(
        page, now=now, kickoff=clock(payload["fixture"]["kickoff_at"])
    )
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
    event_page = occurrence_page or page
    if event_page is not page:
        try:
            event_anchor, _, _ = publication_info(
                event_page, now=now, kickoff=clock(payload["fixture"]["kickoff_at"]), max_age=90
            )
            event_context, _, _ = claim_context(candidate, event_page, target, claim="occurrence")
            event_types = {
                kind
                for kind, (_, pattern) in CAUSES.items()
                if re.search(pattern, event_context, re.IGNORECASE)
            }
            compatible_event = {"muscle", "hamstring", "groin", "thigh", "calf"}
            if (
                event_types
                and code not in event_types
                and not (event_types <= compatible_event and code in compatible_event)
            ):
                raise ValueError("cause_unlinked_episode")
            linked = page["url"] in event_page.get("links", []) or event_page["url"] in page.get(
                "links", []
            )
            recurrence = re.search(
                r"same (?:injury|place|problem)|not a new injury|recurr|aggravat",
                event_context,
                re.IGNORECASE,
            )
            if not linked and not (
                recurrence
                and published.date() <= event_anchor.date()
                and (event_anchor.date() - published.date()).days <= 30
            ):
                raise ValueError("cause_unlinked_episode")
            occurred_on, occurred_month = occurrence(
                candidate, event_page, target, event_anchor, now
            )
        except ValueError:
            occurred_on, occurred_month = None, None
    else:
        occurred_on, occurred_month = occurrence(candidate, page, target, published, now)
    label = CAUSES[code][0]
    if occurred_on or occurred_month:
        event_context, _, _ = claim_context(candidate, event_page, target, claim="occurrence")
        if re.search(r"recurr|aggravat|not a new injury", event_context, re.IGNORECASE):
            label += " 재발"
    return {
        "code": code,
        "label": label,
        "occurred_on": occurred_on,
        "occurred_month": occurred_month,
    }, published_at


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
            "cause_diagnostics": [],
            "_evidence": [],
        }
        for target in targets:
            previous_cause = target.get("cause")
            if (
                previous_cause
                and previous_cause.get("data")
                and previous_cause.get("as_of")
                and now - clock(previous_cause["as_of"]) <= timedelta(hours=6)
            ):
                continue
            target["cause"] = {
                "status": "unverified",
                "reason": "source_unverified",
                "as_of": None,
                "source_ids": [],
                "data": None,
            }
        known = {(row["team_id"], row["player_id"]): row for row in targets}
        seen = {
            (row["team_id"], row["player_id"])
            for row in targets
            if row.get("cause", {}).get("data")
        }
        pages = {}
        try:
            candidates, grounding, tokens = self.discovery(
                deepcopy(result), targets=deepcopy(targets), now=now
            )
            usage["cause_search_tokens"] = tokens
            usage["model_requests"] = tokens.get("model_requests", 1)
            usage["cause_extraction_requests"] = tokens.get("extraction_requests", 0)
            queries = grounding.get("webSearchQueries") or []
            usage["search_queries"] = len(queries)
            usage["search_query_overrun"] = len(queries) > 4
            html = (grounding.get("searchEntryPoint") or {}).get("renderedContent")
            if len(queries) > 100 or not html or len(html) > 32768:
                raise ValueError("unusable_grounding")
            urls = {
                row["web"]["uri"]
                for row in grounding.get("groundingChunks", [])
                if isinstance(row.get("web"), dict) and row["web"].get("uri")
            }
            deadline = time.monotonic() + 60
            attempts = 0
            for candidate in candidates[:8]:
                key = (candidate.get("team_id"), candidate.get("player_id"))
                if key not in known:
                    continue
                existing_data = (known[key].get("cause") or {}).get("data")
                if existing_data and (
                    existing_data["occurred_on"] or existing_data["occurred_month"]
                ):
                    continue
                url = candidate.get("url", "")
                parsed = urlsplit(url)
                if (
                    url not in urls
                    and not registered_article_url(url)
                    and not (
                        parsed.scheme == "https"
                        and parsed.hostname == "vertexaisearch.cloud.google.com"
                        and parsed.path.startswith("/grounding-api-redirect/")
                        and queries
                    )
                ):
                    usage["cause_rejections"] = sorted(
                        set(usage["cause_rejections"]) | {"unregistered_candidate_url"}
                    )
                    continue
                if time.monotonic() >= deadline:
                    break
                stage = "source_fetch"
                page = None
                try:
                    if url not in pages:
                        if attempts >= 8:
                            break
                        attempts += 1
                        pages[url] = self.fetcher(url)
                    page = pages[url]
                    event_page = page
                    event_url = candidate.get("occurrence_url")
                    if (
                        event_url
                        and event_url != url
                        and (event_url in urls or registered_article_url(event_url))
                        and attempts < 8
                    ):
                        if event_url not in pages:
                            attempts += 1
                            pages[event_url] = self.fetcher(event_url)
                        event_page = pages[event_url]
                    checked = self.clock()
                    stage = "claim_validation"
                    data, published = verified_cause(
                        candidate,
                        page,
                        result,
                        known[key],
                        now=checked,
                        aliases=self.aliases,
                        occurrence_page=event_page,
                    )
                    if existing_data and (
                        existing_data["code"] != data["code"]
                        or not (data["occurred_on"] or data["occurred_month"])
                    ):
                        continue
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
                                "published_on": publication_info(
                                    page,
                                    now=checked,
                                    kickoff=clock(result["fixture"]["kickoff_at"]),
                                )[2],
                                "retrieved_at": page.get("_retrieved_at", checked.isoformat()),
                            }
                        )
                    claim_sources = [sid]
                    if event_page is not page and (data["occurred_on"] or data["occurred_month"]):
                        event_sid = (
                            "web-cause-" + sha256(event_page["url"].encode()).hexdigest()[:16]
                        )
                        _, event_stamp, event_day = publication_info(
                            event_page,
                            now=checked,
                            kickoff=clock(result["fixture"]["kickoff_at"]),
                            max_age=90,
                        )
                        if not any(source["id"] == event_sid for source in result["sources"]):
                            result["sources"].append(
                                {
                                    "id": event_sid,
                                    "fixture_id": result["fixture"]["external_id"],
                                    "kind": "web",
                                    "title": event_page["title"],
                                    "url": event_page["url"],
                                    "published_at": event_stamp,
                                    "published_on": event_day,
                                    "retrieved_at": event_page.get(
                                        "_retrieved_at", checked.isoformat()
                                    ),
                                }
                            )
                        claim_sources.append(event_sid)
                    known[key]["cause"] = {
                        "status": "available",
                        "reason": None,
                        "as_of": checked.isoformat(),
                        "source_ids": claim_sources,
                        "data": data,
                    }
                    seen.add(key)
                    result["as_of"] = max(result["as_of"], checked.isoformat())
                    usage["_evidence"].append(
                        {
                            "source_id": sid,
                            "player_id": key[1],
                            "team_id": key[0],
                            "quote": claim_context(candidate, page, known[key], claim="cause")[1][
                                0
                            ],
                            "occurrence_quote": candidate.get("occurrence_quote"),
                            "cause_quotes": claim_context(
                                candidate, page, known[key], claim="cause"
                            )[1],
                            "occurrence_quotes": candidate.get("occurrence_quotes", []),
                            "occurrence_url": event_page["url"],
                            "occurrence_verified": bool(
                                data["occurred_on"] or data["occurred_month"]
                            ),
                            "occurrence_passage_indices": claim_context(
                                candidate, event_page, known[key], claim="occurrence"
                            )[2]
                            if data["occurred_on"] or data["occurred_month"]
                            else [],
                            "occurrence_page_sha256": event_page["digest"],
                            "cause_passage_indices": claim_context(
                                candidate, page, known[key], claim="cause"
                            )[2],
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
                    safe_code = (
                        code if re.fullmatch(r"[a-z_]{1,80}", code) else "source_request_failed"
                    )
                    usage["cause_diagnostics"].append(
                        {
                            "team_id": key[0],
                            "player_id": key[1],
                            "stage": stage,
                            "code": safe_code,
                            "failure_type": type(exc).__name__,
                            "http_status": exc.response.status_code
                            if isinstance(exc, httpx.HTTPStatusError)
                            else None,
                            "source_host": urlsplit(page["url"] if page else url).hostname,
                            "publication_values": page["dates"][:3] if page else [],
                        }
                    )
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
        usage["cause_occurrence_verified"] = sum(
            bool(
                row.get("cause", {}).get("data")
                and (row["cause"]["data"]["occurred_on"] or row["cause"]["data"]["occurred_month"])
            )
            for row in targets
        )
        # This is the actual completion of the last generative research step, never backdated.
        result["generated_at"] = self.clock().isoformat()
        return PreviewPayload.model_validate(result).root, usage
