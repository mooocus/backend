"""ES256-signed, room-independent identity QR credentials (Phase 2).

The scanner's authenticated identity determines the room. This module verifies
JWT integrity and freshness only; it does NOT authorize door access, prevent
replay, prove biometric use, or validate scanner identity.
"""

import secrets
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

TTL_SECONDS = 30
SKEW_SECONDS = 2
REQUIRED = ("iss", "aud", "sub", "jti", "iat", "nbf", "exp", "token_use", "ver")
TOKEN_USE = "facility_identity"
TOKEN_TYPE = "facility-identity+jwt"
TOKEN_VERSION = 2


class InvalidQR(ValueError):
    """Raised when a signed QR credential is malformed, invalid, or expired."""


class QRCodec:
    def __init__(self, private_path, public_path, issuer, audience, kid):
        self.issuer, self.audience, self.kid = issuer, audience, kid
        self.private_key = serialization.load_pem_private_key(
            Path(private_path).read_bytes(), password=None
        )
        self.public_key = serialization.load_pem_public_key(
            Path(public_path).read_bytes()
        )
        if (
            not isinstance(self.private_key, ec.EllipticCurvePrivateKey)
            or not isinstance(self.private_key.curve, ec.SECP256R1)
        ):
            raise ValueError("Private signing key must be P-256 EC")
        if (
            not isinstance(self.public_key, ec.EllipticCurvePublicKey)
            or not isinstance(self.public_key.curve, ec.SECP256R1)
        ):
            raise ValueError("Verification key must be P-256 EC")
        if (
            self.private_key.public_key().public_numbers()
            != self.public_key.public_numbers()
        ):
            raise ValueError("Signing and verification keys do not match")

    def issue(self, uid: str) -> str:
        """Issue one 30-second credential identifying a Firebase user, not a room."""
        if not isinstance(uid, str) or not uid or len(uid) > 128:
            raise ValueError("Invalid UID")

        now = int(time.time())
        payload = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": uid,
            "jti": secrets.token_urlsafe(24),
            "iat": now,
            "nbf": now,
            "exp": now + TTL_SECONDS,
            "token_use": TOKEN_USE,
            "ver": TOKEN_VERSION,
        }
        return jwt.encode(
            payload,
            self.private_key,
            algorithm="ES256",
            headers={"kid": self.kid, "typ": TOKEN_TYPE},
        )

    def verify(self, token: str) -> dict:
        """Verify cryptographic authenticity and time limits, NOT access rights."""
        if not isinstance(token, str) or len(token) > 4096 or token.count(".") != 2:
            raise InvalidQR("Malformed QR token")
        try:
            header = jwt.get_unverified_header(token)
            if header != {"alg": "ES256", "kid": self.kid, "typ": TOKEN_TYPE}:
                raise InvalidQR("Untrusted JWS header")

            claims = jwt.decode(
                token,
                self.public_key,
                algorithms=["ES256"],
                issuer=self.issuer,
                audience=self.audience,
                leeway=SKEW_SECONDS,
                options={"require": list(REQUIRED), "strict_aud": True},
            )
            if set(claims) != set(REQUIRED):
                raise InvalidQR("Unexpected JWT claims")
            for key in ("sub", "jti"):
                if not isinstance(claims[key], str) or not claims[key]:
                    raise InvalidQR(f"Invalid {key}")
            if len(claims["sub"]) > 128 or len(claims["jti"]) > 128:
                raise InvalidQR("Claim length invalid")
            for key in ("iat", "nbf", "exp"):
                if type(claims[key]) is not int:
                    raise InvalidQR(f"Invalid {key} type")
            now = int(time.time())
            if (
                claims["iat"] > now + SKEW_SECONDS
                or claims["nbf"] > claims["iat"]
                or claims["exp"] - claims["iat"] != TTL_SECONDS
            ):
                raise InvalidQR("Invalid token time window")
            if (
                claims["token_use"] != TOKEN_USE
                or type(claims["ver"]) is not int
                or claims["ver"] != TOKEN_VERSION
            ):
                raise InvalidQR("Invalid token purpose/version")
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise InvalidQR("Invalid or expired QR credential") from exc
