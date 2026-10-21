from fastapi.testclient import TestClient

from app.main import app


def test_end_to_end_scenario():
    client = TestClient(app)
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["llm_mode"] == "demo"
    assert status.json()["bank_documents"] == 0

    companies = client.get("/api/companies")
    assert companies.status_code == 200
    assert len(companies.json()["companies"]) >= 5

    kama = client.post("/api/companies/kama-metal/briefing")
    shop = client.post("/api/companies/gorodskaya-polka/briefing")
    assert kama.status_code == 200
    assert shop.status_code == 200
    kama_ids = [item["id"] for item in kama.json()["items"]]
    shop_ids = [item["id"] for item in shop.json()["items"]]
    assert kama_ids[0] == "n-metal"
    assert shop_ids[0] == "n-retail"
    assert "n-metal" not in shop_ids
    assert kama.json()["trace"]

    analysis = client.get("/api/companies/kama-metal/news/n-metal")
    assert analysis.status_code == 200
    body = analysis.json()
    assert body["bank_found"] is False
    assert body["quality"]["passed"] is True
    assert any(step["title"] == "Проверка полноты" for step in body["trace"])

    rate = client.get("/api/companies/kama-metal/news/n-rate")
    assert any(step["title"] == "Результат скорректирован" for step in rate.json()["trace"])

    question = client.post(
        "/api/companies/kama-metal/news/n-metal/questions",
        json={"question": "Кто бенефициар компании?"},
    )
    assert question.status_code == 200
    assert "нет сведений" in question.json()["answer"].lower()

    sparse = client.post("/api/companies/severny-eskiz/briefing")
    assert "выручка" in sparse.json()["profile_gaps"]
    assert client.get("/api/companies/kama-metal/news/n-metal-dup").status_code == 404
    assert client.post("/api/companies/no-such/briefing").status_code == 404
    assert client.post("/api/companies/kama-metal/news/n-metal/questions", json={"question": "a"}).status_code == 422
    assert client.get("/api/health").status_code == 200
    page = client.get("/")
    assert page.status_code == 200
    assert "Бизнес-инсайты" in page.text
