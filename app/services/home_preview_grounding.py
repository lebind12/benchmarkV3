"""Resolve one-call citations from provider metadata; model-authored URLs are never used."""

import json
import re
from copy import deepcopy
from hashlib import sha256
from urllib.parse import urldefrag, urlsplit

import httpx

from app.services.home_preview_causes import folded
from app.services.home_preview_web import normalized


def quote_key(value):
    return folded(normalized(value)).translate(
        str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
    )


def string_spans(raw):
    """Return JSON value paths and UTF-8 byte offsets, including escaped JSON strings."""
    decoder = json.JSONDecoder()
    spans = []

    def whitespace(index):
        while index < len(raw) and raw[index].isspace():
            index += 1
        return index

    def value(index, path):
        index = whitespace(index)
        if raw[index] == "{":
            index = whitespace(index + 1)
            while raw[index] != "}":
                key, index = decoder.raw_decode(raw, index)
                index = whitespace(index)
                if raw[index] != ":":
                    raise ValueError("invalid_json_object")
                index = whitespace(value(index + 1, path + (key,)))
                if raw[index] == "}":
                    break
                if raw[index] != ",":
                    raise ValueError("invalid_json_separator")
                index = whitespace(index + 1)
            return index + 1
        if raw[index] == "[":
            index, rank = whitespace(index + 1), 0
            while raw[index] != "]":
                index = whitespace(value(index, path + (rank,)))
                rank += 1
                if raw[index] == "]":
                    break
                if raw[index] != ",":
                    raise ValueError("invalid_json_separator")
                index = whitespace(index + 1)
            return index + 1
        parsed, end = decoder.raw_decode(raw, index)
        if isinstance(parsed, str):
            spans.append((path, len(raw[: index + 1].encode()), len(raw[: end - 1].encode())))
        return end

    end = value(0, ())
    if raw[end:].strip():
        raise ValueError("trailing_json_data")
    return spans


def claim_grounding(raw, grounding):
    spans, encoded, links, diagnostics = string_spans(raw), raw.encode(), [], []
    chunks = grounding.get("groundingChunks") or []
    for support in grounding.get("groundingSupports") or []:
        segment = support.get("segment") or {}
        start, end = segment.get("startIndex", 0), segment.get("endIndex")
        if segment.get("partIndex", 0) != 0 or type(start) is not int or type(end) is not int:
            diagnostics.append("unsupported_segment")
            continue
        if not 0 <= start < end <= len(encoded):
            diagnostics.append("invalid_segment_range")
            continue
        try:
            actual = encoded[start:end].decode()
        except UnicodeDecodeError:
            diagnostics.append("invalid_segment_utf8")
            continue
        if segment.get("text") != actual:
            diagnostics.append("segment_text_mismatch")
            continue
        indices = [
            i
            for i in support.get("groundingChunkIndices", [])
            if type(i) is int and 0 <= i < len(chunks) and (chunks[i].get("web") or {}).get("uri")
        ]
        for path, low, high in spans:
            if max(start, low) < min(end, high) and path[-1] in {
                "text",
                "reason",
                "summary",
                "claim",
                "quote",
                "timing_text",
                "date_basis",
            }:
                links.append(
                    {
                        "path": list(path),
                        "chunk_indices": indices,
                        "segment_text": actual,
                        "start_byte": start,
                        "end_byte": end,
                    }
                )
    return links, diagnostics


def reference_roots(value, source_id, path=()):
    roots = []
    if isinstance(value, dict):
        if source_id in value.get("source_ids", []) or source_id in value.get("evidence_ids", []):
            roots.append(path)
        for key, item in value.items():
            roots.extend(reference_roots(item, source_id, path + (key,)))
    elif isinstance(value, list):
        for rank, item in enumerate(value):
            roots.extend(reference_roots(item, source_id, path + (rank,)))
    return roots


def source_quotes(value, source_id):
    found = []
    if isinstance(value, dict):
        if value.get("source_id") == source_id and value.get("quote"):
            found.append(value["quote"])
        for child in value.values():
            found.extend(source_quotes(child, source_id))
    elif isinstance(value, list):
        for child in value:
            found.extend(source_quotes(child, source_id))
    return list(dict.fromkeys(found))


def publisher_matches(publisher, url):
    key = re.sub(r"[^a-z0-9]", "", folded(publisher))
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    aliases = {"sportsillustrated": {"si.com"}, "goalcom": {"goal.com"}}
    if key in aliases:
        return any(host == domain or host.endswith("." + domain) for domain in aliases[key])
    labels = host.split(".")
    root = (
        labels[-3]
        if len(labels) >= 3 and ".".join(labels[-2:]) in {"co.uk", "org.uk", "com.au", "co.nz"}
        else labels[-2]
        if len(labels) >= 2
        else ""
    )
    return bool(key) and key == re.sub(r"[^a-z0-9]", "", root)


