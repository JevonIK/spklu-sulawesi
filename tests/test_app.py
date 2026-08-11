def test_index_is_available(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"SPKLU Sulawesi" in response.data
    assert b"State of Charge" in response.data


def test_health_endpoint_reports_dataset(client):
    response = client.get("/api/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "spklu-sulawesi"
    assert payload["data"]["dataset"]["exists"] is True
    assert payload["data"]["dataset"]["filename"] == "dataset_spklu_sulawesi.csv"

