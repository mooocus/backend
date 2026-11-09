import { initializeApp } from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js';
import {
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
} from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js';
import {
  getFirestore,
  doc,
  getDoc,
  collection,
  onSnapshot,
  writeBatch,
  serverTimestamp,
  Timestamp,
  getDocs,
} from 'https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore.js';
import { firebaseConfig } from './firebase-config.js';

// ------------------------------------------------------------
// Firebase services and local state
// ------------------------------------------------------------
const firebaseApp = initializeApp(firebaseConfig);
const auth = getAuth(firebaseApp);
const db = getFirestore(firebaseApp);
const $ = (id) => document.getElementById(id);

const emptyState = () => ({
  users: [],
  rooms: [],
  policies: [],
  bookings: [],
  audit: [],
});

let state = emptyState();
let unsubs = [];
let authRevision = 0;
let auditClearAllowed = false;
let auditClearBusy = false;


// ------------------------------------------------------------
// Shared UI helpers
// ------------------------------------------------------------
function flash(message, isError = false) {
  const element = $('message');
  element.textContent = message;
  element.className = isError ? 'error' : '';
  element.style.display = 'block';
  clearTimeout(element._timer);
  element._timer = setTimeout(() => {
    element.style.display = 'none';
  }, 5500);
}

function clean() {
  for (const unsubscribe of unsubs) unsubscribe();
  unsubs = [];
  state = emptyState();
  auditClearAllowed = false;
  $('clearAuditLogs').hidden = true;
}

function setOptions(select, items, textForItem) {
  const options = items.map((item) => {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = textForItem(item);
    return option;
  });
  select.replaceChildren(...options);
}

function textCell(row, value, className = '') {
  const cell = row.insertCell();
  cell.textContent = String(value ?? '');
  if (className) cell.className = className;
  return cell;
}

function formatTime(timestamp) {
  return timestamp?.toDate?.().toLocaleString() || '—';
}

function statusBadge(status) {
  const element = document.createElement('span');
  const allowed = ['APPROVED', 'PENDING', 'REJECTED', 'SUSPENDED'];
  const safeStatus = allowed.includes(status) ? status : 'UNKNOWN';
  element.className = `pill ${safeStatus}`;
  element.textContent = safeStatus;
  return element;
}

function button(label, callback, className = '') {
  const element = document.createElement('button');
  element.type = 'button';
  element.textContent = label;
  element.className = className;
  element.addEventListener('click', async () => {
    element.disabled = true;
    try {
      await callback();
    } catch (error) {
      flash(error.message, true);
    } finally {
      element.disabled = false;
    }
  });
  return element;
}

function descriptionItem(title, subtitle, actionButton) {
  const wrapper = document.createElement('div');
  wrapper.className = 'item';

  const info = document.createElement('div');
  info.textContent = title;
  const extra = document.createElement('small');
  extra.textContent = subtitle;
  info.append(extra);
  wrapper.append(info);

  if (actionButton) wrapper.append(actionButton);
  return wrapper;
}

// ------------------------------------------------------------
// Real-time Firestore listeners
// ------------------------------------------------------------
function listen(collectionName) {
  const stateKey = {
    access_policies: 'policies',
    audit_logs: 'audit',
  }[collectionName] ?? collectionName;

  const unsubscribe = onSnapshot(
    collection(db, collectionName),
    (snapshot) => {
      state[stateKey] = snapshot.docs.map((snapshotDoc) => ({
        ...snapshotDoc.data(),
        id: snapshotDoc.id,
      }));
      render();
    },
    (error) => flash(`${collectionName}: ${error.message}`, true),
  );

  unsubs.push(unsubscribe);
}

// ------------------------------------------------------------
// Pending registrations and All Users tables
// ------------------------------------------------------------
const ROLES = ['USER', 'STUDENT', 'RESEARCHER', 'STAFF'];

function userMatchesSearch(user, search) {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;

  return [user.name, user.email, user.campusId, user.id]
    .some((value) => String(value || '').toLowerCase().includes(needle));
}

function timestampMillis(value) {
  return value?.toMillis?.() ?? 0;
}

function emptyRow(body, columnCount, message) {
  const row = body.insertRow();
  const cell = row.insertCell();
  cell.colSpan = columnCount;
  cell.className = 'empty-table';
  cell.textContent = message;
}

