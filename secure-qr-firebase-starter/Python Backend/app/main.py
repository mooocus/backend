"""Development-only API; do not expose directly to the public internet."""
import os
from contextlib import asynccontextmanager

import firebase_admin
from firebase_admin import auth, credentials, firestore
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from .qr_crypto import QRCodec, InvalidQR

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": os.environ["FIREBASE_PROJECT_ID"]})
    app.state.db = firestore.client()
    app.state.codec = QRCodec(
        os.environ["JWT_PRIVATE_KEY_FILE"], os.environ["JWT_PUBLIC_KEY_FILE"],
        os.environ.get("QR_ISSUER", "secure-qr-demo"),
        os.environ.get("QR_AUDIENCE", "facility-verifier"),
        os.environ.get("QR_KEY_ID", "issuer-key-v1"),
    )
    yield

app = FastAPI(title="Secure QR Phase 2", lifespan=lifespan)

class IssueRequest(BaseModel):
    room_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")

class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


bearer = HTTPBearer()

def current_user(authorization: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    try:
        result = auth.verify_id_token(authorization.credentials, check_revoked=True)
        return result["uid"]
    except Exception:
        raise HTTPException(401, "Invalid Firebase authentication") from None


def admin_user(uid: str = Depends(current_user)) -> str:
    doc = app.state.db.collection("admins").document(uid).get()
    if not doc.exists:
        raise HTTPException(403, "Administrator required")
    return uid

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/qr/issue")
def issue(request: IssueRequest, uid: str = Depends(current_user)):
    user = app.state.db.collection("users").document(uid).get()
    if not user.exists or (user.to_dict() or {}).get("status") != "APPROVED":
        raise HTTPException(403, "Account not approved")
    # Phase 2: this confirms room existence only; room eligibility is deferred to ABAC phase.
    room = app.state.db.collection("rooms").document(request.room_id).get()
    if not room.exists:
        raise HTTPException(404, "Unknown room")
    token = app.state.codec.issue(uid, request.room_id)
    return {"token": token, "token_type": "facility_access", "expires_in": 30}

@app.post("/qr/validate")
def validate(request: VerifyRequest, _: str = Depends(admin_user)):
    """Admin-only cryptographic test; not a door-opening decision."""
    try:
        claims = app.state.codec.verify(request.token)
    except InvalidQR:
        raise HTTPException(400, "Invalid or expired QR token") from None
    return {"cryptographically_valid": True, "access_granted": False, "claims": claims, "warning": "Not an access decision: no replay, revocation, device proof or ABAC checks."}
