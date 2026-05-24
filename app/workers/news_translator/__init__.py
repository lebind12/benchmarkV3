"""news-translator worker.

Reads pending ``news_article`` rows, turns ESPN/source metadata into a short
Korean title + summary, and fills ``title_ko`` / ``summary_ko`` without
overwriting values that are already present.
"""
from __future__ import annotations

OPENAI_MODEL = "gpt-3.5-turbo"
OPENAI_TEMPERATURE = 0.3
OPENAI_MAX_TOKENS = 400
SEMAPHORE = 5
BATCH_LIMIT = 50
RETRY_MAX = 3
RETRY_BACKOFF_BASE_SEC = 1
POLL_INTERVAL_SEC = 60
FAIL_ALERT_THRESHOLD_CYCLES = 10