function renderPending() {
  const body = $('pendingBody');
  body.replaceChildren();

  const search = $('pendingSearch').value;
  const pending = state.users
    .filter((user) => user.status === 'PENDING')
    .filter((user) => userMatchesSearch(user, search))
    .sort((a, b) => timestampMillis(b.createdAt) - timestampMillis(a.createdAt));

  $('pendingShown').textContent = `${pending.length} matching pending`;
  $('pendingNavCount').textContent = state.users.filter((u) => u.status === 'PENDING').length;

  if (!pending.length) {
    emptyRow(body, 6, 'No pending registrations match your search.');
    return;
  }

  for (const user of pending) {
    const row = body.insertRow();
    textCell(row, user.name || '—', 'user-name');
    textCell(row, user.email || '—', 'user-email');
    textCell(row, user.requestedRole || user.role || '—');
    textCell(row, user.campusId || '—');
    textCell(row, formatTime(user.createdAt));

    const actions = row.insertCell();
    actions.className = 'user-actions';
    actions.append(
      button('Approve', async () => {
        if (!confirm(`Approve ${user.name || user.email}?`)) return;
        await updateUser(user, { status: 'APPROVED' });
      }),
      button('Reject', async () => {
        if (!confirm(`Reject ${user.name || user.email}?`)) return;
        await updateUser(user, { status: 'REJECTED' });
      }, 'danger'),
    );
  }
}

function renderUsers() {
  const body = $('usersBody');
  body.replaceChildren();

  const search = $('userSearch').value;
  const status = $('statusFilter').value;
  const role = $('roleFilter').value;
  const sort = $('userSort').value;

  // Pending applicants are managed only in the Pending Registrations tab.
  const users = state.users.filter((user) =>
    user.status !== 'PENDING' &&
    userMatchesSearch(user, search) &&
    (status === 'ALL' || user.status === status) &&
    (role === 'ALL' || (user.role || 'USER') === role),
  );

  if (sort === 'newest') {
    users.sort((a, b) => timestampMillis(b.createdAt) - timestampMillis(a.createdAt));
  } else if (sort === 'oldest') {
    users.sort((a, b) => timestampMillis(a.createdAt) - timestampMillis(b.createdAt));
  } else {
    users.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  }

  const existingCount = state.users.filter((user) => user.status !== 'PENDING').length;
  $('usersShown').textContent = `Showing ${users.length} of ${existingCount} existing users`;

  if (!users.length) {
    emptyRow(body, 6, 'No existing users match these filters. Pending applications are on the Pending Registrations tab.');
    return;
  }

  for (const user of users) {
    const row = body.insertRow();
    textCell(row, user.name || '—', 'user-name');
    textCell(row, user.email || '—', 'user-email');

    const roleCell = row.insertCell();
    const roleSelect = document.createElement('select');
    roleSelect.setAttribute('aria-label', `Role for ${user.email || user.id}`);

    for (const availableRole of ROLES) {
      roleSelect.add(new Option(availableRole, availableRole));
    }

    roleSelect.value = user.role || 'USER';
    roleSelect.addEventListener('change', async () => {
      if (!confirm(`Change role for ${user.email || user.id}?`)) {
        roleSelect.value = user.role || 'USER';
        return;
      }
      roleSelect.disabled = true;
      try {
        await updateUser(user, { role: roleSelect.value });
      } catch (error) {
        roleSelect.value = user.role || 'USER';
        flash(error.message, true);
      } finally {
        roleSelect.disabled = false;
      }
    });
    roleCell.append(roleSelect);

    row.insertCell().append(statusBadge(user.status));
    textCell(row, formatTime(user.createdAt));

    const actions = row.insertCell();
    actions.className = 'user-actions';

    // Only reviewed users appear here; pending applications are in their own tab.
    if (user.status === 'APPROVED') {
      actions.append(button('Suspend', () => updateUser(user, { status: 'SUSPENDED' }), 'muted'));
      actions.append(button('Reject', () => updateUser(user, { status: 'REJECTED' }), 'danger'));
    } else if (user.status === 'REJECTED' || user.status === 'SUSPENDED') {
      actions.append(button('Approve', () => updateUser(user, { status: 'APPROVED' })));
    }

    // Intentionally NO Delete button. No Firestore/Auth records are removed.
  }
}

// ------------------------------------------------------------
// Render other sections
// ------------------------------------------------------------
function renderRooms() {
  const list = $('roomsList');
  list.replaceChildren();

  for (const room of state.rooms) {
    list.append(descriptionItem(
      room.name || room.id,
      room.description || room.id,
      button(room.enabled ? 'Disable' : 'Enable', () => editRoom(room, !room.enabled), 'muted'),
    ));
  }
}

