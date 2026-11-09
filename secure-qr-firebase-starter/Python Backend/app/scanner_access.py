"""Online scanner verification + ABAC. Add to FastAPI via app.include_router(router).

The scanner secret and room assignment are server controlled. A QR contains only
user identity; room access is determined by the authenticated scanner's room.
This module is intentionally online-only and fail-closed.
"""
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from google.api_core.exceptions import AlreadyExists, GoogleAPICallError
from pydantic import BaseModel, Field
from firebase_admin import auth

from .qr_crypto import InvalidQR

router = APIRouter(prefix='/scanner', tags=['Scanner access'])
log = logging.getLogger('secure_qr.scanner')
LOCAL_ZONE = ZoneInfo(os.getenv('ACCESS_TIME_ZONE', 'Asia/Singapore'))


class ScanRequest(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


def _scanner_identity(scanner_id: str, scanner_key: str, db):
    """Server-side scanner authentication and room binding.

    Provision scanner secrets as SCANNER_KEYS_JSON={"scanner-001":"random-secret"}.
    Never accept a room ID supplied by the scanner request.
    """
    try:
        configured = json.loads(os.environ.get('SCANNER_KEYS_JSON', '{}'))
    except json.JSONDecodeError as exc:
        raise RuntimeError('Invalid SCANNER_KEYS_JSON') from exc
    if not isinstance(configured, dict):
        raise RuntimeError('SCANNER_KEYS_JSON must be a JSON object')
    expected = configured.get(scanner_id)
    if not isinstance(expected, str) or not expected or not hmac.compare_digest(
        expected.encode('utf-8'), scanner_key.encode('utf-8')
    ):
        raise HTTPException(status_code=401, detail='Invalid scanner credentials')
    doc = db.collection('scanners').document(scanner_id).get()
    data = doc.to_dict() if doc.exists else None
    if not data or data.get('enabled') is not True or not isinstance(data.get('roomId'), str):
        raise HTTPException(status_code=403, detail='Scanner not enabled or assigned')
    return data['roomId']


def _booking_active(db, uid: str, room_id: str, now: datetime) -> bool:
    # A user-room equality query avoids exposing booking data to the scanner.
    records = db.collection('bookings').where('userId', '==', uid).where('roomId', '==', room_id).stream()
    for doc in records:
        row = doc.to_dict() or {}
        start, end = row.get('startAt'), row.get('endAt')
        if row.get('status') != 'APPROVED' or not isinstance(start, datetime) or not isinstance(end, datetime):
            continue
        if start.tzinfo is None or end.tzinfo is None:
            continue
        if start <= now < end:
            return True
    return False


def abac_decision(db, uid: str, room_id: str, now: datetime):
    """Default deny. Any enabled policy matching role/time/booking grants access.

    Time convention: startHour inclusive, endHour exclusive in ACCESS_TIME_ZONE.
    Policy schema matches the user's access_policies collection.
    """
    user_doc = db.collection('users').document(uid).get()
    user = user_doc.to_dict() if user_doc.exists else None
    if not user or user.get('status') != 'APPROVED':
        return False, 'User not approved', None
    # Re-check Firebase Auth state at scan time; QR issuance alone is not sufficient.
    try:
        account = auth.get_user(uid)
        if account.disabled:
            return False, 'User account disabled', None
    except auth.UserNotFoundError:
        return False, 'User account not found', None

    room_doc = db.collection('rooms').document(room_id).get()
    room = room_doc.to_dict() if room_doc.exists else None
    if not room or room.get('enabled') is not True:
        return False, 'Room unavailable', None

    role = user.get('role')
    if not isinstance(role, str):
        return False, 'User role missing', None

    # The existing registration rules allow USER; policies must explicitly include USER
    # for such accounts. Never infer a privileged role from the mobile client.
    hour = now.astimezone(LOCAL_ZONE).hour
    policies = db.collection('access_policies').where('roomId', '==', room_id).stream()
    for doc in policies:
        policy = doc.to_dict() or {}
        if policy.get('enabled') is not True:
            continue
        roles = policy.get('allowedRoles', [])
        start, end = policy.get('startHour'), policy.get('endHour')
        if not isinstance(roles, list) or role not in roles:
            continue
        if type(start) is not int or type(end) is not int or not (0 <= start < end <= 24):
            continue
        if not (start <= hour < end):
            continue
        if policy.get('bookingRequired') is True and not _booking_active(db, uid, room_id, now):
            continue
        if policy.get('bookingRequired') is not True and policy.get('bookingRequired') is not False:
            continue
        return True, 'Policy matched', doc.id
    return False, 'No matching active access policy', None


def _record_audit(db, *, scanner_id: str, room_id: str, uid: str | None,
                  jti_hash: str | None, decision: str, reason: str, policy_id: str | None):
    """Server-side audit. Do not store raw QR or scanner secret."""
    db.collection('scanner_access_logs').document().set({
        'scannerId': scanner_id,
        'roomId': room_id,
        'userId': uid,
        'jtiHash': jti_hash,
        'decision': decision,
        'reason': reason,
        'policyId': policy_id,
        'createdAt': datetime.now(timezone.utc),
    })


@router.post('/verify')
def verify_scan(payload: ScanRequest, request: Request,
                x_scanner_id: str = Header(..., alias='X-Scanner-ID'),
                x_scanner_key: str = Header(..., alias='X-Scanner-Key')):
    db = request.app.state.db
    codec = request.app.state.codec
    # Database and credential errors fail closed; never return access granted on outage.
    room_id = _scanner_identity(x_scanner_id, x_scanner_key, db)
    uid = None
    jti_hash = None
    policy_id = None
    decision = 'DENIED'
    reason = 'Invalid QR credential'
    try:
        claims = codec.verify(payload.token)
        uid = claims['sub']
        jti_hash = hashlib.sha256(claims['jti'].encode('utf-8')).hexdigest()
        # Atomic create: exactly one verifier can consume a JTI across online scanners.
        # Keep documents until after exp and cleanup by Firestore TTL / scheduled job.
        try:
            db.collection('used_qr_jtis').document(jti_hash).create({
                'userId': uid,
                'scannerId': x_scanner_id,
                'roomId': room_id,
                'expiresAt': datetime.fromtimestamp(claims['exp'] + 120, tz=timezone.utc),
                'createdAt': datetime.now(timezone.utc),
            })
        except AlreadyExists:
            reason = 'QR credential already used'
        else:
            granted, reason, policy_id = abac_decision(db, uid, room_id, datetime.now(timezone.utc))
            decision = 'GRANTED' if granted else 'DENIED'
    except InvalidQR:
        reason = 'Invalid or expired QR credential'
    except GoogleAPICallError:
        log.exception('Firestore unavailable while verifying scan')
        raise HTTPException(status_code=503, detail='Verification temporarily unavailable')

    # Do not grant access if auditing cannot be persisted.
    try:
        _record_audit(db, scanner_id=x_scanner_id, room_id=room_id, uid=uid,
                      jti_hash=jti_hash, decision=decision, reason=reason, policy_id=policy_id)
    except Exception:
        log.exception('Unable to persist scanner audit record')
        raise HTTPException(status_code=503, detail='Audit service unavailable')

    return {'decision': decision, 'reason': reason, 'room_id': room_id,
            'policy_id': policy_id}
