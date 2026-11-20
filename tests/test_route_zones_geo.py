"""Pruebas unitarias de direccion estructurada, coordenadas y zonas de ruta."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.client import ClientCreate, ClientUpdate, compose_address
from app.schemas.collection_route import RouteItemRead, ZoneOption

VALID_CURP = "LOPJ850312MDFZRN00"


class TestStructuredAddressAndGeo:
    """Composicion automatica de direccion y validacion de coordenadas."""

    def test_compose_address_full_torreon(self) -> None:
        result = compose_address(
            street="Av. Juarez",
            exterior_number="123",
            neighborhood="Centro",
            postal_code="27000",
            city="Torreon",
            state="Coahuila",
        )
        assert result == "Av. Juarez 123, Col. Centro, C.P. 27000, Torreon, Coahuila"

    def test_client_create_composes_address_from_parts(self) -> None:
        payload = ClientCreate(
            full_name="Maria Lopez Perez",
            curp=VALID_CURP,
            phone="8711234567",
            street="Calzada Colon",
            exterior_number="450",
            neighborhood="Centro",
            postal_code="27000",
            city="Torreon",
            state="Coahuila",
            latitude=Decimal("25.542800"),
            longitude=Decimal("-103.406800"),
            zone="Centro",
        )
        assert payload.address == "Calzada Colon 450, Col. Centro, C.P. 27000, Torreon, Coahuila"
        assert payload.latitude == Decimal("25.542800")
        assert payload.longitude == Decimal("-103.406800")

    def test_client_create_keeps_legacy_plain_address(self) -> None:
        payload = ClientCreate(
            full_name="Maria Lopez Perez",
            curp=VALID_CURP,
            phone="8711234567",
            address="Av. Juarez 123, Col. Centro, Torreon, Coahuila",
        )
        assert payload.address == "Av. Juarez 123, Col. Centro, Torreon, Coahuila"
        assert payload.latitude is None

    def test_client_create_rejects_missing_address(self) -> None:
        with pytest.raises(ValidationError, match="direccion"):
            ClientCreate(
                full_name="Maria Lopez Perez",
                curp=VALID_CURP,
                phone="8711234567",
            )

    def test_client_create_rejects_partial_coordinates(self) -> None:
        with pytest.raises(ValidationError, match="latitud como la longitud"):
            ClientCreate(
                full_name="Maria Lopez Perez",
                curp=VALID_CURP,
                phone="8711234567",
                address="Av. Juarez 123, Torreon",
                latitude=Decimal("25.542800"),
            )

    def test_client_update_rejects_out_of_range_latitude(self) -> None:
        with pytest.raises(ValidationError):
            ClientUpdate(latitude=Decimal("95.000000"), longitude=Decimal("-103.400000"))

    def test_route_schemas_accept_zone_and_coordinates(self) -> None:
        zone = ZoneOption(zone="Centro", active_clients=4, pending_installments=2)
        assert zone.pending_installments == 2

        item = RouteItemRead(
            id=uuid4(),
            client_id=uuid4(),
            loan_id=uuid4(),
            installment_id=uuid4(),
            order_index=1,
            visit_status="pendiente",
            notes=None,
            client_name="Maria Lopez",
            client_address="Calzada Colon 450, Col. Centro, Torreon, Coahuila",
            client_neighborhood="Centro",
            client_latitude=Decimal("25.542800"),
            client_longitude=Decimal("-103.406800"),
            client_phone="8711234567",
            installment_number=1,
            due_date="2026-11-20",  # type: ignore[arg-type]
            amount_due=Decimal("500.00"),
            late_fee=Decimal("0.00"),
            total_due=Decimal("500.00"),
        )
        assert item.client_latitude == Decimal("25.542800")
        assert item.client_neighborhood == "Centro"
