"""Phase 2: ES256 JWT signing and strict structural / cryptographic validation.
Does NOT provide replay prevention, device proof, policy enforcement or access authorization.
"""
import re
import secrets
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

TTL_SECONDS = 30
SKEW_SECONDS = 2
REQUIRED = ["iss", "aud", "sub", "jti", "iat", "nbf", "exp", "room_id", "token_use", "ver"]
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

class InvalidQR(ValueError):
    pass

class QRCodec:
    def __init__(self, private_path, public_path, issuer, audience, kid):
        self.issuer, self.audience, self.kid = issuer, audience, kid
        self.private_key = serialization.load_pem_private_key(Path(private_path).read_bytes(), password=None)
        self.public_key = serialization.load_pem_public_key(Path(public_path).read_bytes())
        if not isinstance(self.private_key, ec.EllipticCurvePrivateKey) or not isinstance(self.private_key.curve, ec.SECP256R1):
            raise ValueError("Private signing key must be P-256 EC")
        if not isinstance(self.public_key, ec.EllipticCurvePublicKey) or not isinstance(self.public_key.curve, ec.SECP256R1):
            raise ValueError("Verification key must be P-256 EC")
        if self.private_key.public_key().public_numbers() != self.public_key.public_numbers():
            raise ValueError("Signing and verification keys do not match")

    def issue(self, uid: str, room_id: str) -> str:
        if not isinstance(uid, str) or not uid or len(uid) > 128:
            raise ValueError("Invalid UID")
        if not isinstance(room_id, str) or not ID_PATTERN.fullmatch(room_id):
            raise ValueError("Invalid room")
        now = int(time.time())
        payload = {
            "iss": self.issuer, "aud": self.audience, "sub": uid,
            "jti": secrets.token_urlsafe(24), "iat": now, "nbf": now,
            "exp": now + TTL_SECONDS, "room_id": room_id,
            "token_use": "facility_access", "ver": 1,
        }
        return jwt.encode(payload, self.private_key, algorithm="ES256", headers={"kid": self.kid, "typ": "facility-access+jwt"})

    def verify(self, token: str) -> dict:
        if not isinstance(token, str) or len(token) > 4096 or token.count(".") != 2:
            raise InvalidQR("Malformed QR token")
        try:
            header = jwt.get_unverified_header(token)
            if set(header) != {"alg", "kid", "typ"}:
                raise InvalidQR("Unexpected JWS header")
            if header != {"alg": "ES256", "kid": self.kid, "typ": "facility-access+jwt"}:
                raise InvalidQR("Untrusted JWS header")
            claims = jwt.decode(
                token, self.public_key,
                algorithms=["ES256"], issuer=self.issuer, audience=self.audience,
                leeway=SKEW_SECONDS,
                options={"require": REQUIRED, "strict_aud": True},
            )
            if set(claims) != set(REQUIRED):
                raise InvalidQR("Unexpected JWT claims")
            for key in ("sub", "jti", "room_id"):
                if not isinstance(claims[key], str) or not claims[key]:
                    raise InvalidQR(f"Invalid {key}")
            if len(claims["sub"]) > 128 or len(claims["jti"]) > 128 or not ID_PATTERN.fullmatch(claims["room_id"]):
                raise InvalidQR("Claim length or format invalid")
            for key in ("iat", "nbf", "exp"):
                if type(claims[key]) is not int:
                    raise InvalidQR(f"Invalid {key} type")
            now = int(time.time())
            if claims["iat"] > now + SKEW_SECONDS or claims["nbf"] > claims["iat"] or claims["exp"] - claims["iat"] != TTL_SECONDS:
                raise InvalidQR("Invalid token time window")
            if claims["token_use"] != "facility_access" or type(claims["ver"]) is not int or claims["ver"] != 1:
                raise InvalidQR("Invalid token purpose/version")
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise InvalidQR("Invalid or expired QR credential") from exc
