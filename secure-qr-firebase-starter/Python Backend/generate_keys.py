from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

folder = Path("keys")
folder.mkdir(exist_ok=True)
private_path = folder / "ec-private.pem"
public_path = folder / "ec-public.pem"
if private_path.exists() or public_path.exists():
    raise SystemExit("Key file already exists. Refusing to overwrite.")
private = ec.generate_private_key(ec.SECP256R1())
with private_path.open("xb") as f:
    f.write(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
with public_path.open("xb") as f:
    f.write(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
print("Created signing key pair under keys/. Keep the private key secret.")
