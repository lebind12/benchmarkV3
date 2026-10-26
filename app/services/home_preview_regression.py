"""Count committed-payload tests separately from transport retries without a candidate."""


def is_transport_retry(item):
    status = item.get("http_status")
    return (
        item.get("state") == "transport_retry"
        or status == 429
        or (isinstance(status, int) and status >= 500)
    )


def successful_streak(attempts):
    count = 0
    for item in attempts:
        if is_transport_retry(item):
            continue
        count = count + 1 if item.get("state") == "passed" else 0
    return count
