from fastapi.testclient import TestClient

from app.main import app


def test_preview_uses_new_material_without_polluting_feed():
    client = TestClient(app)
    before = client.get('/api/metrics').json()
    material = {
        'title': 'Новая оценка стоимости кредита для бизнеса',
        'text': 'Ключевая ставка остается неизменной. Компании пересматривают графики финансирования оборотного капитала.',
        'published_at': '2026-10-22',
        'source_url': 'https://example.org/research/new-story',
    }
    result = client.post('/api/companies/u_1595/preview?user_id=shop-treasury', json=material)
    assert result.status_code == 200
    body = result.json()
    assert body['transient'] and body['origin'] == 'user_supplied'
    assert body['title'] == material['title']
    assert body['relevance']['score'] > 0
    assert body['context']['retrieval_attempts']
    after = client.get('/api/metrics').json()
    assert after['analyses'] == before['analyses']
    assert client.get('/api/companies/u_1595/news/' + body['news_id']).status_code == 404
    material['source_url'] = 'javascript:alert(1)'
    assert client.post('/api/companies/u_1595/preview', json=material).status_code == 422


def test_feedback_is_scoped_and_replaces_previous_vote():
    client = TestClient(app)
    url = '/api/companies/u_1595/news/n-rate/feedback?user_id=shop-treasury'
    assert client.post(url, json={'rating': 1}).status_code == 200
    assert client.post(url, json={'rating': -1}).status_code == 200
    feedback = client.get('/api/metrics').json()['feedback']
    assert feedback == {'count': 1, 'positive': 0, 'helpful_rate': 0.0}
    assert client.post(url, json={'rating': 4}).status_code == 422
    assert client.post(url.replace('shop-treasury', 'kama-ceo'), json={'rating': 1}).status_code == 403
    assert client.get('/api/companies/u_1595?user_id=kama-ceo').status_code == 403


def test_research_pdf_is_accessible_but_private_data_is_not():
    client = TestClient(app)
    response = client.get('/bank-pdfs/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf')
    assert response.status_code == 200
    assert response.content.startswith(b'%PDF')
    assert response.headers['content-type'] == 'application/pdf'
    assert client.get('/bank-pdfs/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf.ocr.json').status_code == 404
    assert client.get('/bank-pdfs/..%2Fdf_Uid_data_hack.csv').status_code == 404


def test_whitespace_question_is_rejected():
    client = TestClient(app)
    assert client.post('/api/companies/u_1595/news/n-rate/questions', json={'question': '   '}).status_code == 422
