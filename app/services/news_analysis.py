"""Read-only, conservative linking of literal article names to database identities."""
import re
import threading
import time
import unicodedata
from collections import deque
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from app.models import Player, PlayerTranslation, Team, TeamTranslation


def validate_source_url(value: str) -> str:
    if len(value) > 2048 or any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ValueError("공백·제어문자 없는 HTTP(S) 출처 URL을 입력하세요.")
    try:
        url = urlsplit(value)
        if (url.scheme.lower() not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None or "\\" in value):
            raise ValueError()
        url.port
    except ValueError:
        raise ValueError("HTTP(S) 출처 URL을 입력하세요. 자격증명은 포함할 수 없습니다.") from None
    return value


class ExtractedMention(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mention: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=600)
    entity_type: str = Field(pattern="^(team|player)$")


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mentions: list[ExtractedMention] = Field(max_length=30)


def normalize(value):
    return " ".join(value.strip().lower().split())


def literal_name_present(mention, evidence, article):
    # Latin fragments must be whole names, never e.g. Arsenal inside NotArsenal.
    if any("LATIN" in unicodedata.name(char, "") for char in mention):
        def latin_word(char):
            return (char == "_" or char.isdigit() or "LATIN" in unicodedata.name(char, "")
                    or unicodedata.category(char).startswith("M"))

        occurrences = [match for match in re.finditer(re.escape(mention), article)
                       if (match.start() == 0 or not latin_word(article[match.start() - 1]))
                       and (match.end() == len(article) or not latin_word(article[match.end()]))]
        for excerpt in re.finditer(re.escape(evidence), article):
            if any(excerpt.start() <= name.start() and name.end() <= excerpt.end()
                   for name in occurrences):
                return True
        return False
    return mention in evidence


def candidates_for(session, kind, mention):
    key = normalize(mention)
    if kind == "team":
        query = select(Team.id, Team.name, Team.slug, TeamTranslation.name_ko).outerjoin(
            TeamTranslation, TeamTranslation.team_id == Team.id
        ).where(or_(func.lower(Team.name) == key, func.lower(TeamTranslation.name_ko) == key)).limit(6)
        return [dict(id=row.id, name=row.name_ko or row.name, slug=row.slug) for row in session.execute(query)]
    full = func.trim(func.coalesce(Player.firstname, "") + " " + func.coalesce(Player.lastname, ""))
    query = select(Player.id, Player.name, Player.slug, Player.firstname, Player.lastname,
                   PlayerTranslation.name_ko).outerjoin(
        PlayerTranslation, PlayerTranslation.player_id == Player.id
    ).where(or_(func.lower(Player.name) == key, func.lower(PlayerTranslation.name_ko) == key,
                func.lower(full) == key)).limit(6)
    candidates = []
    for row in session.execute(query):
        # A single surname/first name cannot establish identity, even when unique in this DB.
        if key in {normalize(row.lastname or ""), normalize(row.firstname or "")}:
            safe = False
        elif key == normalize(row.name_ko or ""):
            safe = len(key) >= 3
        else:
            safe = " " in key and not re.search(r"\b[a-z]\.", key)
        candidates.append(dict(id=row.id, name=row.name_ko or row.name, slug=row.slug, safe=safe))
    return candidates


def link_mentions(session, article_text, source_url, payload):
    extraction = Extraction.model_validate(payload)
    results, seen = [], set()
    for item in extraction.mentions:
        if item.evidence not in article_text or not literal_name_present(item.mention, item.evidence, article_text):
            # Unsupported model claims are never echoed or connected.
            continue
        key = (item.entity_type, normalize(item.mention))
        if key in seen:
            continue
        seen.add(key)
        candidates = candidates_for(session, item.entity_type, item.mention)
        status = ("ambiguous" if len(candidates) > 1 else "linked"
                  if len(candidates) == 1 and candidates[0].get("safe", True) else "unresolved")
        entity = None
        if status == "linked":
            candidate = candidates[0]
            prefix = "teams" if item.entity_type == "team" else "players"
            entity = {"id": candidate["id"], "name": candidate["name"],
                      "detail_path": f"/{prefix}/{quote(candidate['slug'], safe='')}"}
        results.append({**item.model_dump(), "status": status, "entity": entity, "reason": {
            "linked": "원문 이름과 일치하는 DB 대상을 확인했습니다.",
            "ambiguous": "같은 이름의 후보가 여러 명이어서 연결을 보류했습니다.",
            "unresolved": "이 이름만으로 확인할 수 있는 DB 대상이 없어 연결을 보류했습니다.",
        }[status]})
    return {"source_url": source_url, "mentions": results}


class AnalysisLimiter:
    """Single-instance memory budget; no new Redis keys or writes."""
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = {}
        self.slots = threading.BoundedSemaphore(2)

    def admit(self, user_id):
        now = time.monotonic()
        with self.lock:
            self.calls = {key: history for key, history in self.calls.items() if history[-1] > now - 60}
            history = self.calls.setdefault(user_id, deque())
            while history and history[0] <= now - 60:
                history.popleft()
            if len(history) >= 3:
                return False
            history.append(now)
            return True


limiter = AnalysisLimiter()
