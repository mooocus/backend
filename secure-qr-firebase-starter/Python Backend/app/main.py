
"""
Secure QR Phase 2 - FastAPI Backend

Development-only API.

Features:
- Firebase Authentication ID token verification
- Firestore user approval checks
- ES256 JWT/JWS issuance
- Signed QR token validation
- Administrator-only validation endpoint
- Local Flutter Web CORS support
- Detailed authentication error logging

Do not expose this development server directly
to the public internet.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import firebase_admin

from dotenv import load_dotenv

from firebase_admin import (
    auth,
    credentials,
    firestore,
)

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
)

from fastapi.middleware.cors import CORSMiddleware

from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from pydantic import BaseModel, Field

from .qr_crypto import QRCodec, InvalidQR
from .scanner_access import router as scanner_router


# ==================================================
# 1. ENVIRONMENT CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

FIREBASE_PROJECT_ID = os.getenv(
    "FIREBASE_PROJECT_ID",
    "",
).strip()

FIREBASE_CREDENTIAL_FILE = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "",
).strip()

JWT_PRIVATE_KEY_FILE = os.getenv(
    "JWT_PRIVATE_KEY_FILE",
    "./keys/ec-private.pem",
)

JWT_PUBLIC_KEY_FILE = os.getenv(
    "JWT_PUBLIC_KEY_FILE",
    "./keys/ec-public.pem",
)

QR_ISSUER = os.getenv(
    "QR_ISSUER",
    "secure-qr-demo",
)

QR_AUDIENCE = os.getenv(
    "QR_AUDIENCE",
    "facility-verifier",
)

QR_KEY_ID = os.getenv(
    "QR_KEY_ID",
    "issuer-key-v1",
)


# ==================================================
# 2. LOGGING CONFIGURATION
# ==================================================

logger = logging.getLogger("secure_qr")

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)


# ==================================================
# 3. FILE PATH HELPER
# ==================================================

def resolve_path(value: str) -> Path:
    """
    Resolve paths relative to the backend root.
    """
    path = Path(value).expanduser()

    if path.is_absolute():
        return path

    return BASE_DIR / path


# ==================================================
# 4. FIREBASE INITIALIZATION
# ==================================================

def initialize_firebase():
    """
    Initialize Firebase Admin SDK using the
    configured project and service account.

    For local development, a service account
    JSON file may be used.

    For managed cloud deployment, use
    Application Default Credentials.
    """

    if not FIREBASE_PROJECT_ID:
        raise RuntimeError(
            "FIREBASE_PROJECT_ID is missing "
            "from the .env file."
        )

    try:
        firebase_app = firebase_admin.get_app()

        if firebase_app.project_id != FIREBASE_PROJECT_ID:
            raise RuntimeError(
                "The initialized Firebase project "
                "does not match FIREBASE_PROJECT_ID."
            )

        return firebase_app

    except ValueError:
        # No Firebase app has been initialized yet.
        pass

    if FIREBASE_CREDENTIAL_FILE:
        credential_path = resolve_path(
            FIREBASE_CREDENTIAL_FILE
        )

        if not credential_path.is_file():
            raise RuntimeError(
                "Firebase service account file "
                f"not found: {credential_path}"
            )

        credential = credentials.Certificate(
            str(credential_path)
        )

        logger.info(
            "Using configured Firebase "
            "service account."
        )

    else:
        credential = credentials.ApplicationDefault()

        logger.info(
            "Using Application Default Credentials."
        )

    firebase_app = firebase_admin.initialize_app(
        credential,
        {
            "projectId": FIREBASE_PROJECT_ID,
        },
    )

    logger.info(
        "Firebase initialized for project: %s",
        FIREBASE_PROJECT_ID,
    )

    return firebase_app


# ==================================================
# 5. APPLICATION STARTUP
# ==================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Secure QR Phase 2 backend.")

    initialize_firebase()

    app.state.db = firestore.client()

    private_key_path = resolve_path(
        JWT_PRIVATE_KEY_FILE
    )

    public_key_path = resolve_path(
        JWT_PUBLIC_KEY_FILE
    )

    if not private_key_path.is_file():
        raise RuntimeError(
            f"JWT private key not found: {private_key_path}"
        )

    if not public_key_path.is_file():
        raise RuntimeError(
            f"JWT public key not found: {public_key_path}"
        )

    app.state.codec = QRCodec(
        str(private_key_path),
        str(public_key_path),
        QR_ISSUER,
        QR_AUDIENCE,
        QR_KEY_ID,
    )

    logger.info(
        "JWT issuer initialized. Key ID: %s",
        QR_KEY_ID,
    )

    logger.info(
        "Secure QR backend startup complete."
    )

    yield

    logger.info(
        "Secure QR backend shutting down."
    )


# ==================================================
# 6. FASTAPI APPLICATION
# ==================================================

app = FastAPI(
    title="Secure QR Phase 2",
    version="0.2.0",
    lifespan=lifespan,
)


# ==================================================
# 7. LOCAL DEVELOPMENT CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,

    allow_origin_regex=(
        r"^http://(?:localhost|127\.0\.0\.1):[0-9]+$"
    ),

    allow_credentials=False,

    allow_methods=[
        "GET",
        "POST",
        "OPTIONS",
    ],

    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Scanner-ID",
        "X-Scanner-Key",
    ],

    max_age=600,
)


# ==================================================
# 8. REQUEST MODELS
# ==================================================

class VerifyRequest(BaseModel):
    token: str = Field(
        min_length=10,
        max_length=4096,
    )


# ==================================================
# 9. FIREBASE BEARER AUTHENTICATION
# ==================================================

bearer = HTTPBearer(
    auto_error=True,
)


def current_user(
    authorization: HTTPAuthorizationCredentials = Depends(
        bearer
    ),
) -> str:
    """
    Verify the Firebase Authentication ID token.

    Return the authenticated Firebase UID.

    Never trust a UID supplied directly
    by the Flutter application.
    """

    id_token = authorization.credentials

    try:
        decoded = auth.verify_id_token(
            id_token,
            check_revoked=True,
            clock_skew_seconds=5,
        )

        uid = decoded.get("uid")

        if not isinstance(uid, str) or not uid:
            raise auth.InvalidIdTokenError(
                "Firebase token has no valid UID."
            )

        logger.info(
            "Firebase authentication successful."
        )

        return uid

    except auth.ExpiredIdTokenError as exc:
        logger.warning(
            "Firebase token expired: %s",
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=401,
            detail="Firebase session expired",
        ) from exc

    except auth.RevokedIdTokenError as exc:
        logger.warning(
            "Firebase token revoked."
        )

        raise HTTPException(
            status_code=401,
            detail="Firebase session revoked",
        ) from exc

    except auth.UserDisabledError as exc:
        logger.warning(
            "Firebase account disabled."
        )

        raise HTTPException(
            status_code=401,
            detail="Firebase account disabled",
        ) from exc

    except auth.InvalidIdTokenError as exc:
        logger.warning(
            "Firebase ID token rejected: %s",
            str(exc),
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid Firebase authentication",
        ) from exc

    except auth.CertificateFetchError as exc:
        logger.error(
            "Unable to fetch Firebase "
            "verification certificates: %s",
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Firebase authentication "
                "verification unavailable"
            ),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected Firebase authentication "
            "verification failure."
        )

        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        ) from exc


# ==================================================
# 10. ADMINISTRATOR AUTHORIZATION
# ==================================================

def admin_user(
    uid: str = Depends(current_user),
) -> str:
    """
    Confirm the Firebase user is an administrator.
    """

    doc = (
        app.state.db
        .collection("admins")
        .document(uid)
        .get()
    )

    if not doc.exists:
        raise HTTPException(
            status_code=403,
            detail="Administrator required",
        )

    admin_data = doc.to_dict() or {}

    if admin_data.get("role") != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Administrator role required",
        )

    return uid


# ==================================================
# 11. HEALTH CHECK
# ==================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "secure-qr-phase2",
    }


# ==================================================
# 12. ISSUE BACKEND-SIGNED QR JWT
# ==================================================


@app.post("/qr/issue")
def issue(
    uid: str = Depends(current_user),
):
    """
    Issue a room-independent signed QR identity pass.

    Room-specific authorization happens later,
    when a trusted scanner submits the QR for
    validation.
    """

    user_doc = (
        app.state.db
        .collection("users")
        .document(uid)
        .get()
    )

    if not user_doc.exists:
        raise HTTPException(
            status_code=403,
            detail="User registration not found",
        )

    user_data = user_doc.to_dict() or {}

    if user_data.get("status") != "APPROVED":
        raise HTTPException(
            status_code=403,
            detail="Account not approved",
        )

    # QRCodec must be updated to issue
    # a room-independent credential.
    token = app.state.codec.issue(uid)

    logger.info(
        "Room-independent QR credential issued."
    )

    return {
        "token": token,
        "token_type": "facility_identity",
        "expires_in": 30,
    }


@app.post("/qr/validate")
def validate(
    request: VerifyRequest,
    uid: str = Depends(admin_user),
):
    """
    Administrator-only cryptographic validation.

    Does NOT grant physical facility access.

    Replay prevention, device binding, and
    ABAC are implemented in later phases.
    """

    try:
        claims = app.state.codec.verify(
            request.token
        )

    except InvalidQR as exc:
        logger.warning(
            "QR validation failed."
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid or expired QR token",
        ) from exc

    return {
        "cryptographically_valid": True,
        "access_granted": False,
        "claims": claims,
        "warning": (
            "This is not an access decision. "
            "Replay, revocation, device proof, "
            "and ABAC checks are not yet implemented."
        ),
    }


# Authenticated scanner verification and Firestore ABAC checks
app.include_router(scanner_router)
