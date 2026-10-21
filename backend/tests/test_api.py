from fastapi.testclient import TestClient

from app.main import app


def test_end_to_end_scenario():
    client = TestClient(app)
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["llm_mode"] == "demo"
    assert status.json()["bank_documents"] >= 1
    assert status.json()["uid_rows"] >= 5

    users = client.get("/api/users")
    assert users.status_code == 200
    assert any(item["id"] == "kama-treasury" for item in users.json()["users"])

    home = client.get("/api/home", params={"user_id": "kama-ceo"})
    assert home.status_code == 200
    assert home.json()["entry"]["always_visible"] is True

    companies = client.get("/api/companies")
    assert companies.status_code == 200
    ids = [item["id"] for item in companies.json()["companies"]]
    assert "u_200890" in ids
    assert "u_67" not in ids
    assert companies.json()["excluded_total"] > 1000

    kama = client.post("/api/companies/u_200890/briefing")
    shop = client.post("/api/companies/u_1595/briefing")
    assert kama.status_code == 200
    assert shop.status_code == 200
    kama_ids = [item["id"] for item in kama.json()["items"]]
    shop_ids = [item["id"] for item in shop.json()["items"]]
    assert kama_ids[0] == "n-metal"
    assert shop_ids[0] == "n-retail"
    assert "n-metal" not in shop_ids
    assert kama.json()["trace"]

    treasury = client.post("/api/companies/u_1595/briefing", params={"user_id": "shop-treasury"})
    assert treasury.status_code == 200
    assert treasury.json()["items"][0]["id"] == "n-rate"

    forbidden = client.post("/api/companies/u_1595/briefing", params={"user_id": "kama-ceo"})
    assert forbidden.status_code == 403

    analysis = client.get("/api/companies/u_200890/news/n-metal")
    assert analysis.status_code == 200
    body = analysis.json()
    assert body["bank_found"] is True
    assert body["quality"]["passed"] is True
    assert any(step["title"] == "Проверка полноты" for step in body["trace"])

    rate = client.get("/api/companies/u_1595/news/n-rate")
    assert any(step["title"] == "Результат скорректирован" for step in rate.json()["trace"])
    assert rate.json()["bank_found"] is True

    question = client.post(
        "/api/companies/u_200890/news/n-metal/questions",
        json={"question": "Кто бенефициар компании?"},
    )
    assert question.status_code == 200
    assert "обезличен" in question.json()["answer"].lower()

    small = client.post("/api/companies/u_67/briefing")
    assert small.status_code == 200
    assert "платежи" in small.json()["profile_gaps"]
    assert client.get("/api/companies/u_200890/news/n-metal-dup").status_code == 404
    assert client.post("/api/companies/no-such/briefing").status_code == 404
    assert client.post("/api/companies/u_200890/news/n-metal/questions", json={"question": "a"}).status_code == 422
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/metrics").status_code == 200
    page = client.get("/")
    assert page.status_code == 200
    assert "Альфа-Бизнес" in page.text
    docs = client.get("/openapi.json")
    assert docs.status_code == 200
    assert docs.json()["info"]["title"].startswith("Альфа-Бизнес")