function renderPolicies() {
  const list = $('policiesList');
  list.replaceChildren();

  for (const policy of state.policies) {
    const roomName = state.rooms.find((room) => room.id === policy.roomId)?.name || policy.roomId;
    const roles = Array.isArray(policy.allowedRoles) ? policy.allowedRoles.join(', ') : '—';

    list.append(descriptionItem(
      `${roomName} · ${roles}`,
      `${policy.startHour}:00–${policy.endHour}:00 · ${policy.bookingRequired ? 'Booking required' : 'No booking'} · ${policy.enabled ? 'Enabled' : 'Disabled'}`,
      button(policy.enabled ? 'Disable' : 'Enable', () => editPolicy(policy, !policy.enabled), 'muted'),
    ));
  }
}

function renderBookings() {
  const list = $('bookingsList');
  list.replaceChildren();

  for (const booking of state.bookings) {
    const userName = state.users.find((user) => user.id === booking.userId)?.name || booking.userId;
    const roomName = state.rooms.find((room) => room.id === booking.roomId)?.name || booking.roomId;

    list.append(descriptionItem(
      `${userName} · ${roomName}`,
      `${formatTime(booking.startAt)} → ${formatTime(booking.endAt)} · ${booking.status}`,
      booking.status === 'APPROVED'
        ? button('Cancel', () => cancelBooking(booking), 'danger')
        : null,
    ));
  }
}

// ------------------------------------------------------------
// Development-only audit clearing
// ------------------------------------------------------------
// This must only be enabled for a designated admin in Firestore:
// settings/auditMaintenance { enabled: true, allowedUid: "<admin UID>" }
// And corresponding Firestore Security Rules must authorize deletes.
// Otherwise no delete occurs. Use only with disposable test logs.
async function configureAuditMaintenance(user) {
  auditClearAllowed = false;
  $('clearAuditLogs').hidden = true;

  const settingsDoc = await getDoc(doc(db, 'settings', 'auditMaintenance'));
  const maintenance = settingsDoc.exists() ? settingsDoc.data() : null;

  auditClearAllowed = maintenance?.enabled === true
    && maintenance?.allowedUid === user.uid;
  $('clearAuditLogs').hidden = !auditClearAllowed;
}

function serializeAuditEvent(event) {
  const record = { ...event };
  if (record.createdAt?.toDate) {
    record.createdAt = record.createdAt.toDate().toISOString();
  }
  return record;
}

