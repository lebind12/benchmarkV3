"""Actual JWT/manager dependency and read-only DB routing, using only in-memory SQLite."""
import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import db
from app.api.v1 import news_analysis as api
from app.core import sessions
from app.models import AppUser
from app.services.news_analysis import AnalysisLimiter


@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    AppUser.__table__.create(engine)
    with Session(engine) as session:
        for id, role, active in [(1,'STREAMER',True),(2,'ADMIN',True),(3,'USER',True),(4,'ADMIN',False)]:
            session.add(AppUser(id=id, email=f'{id}@example.com', password_hash='test', role=role, is_active=active))
        session.commit()
    with engine.begin() as conn:
        for sql in ['CREATE TABLE team (id INTEGER, name TEXT, slug TEXT)', 'CREATE TABLE team_translation (team_id INTEGER, name_ko TEXT)', "INSERT INTO team VALUES(42,'Arsenal','arsenal')"]:
            conn.execute(text(sql))
    app = FastAPI()
    app.include_router(api.router)
    def session_override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[db.get_db_session] = session_override
    monkeypatch.setattr(sessions, '_secret', lambda: 'test-news-secret-key-with-at-least-32-characters')
    monkeypatch.setattr(api, 'limiter', AnalysisLimiter())
    monkeypatch.setattr(api, 'extract_bounded', lambda article: {'relevance':'football','relevance_evidence':'Arsenal','mentions':[{'mention':'Arsenal','evidence':'Arsenal','entity_type':'team'}]})
    with TestClient(app) as client:
        yield client
    engine.dispose()


def headers(user_id):
    return {'Authorization': 'Bearer '+sessions.encode_token(user_id, 'access', lifetime=60)}


BODY = {'article_text':'Arsenal won.', 'source_url':'https://example.com/article'}
PATH = '/api/v1/admin/management/news/analyze'


def test_real_manager_auth_and_success(client):
    assert client.post(PATH, json=BODY).status_code == 401
    assert client.post(PATH, json=BODY, headers={'Authorization':'Bearer invalid'}).status_code == 401
    assert client.post(PATH, json=BODY, headers=headers(3)).status_code == 403
    assert client.post(PATH, json=BODY, headers=headers(4)).status_code == 401
    for id in (1,2):
        response = client.post(PATH, json=BODY, headers=headers(id))
        assert response.status_code == 200
        assert response.json()['mentions'][0]['entity']['detail_path'] == '/teams/arsenal'


@pytest.mark.parametrize('body', [{**BODY,'article_text':' '}, {**BODY,'article_text':'x'*20001}, {**BODY,'source_url':'javascript:alert(1)'}, {**BODY,'source_url':'https://example.com\n'}, {**BODY,'source_url':'https://user:pass@example.com'}, {**BODY,'source_url':'x'*2049}])
def test_input_rejected_before_model(client, monkeypatch, body):
    def forbidden(article):
        raise AssertionError('provider called for invalid input')
    monkeypatch.setattr(api, 'extract_bounded', forbidden)
    assert client.post(PATH, json=body, headers=headers(1)).status_code == 422


def test_limit_and_safe_error(client, monkeypatch):
    monkeypatch.setattr(api, 'extract_bounded', lambda article: (_ for _ in ()).throw(ValueError('SECRET ARTICLE PAYLOAD')))
    for _ in range(3):
        response = client.post(PATH, json=BODY, headers=headers(1))
        assert response.status_code == 503
        assert 'SECRET' not in response.text and BODY['article_text'] not in response.text
    response = client.post(PATH, json=BODY, headers=headers(1))
    assert response.status_code == 429 and response.headers['Retry-After'] == '60'


def test_timeout_and_empty(client, monkeypatch):
    monkeypatch.setattr(api, 'extract_bounded', lambda article: (_ for _ in ()).throw(TimeoutError()))
    assert client.post(PATH, json=BODY, headers=headers(1)).status_code == 504
    monkeypatch.setattr(api, 'extract_bounded', lambda article: {'relevance':'football','relevance_evidence':'Arsenal','mentions':[]})
    assert client.post(PATH, json=BODY, headers=headers(1)).json()['mentions'] == []


def test_actual_wait_timeout(client, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(api, 'get_settings', lambda: SimpleNamespace(news_analysis_timeout_seconds=0.01))
    monkeypatch.setattr(api, 'extract_bounded', lambda article: gate.wait(1))
    try:
        assert client.post(PATH, json=BODY, headers=headers(1)).status_code == 504
    finally:
        gate.set()


@pytest.mark.parametrize('relevance', ['not_football', 'uncertain'])
def test_api_relevance_and_no_links(client, monkeypatch, relevance):
    monkeypatch.setattr(api, 'extract_bounded', lambda article: {'relevance': relevance, 'relevance_evidence': 'Arsenal', 'mentions': [{'mention':'Arsenal','evidence':'Arsenal','entity_type':'team'}]})
    response = client.post(PATH, json=BODY, headers=headers(1))
    assert response.status_code == 200
    assert response.json()['relevance'] == relevance
    assert response.json()['mentions'] == []


def test_api_missing_relevance_fails_and_bad_evidence_downgrades(client, monkeypatch):
    monkeypatch.setattr(api, 'extract_bounded', lambda article: {'mentions': []})
    assert client.post(PATH, json=BODY, headers=headers(1)).status_code == 503
    monkeypatch.setattr(api, 'extract_bounded', lambda article: {'relevance':'football','relevance_evidence':'invented','mentions': []})
    response = client.post(PATH, json=BODY, headers=headers(1))
    assert response.status_code == 200
    assert response.json()['relevance'] == 'uncertain'