def resolve_sources(raw, grounding, *, fetcher, reference_urls=()):
    """Keep response prose unchanged; add authoritative source URLs and per-field citations.

    reference_urls must be supplied by the caller (e.g. explicit user references), never
    copied from model JSON. Grounding links identify attribution, not factual truth.
    """
    value = json.loads(raw)
    result = deepcopy(value)
    links, diagnostics = claim_grounding(raw, grounding)
    chunks = grounding.get("groundingChunks") or []
    queue = [
        ((chunk.get("web") or {}).get("uri"), "google_grounding", i)
        for i, chunk in enumerate(chunks)
    ]
    queue.extend((url, "user_reference", None) for url in reference_urls)
    pages, fetched, failures = [], {}, []
    for url, origin, index in queue[:14]:
        if not url or not url.startswith("https://"):
            continue
        if url not in fetched:
            try:
                fetched[url] = fetcher(url)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                failures.append(
                    {
                        "origin": origin,
                        "chunk_index": index,
                        "url": url,
                        "failure_type": type(exc).__name__,
                        "reason": str(exc)[:100],
                    }
                )
                fetched[url] = None
            except httpx.HTTPError as exc:
                # Network diagnostics contain status/type only, never response headers/body.
                row = {
                    "origin": origin,
                    "chunk_index": index,
                    "url": url,
                    "failure_type": type(exc).__name__,
                }
                if hasattr(exc, "response"):
                    row["http_status"] = exc.response.status_code
                failures.append(row)
                fetched[url] = None
        page = fetched[url]
        if page:
            pages.append(
                {
                    "page": page,
                    "origin": origin,
                    "chunk_index": index,
                    "url": urldefrag(page["url"])[0],
                }
            )
    resolved = []
    for source in result["source_catalog"]:
        source_id = source["id"]
        quotes = source_quotes(value, source_id)
        roots = reference_roots(value, source_id)
        indices = {
            i
            for link in links
            for root in roots
            if tuple(link["path"][: len(root)]) == root
            for i in link["chunk_indices"]
        }
        matches = []
        for row in pages:
            if not publisher_matches(source["publisher"], row["url"]):
                continue
            hits = [quote_key(q) in quote_key(row["page"]["text"]) for q in quotes]
            if (quotes and any(hits)) or (not quotes and row["chunk_index"] in indices):
                matches.append({**row, "quote_matches": hits})
        urls = {row["url"] for row in matches}
        source.update(url=None, published_on=None, published_at=None, verification="unresolved")
        record = {"id": source_id, "state": "unresolved", "quote_count": len(quotes)}
        if len(urls) == 1:
            row = matches[0]
            state = (
                ("original_quote_matched" if all(row["quote_matches"]) else "partial_quote_match")
                if quotes
                else "grounding_linked"
            )
            source.update(url=row["url"], title=row["page"]["title"], verification=state)
            record.update(
                state=state,
                url=row["url"],
                origin=row["origin"],
                chunk_index=row["chunk_index"],
                quote_matches=row["quote_matches"],
            )
            # Only actual original metadata determines publication values.
            for date_value in row["page"].get("dates", [])[:1]:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
                    source["published_on"] = date_value
                else:
                    from app.schemas.home_preview import clock

                    try:
                        stamp = clock(date_value)
                        if stamp.tzinfo is not None:
                            source.update(
                                published_on=stamp.date().isoformat(),
                                published_at=stamp.isoformat(),
                            )
                    except (ValueError, TypeError):
                        pass
        elif len(urls) > 1:
            record["state"] = "ambiguous_original"
        resolved.append(record)
    # Attribution stays separate from the model's possibly incorrect evidence_ids.
    for link in links:
        link["source_ids"] = []
        for index in link["chunk_indices"]:
            uri = chunks[index]["web"]["uri"]
            page = fetched.get(uri)
            actual_url = urldefrag(page["url"])[0] if page else uri
            sid = "grounding-" + sha256(actual_url.encode()).hexdigest()[:12]
            link["source_ids"].append(sid)
            if not any(s["id"] == sid for s in result["source_catalog"]):
                result["source_catalog"].append(
                    {
                        "id": sid,
                        "url": actual_url,
                        "title": page["title"]
                        if page
                        else chunks[index]["web"].get("title", "Google Search"),
                        "publisher": urlsplit(actual_url).hostname,
                        "published_on": None,
                        "published_at": None,
                        "verification": "grounding_attribution",
                    }
                )
    result["grounding_links"] = links
    report = {
        "model_urls_used": 0,
        "sources": resolved,
        "fetch_failures": failures,
        "segment_diagnostics": diagnostics,
        "claim_links": len(links),
    }
    return result, report, pages
