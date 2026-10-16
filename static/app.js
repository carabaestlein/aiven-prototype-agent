const $ = id => document.getElementById(id);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const statusLabels = {
  awaiting_review: 'Ready for review',
  completed: 'Completed',
  needs_continue: 'Ready to continue',
};
let csrf = '', current = null, authenticated = false, busy = false;
let routeVersion = 0, sessionVersion = 0, historyVersion = 0;
let historyLoading = false, runs = [], operationMessage = '';
const feedbackDrafts = new Map();

function notice(message = '', link = null) {
  const target = $('notice');
  target.replaceChildren(document.createTextNode(message));
  if (link) {
    const action = document.createElement(link.href ? 'a' : 'button');
    action.className = 'notice-action';
    action.textContent = link.label;
    if (link.href) action.href = link.href;
    else { action.type = 'button'; action.onclick = link.action; }
    target.append(document.createTextNode(' '), action);
  }
  target.hidden = !message;
}

async function api(path, options = {}) {
  const version = sessionVersion;
  const response = await fetch(path, {
    credentials: 'same-origin', ...options,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...(options.headers || {}) },
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error('The service could not respond. Please try again.'); }
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login' && version === sessionVersion) showLogin();
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Please check the form and try again.');
    error.status = response.status;
    throw error;
  }
  return data;
}

function syncControls() {
  document.querySelectorAll('#workspace button, #logout').forEach(button => { button.disabled = busy; });
  $('refresh').disabled = busy || historyLoading;
  $('copy-draft').disabled = busy || !current?.draft;
  $('workspace').setAttribute('aria-busy', String(busy));
}

function showLogin() {
  authenticated = false;
  csrf = '';
  current = null;
  runs = [];
  feedbackDrafts.clear();
  sessionVersion += 1;
  routeVersion += 1;
  historyVersion += 1;
  historyLoading = false;
  $('workspace').hidden = true;
  $('workspace-nav').hidden = true;
  $('logout').hidden = true;
  $('login-view').hidden = false;
  $('run-list').replaceChildren();
  $('draft').textContent = '';
  $('run-title').textContent = '';
  $('detail-request').textContent = '';
  $('request').value = '';
  $('feedback').value = '';
  $('run-search').value = '';
  notice();
  updateRequestCount();
}

async function enter() {
  const session = await api('/api/session');
  csrf = session.csrf;
  authenticated = true;
  sessionVersion += 1;
  $('login-view').hidden = true;
  $('workspace').hidden = false;
  $('workspace-nav').hidden = false;
  $('logout').hidden = false;
  $('mode').textContent = session.mode === 'mock' ? 'Demo mode' : session.model;
  if (!location.hash) history.replaceState(null, '', '#/new');
  await showRoute();
}

function route() {
  const hash = location.hash || '#/new';
  if (hash === '#/new') return { page: 'new', hash };
  if (hash === '#/runs') return { page: 'history', hash };
  const match = /^#\/runs\/([^/]+)$/.exec(hash);
  if (match && UUID.test(match[1])) return { page: 'detail', id: match[1].toLowerCase(), hash };
  return { page: 'invalid', hash };
}

function focusHeading(page, version) {
  queueMicrotask(() => {
    if (version === routeVersion && authenticated) {
      $(page === 'new' ? 'new-heading' : page === 'history' ? 'history-heading' : 'detail-heading').focus({ preventScroll: true });
    }
  });
}

function showPage(page) {
  $('create-view').hidden = page !== 'new';
  $('history-view').hidden = page !== 'history';
  $('detail-view').hidden = page !== 'detail';
  for (const [id, active] of [['nav-new', page === 'new'], ['nav-runs', page !== 'new']]) {
    $(id).classList.toggle('active', active);
    if (active) $(id).setAttribute('aria-current', 'page');
    else $(id).removeAttribute('aria-current');
  }
}

function saveFeedback() {
  if (current) feedbackDrafts.set(current.id, $('feedback').value);
}