function downloadAuditBackup(events) {
  const backup = {
    exportedAt: new Date().toISOString(),
    firebaseProjectId: firebaseConfig.projectId,
    collection: 'audit_logs',
    events: events.map(serializeAuditEvent),
  };
  const blob = new Blob([JSON.stringify(backup, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `secure-qr-audit-backup-${Date.now()}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function clearTestAuditLogs() {
  if (auditClearBusy) return;
  const currentAdmin = auth.currentUser;
  if (!currentAdmin || !auditClearAllowed) {
    throw new Error('Audit clearing is not enabled for this administrator.');
  }

  // Fetch the entire collection, not the 200 currently shown in the table.
  const snapshot = await getDocs(collection(db, 'audit_logs'));
  const count = snapshot.size;
  if (count === 0) {
    flash('There are no audit logs to clear.');
    return;
  }

  const confirmation = prompt(
    `Delete ${count} TEST audit events permanently?\n` +
    'Download the JSON backup when prompted.\n' +
    'This operation is irreversible and must never be used on production logs.\n\n' +
    'Type CLEAR LOGS to proceed:',
  );
  if (confirmation !== 'CLEAR LOGS') return;

  auditClearBusy = true;
  const control = $('clearAuditLogs');
  control.disabled = true;
  try {
    downloadAuditBackup(snapshot.docs.map((entry) => ({
      id: entry.id,
      ...entry.data(),
    })));

    // Firestore batch limits: keep well below 500 writes per commit.
    // A failure stops processing and reports partial completion.
    let completed = 0;
    const batchSize = 100;
    for (let offset = 0; offset < snapshot.docs.length; offset += batchSize) {
      if (auth.currentUser?.uid !== currentAdmin.uid) {
        throw new Error('Administrator session changed. Stopped.');
      }
      const batch = writeBatch(db);
      for (const entry of snapshot.docs.slice(offset, offset + batchSize)) {
        batch.delete(entry.ref);
      }
      await batch.commit();
      completed += Math.min(batchSize, snapshot.docs.length - offset);
    }
    flash(`${completed} test audit events removed. Disable maintenance mode in Firestore now.`);
  } catch (error) {
    throw new Error(`Clear stopped; some logs may already have been deleted. ${error.message}`);
  } finally {
    auditClearBusy = false;
    control.disabled = false;
  }
}

$('clearAuditLogs').addEventListener('click', async () => {
  try {
    await clearTestAuditLogs();
  } catch (error) {
    flash(error.message, true);
  }
});

// Present human-readable audit information without changing stored Firestore IDs.
// Older events may not have a name snapshot; use current records when available.
function auditUserName(uid) {
  const user = state.users.find((entry) => entry.id === uid);
  return user?.name || user?.email || 'User record unavailable';
}

function auditRoomName(roomId) {
  const room = state.rooms.find((entry) => entry.id === roomId);
  return room?.name || null;
}

function auditPolicyRoom(event) {
  const policy = state.policies.find((entry) => entry.id === event.targetUid);
  const roomId = policy?.roomId || event.details;
  return auditRoomName(roomId);
}

function auditBookingInfo(event) {
  const booking = state.bookings.find((entry) => entry.id === event.targetUid);
  if (!booking) return null;
  const room = auditRoomName(booking.roomId) || 'Unknown room';
  const user = auditUserName(booking.userId);
  return `${room} · ${user}`;
}

const AUDIT_ACTIONS = {
  USER_DECISION: 'User account',
  ROOM_CHANGE: 'Room',
  POLICY_CHANGE: 'Access policy',
  BOOKING_CHANGE: 'Booking',
};

const AUDIT_OUTCOMES = {
  CREATED: 'Created',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  SUSPENDED: 'Suspended',
  ENABLED: 'Enabled',
  DISABLED: 'Disabled',
  CANCELLED: 'Cancelled',
  DELETED: 'Deleted',
  ROLE_CHANGED: 'Role updated',
};

function auditActivity(event) {
  const label = AUDIT_ACTIONS[event.type] || 'Administrative event';
  const outcome = AUDIT_OUTCOMES[event.outcome] || event.outcome || 'Updated';
  return `${label} · ${outcome.toLowerCase()}`;
}

function auditTarget(event) {
  switch (event.type) {
    case 'USER_DECISION':
      return auditUserName(event.targetUid);
    case 'ROOM_CHANGE':
      return auditRoomName(event.targetUid) ||
        (event.details && !event.details.startsWith('{') ? event.details : null) ||
        'Room record unavailable';
    case 'POLICY_CHANGE':
      return auditPolicyRoom(event) || 'Policy room unavailable';
    case 'BOOKING_CHANGE':
      return auditBookingInfo(event) || auditRoomName(event.details) || 'Booking record unavailable';
    default:
      return 'Administrative record';
  }
}

function auditDetails(event) {
  if (event.type === 'USER_DECISION') {
    let changes;
    try { changes = JSON.parse(event.details || '{}'); } catch { changes = null; }
    if (changes && typeof changes === 'object') {
      const parts = [];
      if (changes.status) parts.push(`Account status: ${changes.status.toLowerCase()}`);
      if (changes.role) parts.push(`Role: ${changes.role}`);
      return parts.join(' · ') || 'User account updated';
    }
    return 'User account updated';
  }
  if (event.type === 'ROOM_CHANGE') {
    return event.outcome === 'CREATED' ? 'New room registered' :
      event.outcome === 'ENABLED' ? 'Room available for access' :
      event.outcome === 'DISABLED' ? 'Room disabled for access' : 'Room settings changed';
  }
  if (event.type === 'POLICY_CHANGE') {
    const policy = state.policies.find((entry) => entry.id === event.targetUid);
    if (policy) {
      const roles = Array.isArray(policy.allowedRoles) ? policy.allowedRoles.join(', ') : 'Unspecified';
      return `Roles: ${roles} · ${policy.startHour}:00–${policy.endHour}:00 · ${policy.bookingRequired ? 'Booking required' : 'No booking required'}`;
    }
    return event.outcome === 'CREATED' ? 'Room access policy created' :
      event.outcome === 'ENABLED' ? 'Room access policy enabled' :
      event.outcome === 'DISABLED' ? 'Room access policy disabled' : 'Room access policy updated';
  }
  if (event.type === 'BOOKING_CHANGE') {
    const booking = state.bookings.find((entry) => entry.id === event.targetUid);
    return booking ? `${formatTime(booking.startAt)} to ${formatTime(booking.endAt)}` :
      event.outcome === 'CANCELLED' ? 'Booking cancelled' : 'Approved booking created';
  }
  return 'Administrative change recorded';
}

function auditActor(event) {
  if (event.actorUid && event.actorUid === auth.currentUser?.uid) {
    return auth.currentUser?.email || 'You (administrator)';
  }
  return 'Administrator';
}

function renderAudit() {
  const body = $('auditBody');
  body.replaceChildren();

  const latest = [...state.audit]
    .sort((a, b) => (b.createdAt?.seconds || 0) - (a.createdAt?.seconds || 0))
    .slice(0, 200);

  if (!latest.length) {
    emptyRow(body, 5, 'No administrative audit events recorded yet.');
    return;
  }

  for (const event of latest) {
    const row = body.insertRow();
    textCell(row, formatTime(event.createdAt));
    textCell(row, auditActivity(event));
    textCell(row, auditTarget(event));
    textCell(row, auditDetails(event));
    textCell(row, auditActor(event));
  }
}

function render() {
  $('total').textContent = state.users.length;
  $('pending').textContent = state.users.filter((user) => user.status === 'PENDING').length;
  $('approved').textContent = state.users.filter((user) => user.status === 'APPROVED').length;
  $('events').textContent = state.audit.length;

  renderPending();
  renderUsers();
  renderRooms();
  renderPolicies();
  renderBookings();
  renderAudit();

  const enabledRooms = state.rooms.filter((room) => room.enabled);
  setOptions($('policyRoom'), enabledRooms, (room) => room.name);
  setOptions($('bookingRoom'), enabledRooms, (room) => room.name);
  setOptions(
    $('bookingUser'),
    state.users.filter((user) => user.status === 'APPROVED'),
    (user) => `${user.name || user.email} (${user.email || user.id})`,
  );
}

// ------------------------------------------------------------
// Audited Firestore updates
// ------------------------------------------------------------
function audit(batch, type, targetUid, outcome, details) {
  const auditRef = doc(collection(db, 'audit_logs'));
  batch.set(auditRef, {
    type,
    actorUid: auth.currentUser.uid,
    targetUid,
    outcome,
    details,
    createdAt: serverTimestamp(),
  });
}

async function updateUser(user, changes) {
  const batch = writeBatch(db);
  const updates = { ...changes };

  // Approval metadata should only change for approval decisions,
  // not when an administrator edits a user's role.
  if (changes.status) {
    updates.approvedAt = serverTimestamp();
    updates.approvedBy = auth.currentUser.uid;
  }

  batch.update(doc(db, 'users', user.id), updates);
  audit(batch, 'USER_DECISION', user.id, changes.status || 'ROLE_CHANGED', JSON.stringify(changes));
  await batch.commit();
  flash('User updated successfully');
}

async function editRoom(room, enabled) {
  const batch = writeBatch(db);
  batch.update(doc(db, 'rooms', room.id), { enabled });
  audit(batch, 'ROOM_CHANGE', room.id, enabled ? 'ENABLED' : 'DISABLED', room.name);
  await batch.commit();
}

async function editPolicy(policy, enabled) {
  const batch = writeBatch(db);
  batch.update(doc(db, 'access_policies', policy.id), { enabled });
  audit(batch, 'POLICY_CHANGE', policy.id, enabled ? 'ENABLED' : 'DISABLED', policy.roomId);
  await batch.commit();
}

async function cancelBooking(booking) {
  const batch = writeBatch(db);
  batch.update(doc(db, 'bookings', booking.id), { status: 'CANCELLED' });
  audit(batch, 'BOOKING_CHANGE', booking.id, 'CANCELLED', booking.roomId);
  await batch.commit();
}

// ------------------------------------------------------------
// Forms: rooms, policies and bookings
// ------------------------------------------------------------
$('roomForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const name = $('roomName').value.trim();
    const description = $('roomDesc').value.trim();
    if (!name) throw new Error('Room name required');

    const batch = writeBatch(db);
    const ref = doc(collection(db, 'rooms'));
    batch.set(ref, { name, description, enabled: true });
    audit(batch, 'ROOM_CHANGE', ref.id, 'CREATED', name);
    await batch.commit();
    event.target.reset();
    flash('Room created');
  } catch (error) {
    flash(error.message, true);
  }
});

$('policyForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const roomId = $('policyRoom').value;
    const allowedRoles = [...$('policyRoles').selectedOptions].map((option) => option.value);
    const startHour = Number($('startHour').value);
    const endHour = Number($('endHour').value);

    if (!roomId || !allowedRoles.length || startHour < 0 || endHour > 24 || endHour <= startHour) {
      throw new Error('Check policy values');
    }

    const batch = writeBatch(db);
    const ref = doc(collection(db, 'access_policies'));
    batch.set(ref, {
      roomId,
      allowedRoles,
      startHour,
      endHour,
      bookingRequired: $('bookingRequired').checked,
      enabled: true,
    });
    audit(batch, 'POLICY_CHANGE', ref.id, 'CREATED', roomId);
    await batch.commit();
    flash('Policy created');
  } catch (error) {
    flash(error.message, true);
  }
});

$('bookingForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const userId = $('bookingUser').value;
    const roomId = $('bookingRoom').value;
    const startAt = Timestamp.fromDate(new Date($('bookingStart').value));
    const endAt = Timestamp.fromDate(new Date($('bookingEnd').value));

    if (!userId || !roomId || endAt.toMillis() <= startAt.toMillis()) {
      throw new Error('Invalid booking');
    }

    const batch = writeBatch(db);
    const ref = doc(collection(db, 'bookings'));
    batch.set(ref, { userId, roomId, startAt, endAt, status: 'APPROVED' });
    audit(batch, 'BOOKING_CHANGE', ref.id, 'CREATED', roomId);
    await batch.commit();
    flash('Booking created');
  } catch (error) {
    flash(error.message, true);
  }
});

// ------------------------------------------------------------
// Authentication and navigation
// ------------------------------------------------------------
$('loginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await signInWithEmailAndPassword(auth, $('email').value, $('password').value);
  } catch (error) {
    flash(error.message, true);
  }
});

$('logout').addEventListener('click', () => signOut(auth));

function switchTab(activeTab) {
  if (activeTab === 'users') {
    // Open All Users unfiltered every time the tab is selected.
    $('userSearch').value = '';
    $('statusFilter').value = 'ALL';
    $('roleFilter').value = 'ALL';
    $('userSort').value = 'newest';
    renderUsers();
  }
  for (const tab of ['pending', 'users', 'rooms', 'policies', 'bookings', 'audit']) {
    $(`${tab}Tab`).hidden = tab !== activeTab;
  }
  document.querySelectorAll('[data-tab]').forEach((button) => {
    const active = button.dataset.tab === activeTab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
}

document.querySelectorAll('[data-tab]').forEach((button) => {
  button.addEventListener('click', () => switchTab(button.dataset.tab));
});

for (const id of ['pendingSearch', 'userSearch']) {
  $(id).addEventListener('input', () => {
    renderPending();
    renderUsers();
  });
}
for (const id of ['statusFilter', 'roleFilter', 'userSort']) {
  $(id).addEventListener('change', renderUsers);
}
$('clearFilters').addEventListener('click', () => {
  $('userSearch').value = '';
  $('statusFilter').value = 'ALL';
  $('roleFilter').value = 'ALL';
  $('userSort').value = 'newest';
  renderUsers();
});

onAuthStateChanged(auth, async (user) => {
  const revision = ++authRevision;
  clean();

  if (!user) {
    $('loginView').hidden = false;
    $('appView').hidden = true;
    $('logout').hidden = true;
    return;
  }

  try {
    const adminMarker = await getDoc(doc(db, 'admins', user.uid));
    if (revision !== authRevision) return;

    if (!adminMarker.exists() || adminMarker.data()?.role !== 'ADMIN') {
      flash('This account is not an administrator.', true);
      await signOut(auth);
      return;
    }

    $('loginView').hidden = true;
    $('appView').hidden = false;
    $('logout').hidden = false;
    switchTab('pending');

    // Inactive by default; the button remains hidden if settings are absent.
    try {
      await configureAuditMaintenance(user);
    } catch (error) {
      console.warn('Audit maintenance unavailable:', error);
    }

    for (const name of ['users', 'rooms', 'access_policies', 'bookings', 'audit_logs']) {
      listen(name);
    }
  } catch (error) {
    flash(error.message, true);
    await signOut(auth);
  }
});
