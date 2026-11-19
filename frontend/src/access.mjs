// Browser access roles. Mirrors capstone/api/access.py: one token per role,
// each sent only to the action that needs it.

export const ROLES = [
  { role: 'viewer', variable: 'CAPSTONE_UI_TOKEN', purpose: 'Read pages' },
  { role: 'operator', variable: 'CAPSTONE_UI_RUN_TOKEN', purpose: 'Start simulator runs' },
  { role: 'reviewer', variable: 'CAPSTONE_UI_REVIEW_TOKEN', purpose: 'Approve or reject proposed actions' },
  { role: 'evaluator', variable: 'CAPSTONE_UI_EVALUATOR_TOKEN', purpose: 'Evaluation records and scorecards' },
];
export const RUNS_VARIABLE = 'CAPSTONE_UI_SIM_RUNS';

export function emptyTokens() {
  return { viewer: '', operator: '', reviewer: '', evaluator: '' };
}

// Any role's token can read, so reads use the first one entered.
export function readToken(tokens) {
  return tokens.viewer || tokens.operator || tokens.reviewer || tokens.evaluator || '';
}

// Actions send their own role's token; an empty slot falls back to the read
// token so the server answers with a message naming the token it needs.
export function tokenFor(tokens, role) {
  return tokens[role] || readToken(tokens);
}

export function countTokens(tokens) {
  return ROLES.filter(item => tokens[item.role]).length;
}

function base64Url(bytes) {
  let text = '';
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

// Four distinct 43-character tokens made in the browser; nothing is sent anywhere.
export function generateTokens(fillRandom = bytes => crypto.getRandomValues(bytes)) {
  let tokens = emptyTokens();
  while (new Set(Object.values(tokens)).size < ROLES.length || !tokens.viewer) {
    tokens = Object.fromEntries(ROLES.map(item => [item.role, base64Url(fillRandom(new Uint8Array(32)))]));
  }
  return tokens;
}

export function envBlock(tokens) {
  return ROLES.map(item => item.variable + '=' + tokens[item.role]).join('\n') +
    '\n' + RUNS_VARIABLE + '=1\n';
}

// The server's fixed 403 details (capstone/api/app.py ROLE_DENIED). Only these
// exact strings are shown to the user; any other detail stays hidden.
export const ROLE_DENIED_MESSAGES = [
  'Starting a run needs the operator token (CAPSTONE_UI_RUN_TOKEN)',
  'Review decisions need the reviewer token (CAPSTONE_UI_REVIEW_TOKEN)',
  'Evaluation records need the evaluator token (CAPSTONE_UI_EVALUATOR_TOKEN)',
];

// What the dialog says about one slot after asking the server who it is.
export function describeCheck(role, roles) {
  if (!roles) return { ok: false, text: 'Not checked' };
  if (roles.includes(role)) return { ok: true, text: 'Recognised as ' + role };
  if (roles.length) return { ok: false, text: 'This is the ' + roles.join(', ') + ' token, not ' + role };
  return { ok: false, text: 'Not recognised by this backend' };
}