async function showRoute() {
  if (!authenticated) return;
  saveFeedback();
  current = null;
  const version = ++routeVersion;
  const selected = route();
  notice(busy ? operationMessage : '');
  if (selected.page === 'invalid') {
    history.replaceState(null, '', '#/new');
    showPage('new');
    notice('That run link is not valid. Start a new run or open your past runs.');
    focusHeading('new', version);
    syncControls();
    return;
  }
  showPage(selected.page);
  syncControls();
  focusHeading(selected.page, version);
  if (selected.page === 'new') return;
  if (selected.page === 'history') {
    renderHistory();
    await refreshHistory(version);
    return;
  }
  $('detail-heading').textContent = 'Your run';
  $('run-title').textContent = 'Loading run…';
  $('run-date').textContent = '';
  $('detail-request').textContent = '';
  $('draft').textContent = '';
  $('status').textContent = '';
  $('revision').textContent = '';
  for (const id of ['review-area', 'continue-area', 'complete-area']) $(id).hidden = true;
  $('detail-view').setAttribute('aria-busy', 'true');
  try {
    const run = await api(`/api/runs/${selected.id}`);
    if (version === routeVersion && authenticated) renderRun(run);
  } catch (error) {
    if (version === routeVersion && authenticated) {
      $('run-title').textContent = error.status === 404 ? 'Run not found' : 'Could not open this run';
      notice(error.message, { label: 'Try again', action: () => showRoute() });
    }
  } finally {
    if (version === routeVersion) {
      $('detail-view').setAttribute('aria-busy', 'false');
      syncControls();
    }
  }
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function renderHistory() {
  const search = $('run-search').value.trim().toLocaleLowerCase();
  const visible = runs.filter(run => run.request.toLocaleLowerCase().includes(search));
  $('run-list').replaceChildren();
  for (const run of visible) {
    if (!UUID.test(run.id)) continue;
    const row = document.createElement('a');
    row.className = 'run-row';
    row.href = `#/runs/${run.id}`;
    const summary = document.createElement('span');
    summary.className = 'run-summary';
    const name = document.createElement('span');
    name.className = 'run-name';
    name.textContent = run.request;
    summary.append(name);
    const date = document.createElement('time');
    date.className = 'run-date';
    date.dateTime = run.created_at;
    date.textContent = formatDate(run.created_at);
    const arrow = document.createElement('span');
    arrow.className = 'run-arrow';
    arrow.setAttribute('aria-hidden', 'true');
    arrow.textContent = '↗';
    row.append(summary, date, arrow);
    $('run-list').append(row);
  }
  $('run-count').textContent = search ? `${visible.length} of ${runs.length} runs` : `${runs.length} ${runs.length === 1 ? 'run' : 'runs'}`;
  $('history-empty').hidden = visible.length > 0;
  $('history-empty').textContent = historyLoading && !runs.length ? 'Loading your runs…' : search
    ? 'No runs match your search. Try a different word.'
    : 'No runs yet. Start a new run and it will appear here.';
}

async function refreshHistory(version = routeVersion) {
  const requestVersion = ++historyVersion;
  historyLoading = true;
  syncControls();
  renderHistory();
  try {
    const result = await api('/api/runs');
    if (requestVersion !== historyVersion || !authenticated) return;
    runs = result;
    if (version === routeVersion && route().page === 'history') renderHistory();
  } catch (error) {
    if (version === routeVersion && authenticated) {
      notice(error.message, { label: 'Try again', action: () => refreshHistory() });
    }
  } finally {
    if (requestVersion === historyVersion) {
      historyLoading = false;
      if (route().page === 'history') renderHistory();
      syncControls();
    }
  }
}

function renderRun(run) {
  const previousFocus = document.activeElement;
  current = run;
  $('detail-view').setAttribute('aria-busy', 'false');
  $('detail-heading').textContent = run.status === 'completed' ? 'Completed run'
    : run.status === 'awaiting_review' ? 'Review your draft' : 'Continue your run';
  $('run-title').textContent = run.status === 'completed' ? 'Approved draft' : 'Your draft';
  $('detail-request').textContent = run.request;
  $('run-date').textContent = `Started ${formatDate(run.created_at)}`;
  $('status').textContent = statusLabels[run.status] || 'Saved';
  $('status').className = `status status-${run.status}`;
  $('revision').textContent = run.revision ? `Version ${run.revision}` : '';
  $('draft').textContent = run.draft || 'No draft has been saved yet. Continue the run to pick up from its last saved step.';
  $('review-area').hidden = run.status !== 'awaiting_review';
  $('continue-area').hidden = run.status !== 'needs_continue';
  $('complete-area').hidden = run.status !== 'completed';
  $('feedback').value = feedbackDrafts.get(run.id) || '';
  const stage = run.status === 'completed' ? 3 : run.status === 'awaiting_review' ? 2 : 1;
  ['step-request', 'step-draft', 'step-review', 'step-complete'].forEach((id, index) => {
    $(id).classList.toggle('active', index === stage);
    $(id).classList.toggle('done', index < stage);
    if (index === stage) $(id).setAttribute('aria-current', 'step');
    else $(id).removeAttribute('aria-current');
  });
  if (run.error) notice(run.error);
  syncControls();
  if (previousFocus?.closest('[hidden]')) focusHeading('detail', routeVersion);
}

function rememberRun(run) {
  const index = runs.findIndex(item => item.id === run.id);
  if (index === -1) runs.unshift(run);
  else runs[index] = run;
  runs = runs.slice(0, 50);
  if (route().page === 'history') renderHistory();
}

async function mutation(progress, perform, { feedbackId = null, submittedFeedback = null, submittedRequest = null } = {}) {
  if (busy || !authenticated) return;
  saveFeedback();
  const version = sessionVersion;
  const sourceRoute = routeVersion;
  const sourceId = current?.id;
  busy = true;
  operationMessage = progress;
  syncControls();
  notice(progress);
  try {
    const run = await perform();
    if (version !== sessionVersion || !authenticated) return;
    if (feedbackId && feedbackDrafts.get(feedbackId) === submittedFeedback) feedbackDrafts.delete(feedbackId);
    if (submittedRequest !== null && $('request').value === submittedRequest) {
      $('request').value = '';
      updateRequestCount();
    }
    rememberRun(run);
    const selected = route();
    if (selected.page === 'detail' && selected.id === run.id) {
      routeVersion += 1;
      $('detail-view').setAttribute('aria-busy', 'false');
      renderRun(run);
      notice(run.error || '');
    } else if (sourceRoute === routeVersion) {
      // The response already contains the saved state; changing the URL does not need another read.
      history.pushState(null, '', `#/runs/${run.id}`);
      routeVersion += 1;
      showPage('detail');
      renderRun(run);
      notice(run.error || '');
      focusHeading('detail', routeVersion);
    } else {
      notice(run.error || (run.status === 'completed' ? 'Your draft has been approved.' : 'Your run is saved and ready to open.'), {
        label: 'Open run', href: `#/runs/${run.id}`,
      });
    }
  } catch (error) {
    if (version !== sessionVersion || !authenticated) return;
    const selected = route();
    if (error.status === 409 && sourceId) {
      notice(`${error.message} Your feedback is still here.`, selected.page === 'detail' && selected.id === sourceId
        ? { label: 'Refresh run', action: () => showRoute() }
        : { label: 'Open run', href: `#/runs/${sourceId}` });
    } else {
      notice(error.message);
    }
  } finally {
    busy = false;
    operationMessage = '';
    syncControls();
  }
}

function updateRequestCount() {
  $('request-count').textContent = `${$('request').value.length.toLocaleString()} / 4,000`;
}

$('login-form').onsubmit = async event => {
  event.preventDefault();
  $('login-error').textContent = '';
  const button = event.submitter || $('login-form').querySelector('button');
  button.disabled = true;
  try {
    await api('/api/login', { method: 'POST', body: JSON.stringify({ password: $('password').value }) });
    $('password').value = '';
    await enter();
  } catch (error) { $('login-error').textContent = error.message; }
  finally { button.disabled = false; }
};
$('logout').onclick = async () => {
  if (busy) return;
  $('logout').disabled = true;
  try {
    await api('/api/logout', { method: 'POST' });
    showLogin();
    history.replaceState(null, '', '#/new');
    $('password').focus();
  } catch (error) { notice(error.message); }
  finally { syncControls(); }
};
$('refresh').onclick = () => refreshHistory();
$('run-search').oninput = renderHistory;
$('request').oninput = updateRequestCount;
$('feedback').oninput = saveFeedback;
document.querySelectorAll('[data-prompt]').forEach(button => {
  button.onclick = () => {
    $('request').value = button.dataset.prompt;
    updateRequestCount();
    $('request').focus();
  };
});
$('create-form').onsubmit = event => {
  event.preventDefault();
  const request = $('request').value;
  if (!request.trim()) { notice('Add a request to start your run.'); $('request').focus(); return; }
  mutation('Creating your draft. You can browse past runs while it works…', () => api('/api/runs', {
    method: 'POST', body: JSON.stringify({ request }),
  }), { submittedRequest: request });
};
function review(action) {
  if (!current) return;
  const run = current;
  const feedback = $('feedback').value;
  if (action === 'revise' && !feedback.trim()) {
    notice('Add feedback before requesting a revision.'); $('feedback').focus(); return;
  }
  mutation(action === 'approve' ? 'Approving and saving your draft…' : 'Revising your draft. Your feedback is being applied…',
    () => api(`/api/runs/${run.id}/review`, {
      method: 'POST', body: JSON.stringify({ action, feedback, checkpoint: run.checkpoint }),
    }), { feedbackId: run.id, submittedFeedback: feedback });
}
$('review-form').onsubmit = event => { event.preventDefault(); review('revise'); };
$('approve').onclick = () => review('approve');
$('continue').onclick = () => {
  if (!current) return;
  const id = current.id;
  mutation('Continuing from the last saved step…', () => api(`/api/runs/${id}/continue`, { method: 'POST' }));
};
$('copy-draft').onclick = async () => {
  if (!current?.draft) return;
  try {
    await navigator.clipboard.writeText(current.draft);
    notice('Draft copied to clipboard.');
  } catch { notice('Copy is unavailable in this browser. You can select and copy the draft text.'); }
};
document.querySelector('.skip-link').onclick = event => {
  event.preventDefault();
  $('main').setAttribute('tabindex', '-1');
  $('main').focus();
};
window.addEventListener('hashchange', () => { showRoute(); });
updateRequestCount();
enter().catch(error => {
  showLogin();
  if (error.status !== 401) $('login-error').textContent = error.message;
}).finally(() => { $('loading').hidden = true; });
