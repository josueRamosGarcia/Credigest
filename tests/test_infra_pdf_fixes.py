"""Pruebas unitarias para PDF del pagare, storage, rate limiter y configuracion."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.storage import (
    InvalidFileError,
    LocalStorage,
    StorageError,
    validate_file_signature,
)
from app.models.client import Client
from app.models.loan import Loan
from app.models.tenant import Tenant
from app.pdf.generator import build_context, render_pagare_html


class TestPagareTemplateFixes:
    """Sin M.N. duplicado y con concordancia plural en clausula 1."""

    def test_no_duplicate_mn_and_plural_frequency(self) -> None:
        tenant = Tenant(name="Financiera Demo", slug="demo")
        client = Client(
            full_name="Maria Lopez",
            curp="LOPJ850312MDFZRN00",
            phone="8711234567",
            address="Av. Juarez 123",
        )
        loan = Loan(
            id=uuid4(),
            principal=Decimal("10000.00"),
            interest_rate=Decimal("0.0500"),
            rate_period="semanal",
            scheme="simple",
            term_periods=12,
            start_date=date(2026, 11, 2),
            first_due_date=date(2026, 11, 9),
            end_date=date(2027, 1, 25),
            total_interest=Decimal("6000.00"),
            total_amount=Decimal("16000.00"),
            late_fee_rate=Decimal("0.1000"),
            grace_days=5,
        )

        html = render_pagare_html(
            build_context(tenant=tenant, client=client, loan=loan, issued_date=date(2026, 11, 10))
        )

        assert "M.N. M.N." not in html
        assert "12 pagos semanales" in html


class TestStorageHardening:
    """Magic bytes y proteccion contra traversal en save()."""

    def test_validates_real_signatures(self) -> None:
        validate_file_signature(b"%PDF-1.4\nbody", "application/pdf")
        validate_file_signature(b"\xff\xd8\xff\xe0jpeg", "image/jpeg")
        validate_file_signature(b"\x89PNG\r\n\x1a\npng", "image/png")
        validate_file_signature(b"RIFF1234WEBPdata", "image/webp")

    def test_rejects_mismatched_signature(self) -> None:
        with pytest.raises(InvalidFileError, match="no coincide"):
            validate_file_signature(b"<html>fake</html>", "application/pdf")

    def test_save_rejects_traversal_in_doc_type(self, tmp_path: Path) -> None:
        storage = LocalStorage(tmp_path)
        with pytest.raises(StorageError, match="no valido"):
            storage.save(uuid4(), uuid4(), "../../etc/evil", b"%PDF-1.4", "application/pdf")


class TestRateLimiterPruning:
    """Los buckets vacios se eliminan para no filtrar memoria."""

    def test_prunes_expired_bucket_key(self) -> None:
        limiter = RateLimiter(limit=2, window_seconds=10)
        limiter.hit("1.2.3.4", now=0.0)
        assert "1.2.3.4" in limiter._buckets

        allowed, retry = limiter.check("1.2.3.4", now=15.0)
        assert allowed is True
        assert retry == 0
        assert "1.2.3.4" not in limiter._buckets


class TestProductionConfig:
    """Impide arrancar en produccion con el JWT secret de desarrollo."""

    def test_rejects_default_secret_in_production(self) -> None:
        with pytest.raises(ValidationError, match="JWT_SECRET"):
            Settings(environment="production")

    def test_accepts_strong_secret_in_production(self) -> None:
        cfg = Settings(
            environment="production",
            jwt_secret="s" * 40,
            cors_origins="https://app.credigest.mx, https://admin.credigest.mx",
        )
        assert cfg.cors_origins_list == [
            "https://app.credigest.mx",
            "https://admin.credigest.mx",
        ]
