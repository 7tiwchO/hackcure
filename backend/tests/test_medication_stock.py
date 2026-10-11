import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_stock_settings_are_saved_only_for_patient_medication(client: AsyncClient, auth_headers):
    headers = await auth_headers(client)
    medications_response = await client.get("/api/v1/patients/me/medications", headers=headers)
    assert medications_response.status_code == 200
    medication = medications_response.json()[0]

    update_response = await client.put(
        f"/api/v1/patients/me/medications/{medication['id']}/stock",
        headers=headers,
        json={"stock_remaining": 23, "stock_reminder_enabled": True, "stock_reminder_threshold": 8},
    )
    assert update_response.status_code == 200
    assert update_response.json()["stock_remaining"] == 23
    assert update_response.json()["stock_reminder_enabled"] is True
    assert update_response.json()["stock_reminder_threshold"] == 8

    detail_response = await client.get(
        f"/api/v1/patients/me/medications/{medication['id']}", headers=headers
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["stock_remaining"] == 23

    invalid_response = await client.put(
        f"/api/v1/patients/me/medications/{medication['id']}/stock",
        headers=headers,
        json={"stock_remaining": -1, "stock_reminder_enabled": True, "stock_reminder_threshold": 0},
    )
    assert invalid_response.status_code == 422

    hidden_medication_response = await client.put(
        "/api/v1/patients/me/medications/00000000-0000-0000-0000-000000000000/stock",
        headers=headers,
        json={"stock_remaining": 4, "stock_reminder_enabled": True, "stock_reminder_threshold": 5},
    )
    assert hidden_medication_response.status_code == 404
