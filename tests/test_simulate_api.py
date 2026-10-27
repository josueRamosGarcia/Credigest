"""Pruebas de integracion del endpoint de simulacion."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> Any:
    """Cliente HTTP conectado directamente a la app, sin red."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


SIMPLE_PAYLOAD = {
    "principal": 10000,
    "interest_rate": 0.05,
    "rate_period": "semanal",
    "scheme": "simple",
    "term_periods": 12,
    "start_date": "2026-11-02",
}


class TestSimulateSuccess:
    """Camino feliz: el ejemplo documentado en docs/02-arquitectura.md."""

    async def test_returns_200(self, client: Any) -> None:
        response = await client.post("/api/v1/loans/simulate", json=SIMPLE_PAYLOAD)
        assert response.status_code == 200

    async def test_totals_match_documentation(self, client: Any) -> None:
        response = await client.post("/api/v1/loans/simulate", json=SIMPLE_PAYLOAD)
        body = response.json()

        assert body["installment_amount"] == "1333.33"
        assert body["total_interest"] == "6000.00"
        assert body["total_amount"] == "16000.00"
        assert body["estimated_profit"] == "6000.00"

    async def test_end_date(self, client: Any) -> None:
        response = await client.post("/api/v1/loans/simulate", json=SIMPLE_PAYLOAD)
        assert response.json()["end_date"] == "2027-01-25"

    async def test_schedule_has_twelve_rows(self, client: Any) -> None:
        response = await client.post("/api/v1/loans/simulate", json=SIMPLE_PAYLOAD)
        schedule = response.json()["schedule"]

        assert len(schedule) == 12
        assert schedule[0]["number"] == 1
        assert schedule[-1]["balance"] == "0.00"

    async def test_first_row_details(self, client: Any) -> None:
        response = await client.post("/api/v1/loans/simulate", json=SIMPLE_PAYLOAD)
        first = response.json()["schedule"][0]

        assert first["due_date"] == "2026-11-09"
        assert first["amount"] == "1333.33"
        assert first["interest_part"] == "500.00"
        assert first["principal_part"] == "833.33"
        assert first["balance"] == "9166.67"

    async def test_money_is_returned_as_string(self, client: Any) -> None:
        """RN-01: los importes no pasan por float en ningun punto."""
        response = await client.post("/api/v1/loans/simulate", json=SIMPLE_PAYLOAD)
        body = response.json()

        assert isinstance(body["total_amount"], str)
        assert isinstance(body["schedule"][0]["amount"], str)

    async def test_annual_equivalent_is_informative(self, client: Any) -> None:
        response = await client.post("/api/v1/loans/simulate", json=SIMPLE_PAYLOAD)
        assert response.json()["annual_equivalent_rate"] == "11.6428"


class TestSimulateDeclining:
    """RN-13: en saldo insoluto la primera y la ultima cuota difieren."""

    async def test_first_and_last_differ(self, client: Any) -> None:
        payload = {
            "principal": 10000,
            "interest_rate": 0.03,
            "rate_period": "mensual",
            "scheme": "saldo_insoluto",
            "term_periods": 4,
            "start_date": "2026-11-02",
        }
        response = await client.post("/api/v1/loans/simulate", json=payload)
        body = response.json()

        assert body["installment_amount"] == "2800.00"
        assert body["installment_amount_last"] == "2575.00"
        assert body["total_interest"] == "750.00"

    async def test_fixed_payment_has_equal_installments(self, client: Any) -> None:
        payload = {
            "principal": 10000,
            "interest_rate": 0.03,
            "rate_period": "mensual",
            "scheme": "cuota_fija",
            "term_periods": 12,
            "start_date": "2026-11-02",
        }
        response = await client.post("/api/v1/loans/simulate", json=payload)
        body = response.json()

        assert body["installment_amount"] == "1004.62"
        assert body["installment_amount_last"] == "1004.62"


class TestSimulateValidation:
    """Errores de entrada: siempre 422, nunca 500."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("principal", 0),
            ("principal", -100),
            ("interest_rate", -0.01),
            ("term_periods", 0),
            ("term_periods", -5),
        ],
    )
    async def test_rejects_invalid_numbers(self, client: Any, field: str, value: Any) -> None:
        payload = {**SIMPLE_PAYLOAD, field: value}
        response = await client.post("/api/v1/loans/simulate", json=payload)
        assert response.status_code == 422

    async def test_rejects_unknown_frequency(self, client: Any) -> None:
        payload = {**SIMPLE_PAYLOAD, "rate_period": "diaria"}
        response = await client.post("/api/v1/loans/simulate", json=payload)

        assert response.status_code == 422
        assert "Frecuencia no valida" in response.json()["detail"]

    async def test_rejects_unknown_scheme(self, client: Any) -> None:
        payload = {**SIMPLE_PAYLOAD, "scheme": "compuesto"}
        response = await client.post("/api/v1/loans/simulate", json=payload)

        assert response.status_code == 422
        assert "Esquema no valido" in response.json()["detail"]

    async def test_rejects_missing_fields(self, client: Any) -> None:
        response = await client.post("/api/v1/loans/simulate", json={"principal": 1000})
        assert response.status_code == 422

    async def test_rejects_invalid_date(self, client: Any) -> None:
        payload = {**SIMPLE_PAYLOAD, "start_date": "no-es-fecha"}
        response = await client.post("/api/v1/loans/simulate", json=payload)
        assert response.status_code == 422

    async def test_rejects_more_than_two_decimals(self, client: Any) -> None:
        """Un monto con centavos de mas debe rechazarse, no redondearse en silencio."""
        payload = {**SIMPLE_PAYLOAD, "principal": "10000.555"}
        response = await client.post("/api/v1/loans/simulate", json=payload)
        assert response.status_code == 422

    async def test_rejects_principal_too_large_for_column(self, client: Any) -> None:
        payload = {**SIMPLE_PAYLOAD, "principal": "99999999999999999"}
        response = await client.post("/api/v1/loans/simulate", json=payload)
        assert response.status_code == 422


class TestOpenApi:
    """La documentacion debe exponer el endpoint."""

    async def test_simulate_is_documented(self, client: Any) -> None:
        response = await client.get("/openapi.json")
        paths = response.json()["paths"]

        assert "/api/v1/loans/simulate" in paths
        assert "post" in paths["/api/v1/loans/simulate"]
