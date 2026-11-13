import time
import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from app.qr_crypto import QRCodec, InvalidQR

@pytest.fixture
def codec(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    pri = tmp_path / "pri.pem"
    pub = tmp_path / "pub.pem"
    pri.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return QRCodec(pri, pub, "secure-qr-demo", "facility-verifier", "issuer-key-v1")

def test_valid(codec):
    t = codec.issue("user123")
    d = codec.verify(t)
    assert d["sub"] == "user123"
    assert d["exp"] - d["iat"] == 30

def test_unique_jti(codec):
    a = codec.verify(codec.issue("user123"))
    b = codec.verify(codec.issue("user123"))
    assert a["jti"] != b["jti"]

def test_tamper(codec):
    t = codec.issue("user123")
    h, p, s = t.split(".")
    changed = ("A" if p[0] != "A" else "B") + p[1:]
    with pytest.raises(InvalidQR):
        codec.verify(f"{h}.{changed}.{s}")

def test_wrong_audience(codec):
    t = codec.issue("user123")
    claims = jwt.decode(t, codec.public_key, algorithms=["ES256"], options={"verify_aud":False})
    claims["aud"] = "other"
    forged = jwt.encode(claims, codec.private_key, algorithm="ES256", headers={"kid":"issuer-key-v1","typ":"facility-identity+jwt"})
    with pytest.raises(InvalidQR):
        codec.verify(forged)

def test_expired(codec):
    t = codec.issue("user123")
    claims = jwt.decode(t, codec.public_key, algorithms=["ES256"], options={"verify_aud":False})
    claims["iat"] = int(time.time()) - 100
    claims["nbf"] = claims["iat"]
    claims["exp"] = claims["iat"] + 30
    expired = jwt.encode(claims, codec.private_key, algorithm="ES256", headers={"kid":"issuer-key-v1","typ":"facility-identity+jwt"})
    with pytest.raises(InvalidQR):
        codec.verify(expired)

def test_unsigned_rejected(codec):
    with pytest.raises(InvalidQR):
        codec.verify("abc.def.ghi")

def test_claims_are_room_independent(codec):
    d = codec.verify(codec.issue("user123"))
    assert set(d) == {"iss", "aud", "sub", "jti", "iat", "nbf", "exp", "token_use", "ver"}
    assert d["token_use"] == "facility_identity"
    assert d["ver"] == 2
    assert "room" not in d and "role" not in d

def test_old_room_bound_token_rejected(codec):
    t = codec.issue("user123")
    claims = jwt.decode(t, codec.public_key, algorithms=["ES256"], options={"verify_aud": False})
    claims["room"] = "LAB_A"
    claims["ver"] = 1
    old = jwt.encode(claims, codec.private_key, algorithm="ES256",
                     headers={"kid": "issuer-key-v1", "typ": "facility-access+jwt"})
    with pytest.raises(InvalidQR):
        codec.verify(old)
