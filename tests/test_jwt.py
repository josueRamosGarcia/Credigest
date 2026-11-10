"""Pruebas de emision y validacion de JWT."""

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
)
from app.core.security import hash_password


class TestCreateAccessToken:
    """El access token debe ser valido y de corta duracion."""

    def test_round_trip(self) -> None:
        user_id, tenant_id = uuid4(), uuid4()
        token, _, _ = create_access_token(user_id, tenant_id, "prestamista")

        payload = decode_token(token, expected_type="access")

        assert payload.subject == user_id
        assert payload.tenant_id == tenant_id
        assert payload.role == "prestamista"
        assert payload.token_type == "access"

    def test_expires_in_configured_minutes(self) -> None:
        settings = get_settings()
        token, _, expires_at = create_access_token(uuid4(), uuid4(), "admin")
        payload = decode_token(token, expected_type="access")

        delta = payload.expires_at - payload.issued_at
        assert delta == timedelta(minutes=settings.access_token_minutes)
        assert expires_at == payload.expires_at

    def test_has_unique_jti(self) -> None:
        first, jti_one, _ = create_access_token(uuid4(), uuid4(), "admin")
        second, jti_two, _ = create_access_token(uuid4(), uuid4(), "admin")

        assert jti_one != jti_two
        assert decode_token(first, "access").jti == jti_one
        assert decode_token(second, "access").jti == jti_two


class TestCreateRefreshToken:
    """El refresh token dura mas y no sirve como access."""

    def test_expires_in_configured_days(self) -> None:
        settings = get_settings()
        token, _, _ = create_refresh_token(uuid4(), uuid4(), "admin")
        payload = decode_token(token, expected_type="refresh")

        delta = payload.expires_at - payload.issued_at
        assert delta == timedelta(days=settings.refresh_token_days)

    def test_cannot_be_used_as_access(self) -> None:
        token, _, _ = create_refresh_token(uuid4(), uuid4(), "admin")
        with pytest.raises(TokenError, match="Se esperaba"):
            decode_token(token, expected_type="access")

    def test_access_cannot_be_used_as_refresh(self) -> None:
        token, _, _ = create_access_token(uuid4(), uuid4(), "admin")
        with pytest.raises(TokenError, match="Se esperaba"):
            decode_token(token, expected_type="refresh")

    def test_accepts_fixed_jti(self) -> None:
        fixed = uuid4()
        token, jti, _ = create_refresh_token(uuid4(), uuid4(), "admin", token_id=fixed)

        assert jti == fixed
        assert decode_token(token, "refresh").jti == fixed


class TestTokenPayload:
    """El token no debe contener datos personales."""

    def test_does_not_include_personal_data(self) -> None:
        token, _, _ = create_access_token(uuid4(), uuid4(), "admin")
        claims = jwt.decode(token, options={"verify_signature": False})

        assert "email" not in claims
        assert "name" not in claims
        assert "curp" not in claims
        assert set(claims) == {"sub", "tid", "role", "type", "jti", "iat", "exp"}

    def test_role_is_carried_for_quick_authorization(self) -> None:
        token, _, _ = create_access_token(uuid4(), uuid4(), "cobrador")
        assert decode_token(token, "access").role == "cobrador"


class TestTokenValidation:
    """Tokens invalidos deben rechazarse siempre."""

    def test_rejects_garbage(self) -> None:
        with pytest.raises(TokenError, match="no es valido"):
            decode_token("no-es-un-token", "access")

    def test_rejects_empty(self) -> None:
        with pytest.raises(TokenError):
            decode_token("", "access")

    def test_rejects_tampered_signature(self) -> None:
        token, _, _ = create_access_token(uuid4(), uuid4(), "admin")
        tampered = token[:-5] + "AAAAA"

        with pytest.raises(TokenError):
            decode_token(tampered, "access")

    def test_rejects_refresh_token_with_removed_jti(self) -> None:
        token, _, _ = create_access_token(uuid4(), uuid4(), "admin")
        claims = jwt.decode(token, options={"verify_signature": False})
        del claims["jti"]
        forged = jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")

        with pytest.raises(TokenError, match="no es valido"):
            decode_token(forged, "access")

    def test_rejects_expired_token(self) -> None:
        token, _, _ = create_token(
            subject=uuid4(),
            tenant_id=uuid4(),
            role="admin",
            token_type="access",
            expires_delta=timedelta(seconds=-10),
        )

        with pytest.raises(TokenError, match="expiro"):
            decode_token(token, "access")

    def test_rejects_token_signed_with_other_secret(self) -> None:
        claims = {
            "sub": str(uuid4()),
            "tid": str(uuid4()),
            "role": "admin",
            "type": "access",
            "jti": str(uuid4()),
            "iat": 1700000000,
            "exp": 9999999999,
        }
        forged = jwt.encode(
            claims, "otro-secreto-distinto-y-suficientemente-largo", algorithm="HS256"
        )

        with pytest.raises(TokenError, match="no es valido"):
            decode_token(forged, "access")

    def test_rejects_non_uuid_subject(self) -> None:
        claims = {
            "sub": "no-es-uuid",
            "tid": str(uuid4()),
            "role": "admin",
            "type": "access",
            "jti": str(uuid4()),
            "iat": 1700000000,
            "exp": 9999999999,
        }
        forged = jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")

        with pytest.raises(TokenError, match="formato inesperado"):
            decode_token(forged, "access")


class TestPasswordUnrelatedGuard:
    """El hash y el token son independientes: no se puede derivar uno del otro."""

    def test_token_does_not_contain_password_hash(self) -> None:
        password_hash = hash_password("clave-segura-123")
        token, _, _ = create_access_token(uuid4(), uuid4(), "admin")

        assert password_hash not in token
