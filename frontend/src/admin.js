import { apiKeysService } from './services/api_keys.js';

const state = {
  backendUrl: 'http://127.0.0.1:8000',
  adminCredential: null,
  models: [],
  rules: []
};

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('admin-login-form').addEventListener('submit', authenticate);
  document.getElementById('btn-logout').addEventListener('click', logout);
  document.getElementById('btn-refresh').addEventListener('click', refreshCatalogs);
  document.getElementById('btn-add-model').addEventListener('click', addModel);
  document.getElementById('btn-add-rule').addEventListener('click', addRule);
  document.getElementById('btn-add-key').addEventListener('click', addLocalKey);
  renderKeysList();
});

async function authenticate(event) {
  event.preventDefault();
  const secretInput = document.getElementById('admin-secret');
  const error = document.getElementById('login-error');
  const credential = secretInput.value;

  error.style.display = 'none';
  try {
    const response = await fetch(`${state.backendUrl}/admin/models`, {
      headers: { Authorization: `Bearer ${credential}` }
    });

    if (!response.ok) {
      throw new Error('Invalid administrator credential.');
    }

    // Deliberately module-memory only. Never persist this value.
    state.adminCredential = credential;
    secretInput.value = '';
    document.getElementById('admin-auth').style.display = 'none';
    document.getElementById('admin-app').style.display = 'block';
    await refreshCatalogs();
  } catch (err) {
    error.textContent = err.message || 'Authentication failed.';
    error.style.display = 'flex';
  }
}

function logout() {
  state.adminCredential = null;
  state.models = [];
  state.rules = [];
  document.getElementById('admin-app').style.display = 'none';
  document.getElementById('admin-auth').style.display = 'grid';
  document.getElementById('admin-secret').value = '';
}

function adminHeaders(json = false) {
  if (!state.adminCredential) throw new Error('Administrator authentication required.');
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    Authorization: `Bearer ${state.adminCredential}`
  };
}

async function adminFetch(path, options = {}) {
  const headers = { ...adminHeaders(Boolean(options.body)), ...(options.headers || {}) };
  const response = await fetch(`${state.backendUrl}${path}`, { ...options, headers });

  if (response.status === 401) {
    logout();
    throw new Error('Administrator credential expired or was rejected.');
  }

  if (!response.ok) {
    let detail = 'Administrator request failed.';
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response;
}

async function refreshCatalogs() {
  try {
    const [modelsRes, rulesRes] = await Promise.all([
      adminFetch('/admin/models'),
      adminFetch('/admin/optimizer-rules')
    ]);
    state.models = await modelsRes.json();
    state.rules = await rulesRes.json();
    renderModels();
    renderRules();
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function addModel() {
  const modelId = value('admin-model-id');
  const displayName = value('admin-model-name');
  if (!modelId || !displayName) return showNotification('Model ID and display name are required.', 'error');

  const input = number('admin-model-in');
  const output = number('admin-model-out');
  const cached = number('admin-model-cached');

  try {
    await adminFetch('/admin/models', {
      method: 'POST',
      body: JSON.stringify({
        provider: value('admin-model-provider'),
        model_id: modelId,
        display_name: displayName,
        pricing: {
          input_per_1m: input,
          output_per_1m: output,
          cached_input_per_1m: cached,
          batch_input_per_1m: input / 2,
          batch_output_per_1m: output / 2
        },
        context_window: 128000,
        capabilities: ['text'],
        active: true
      })
    });
    showNotification('Model added to catalog.', 'success');
    await refreshCatalogs();
  } catch (err) { showNotification(err.message, 'error'); }
}

async function updatePricing(provider, modelId, button) {
  const row = button.closest('tr');
  const inputs = row.querySelectorAll('.pricing-input');
  const pricing = {
    input_per_1m: Number(inputs[0].value),
    output_per_1m: Number(inputs[1].value),
    cached_input_per_1m: Number(inputs[2].value),
    batch_input_per_1m: Number(inputs[0].value) / 2,
    batch_output_per_1m: Number(inputs[1].value) / 2
  };

  try {
    // Provider is included as a query parameter so the admin operation cannot
    // accidentally target a different provider when model IDs collide.
    await adminFetch(`/admin/models/${encodeURIComponent(modelId)}?provider=${encodeURIComponent(provider)}`, {
      method: 'PATCH',
      body: JSON.stringify(pricing)
    });
    showNotification('Model pricing updated.', 'success');
    await refreshCatalogs();
  } catch (err) { showNotification(err.message, 'error'); }
}

async function addRule() {
  const ruleId = value('admin-rule-id');
  const name = value('admin-rule-name');
  if (!ruleId || !name) return showNotification('Rule ID and name are required.', 'error');

  const expected = Math.max(0, Math.min(1, number('admin-rule-expected') / 100));
  try {
    await adminFetch('/admin/optimizer-rules', {
      method: 'POST',
      body: JSON.stringify({
        rule_id: ruleId,
        version: 1,
        name,
        description: 'Custom administrator-configured rule.',
        category: 'caching',
        condition: {
          field: value('admin-rule-field'),
          operator: value('admin-rule-op'),
          threshold: number('admin-rule-threshold')
        },
        token_pool: 'input',
        savings_percentage: {
          low: Math.max(0, expected * 0.8),
          expected,
          high: Math.min(1, expected * 1.2)
        },
        max_reduction: 0.60,
        affected_phases: ['*'],
        active: true
      })
    });
    showNotification('Optimizer rule created.', 'success');
    await refreshCatalogs();
  } catch (err) { showNotification(err.message, 'error'); }
}

function renderModels() {
  const body = document.getElementById('admin-models-body');
  body.innerHTML = state.models.map(m => `
    <tr>
      <td>${escapeHtml(m.provider)}</td>
      <td><strong>${escapeHtml(m.model_id)}</strong><br><span class="text-muted">${escapeHtml(m.display_name)}</span></td>
      <td><input class="table-input pricing-input" type="number" step="0.001" value="${m.pricing.input_per_1m}"></td>
      <td><input class="table-input pricing-input" type="number" step="0.001" value="${m.pricing.output_per_1m}"></td>
      <td><input class="table-input pricing-input" type="number" step="0.001" value="${m.pricing.cached_input_per_1m}"></td>
      <td><span class="badge ${m.active ? 'badge-success' : 'badge-danger'}">${m.active ? 'Active' : 'Inactive'}</span></td>
      <td><button class="btn btn-secondary btn-sm save-pricing">Save</button></td>
    </tr>`).join('');

  body.querySelectorAll('.save-pricing').forEach((button, i) => {
    const model = state.models[i];
    button.addEventListener('click', () => updatePricing(model.provider, model.model_id, button));
  });
}

function renderRules() {
  const body = document.getElementById('admin-rules-body');
  body.innerHTML = state.rules.map(r => `
    <tr>
      <td><strong>${escapeHtml(r.rule_id)}</strong><br><span class="text-muted">${escapeHtml(r.name)}</span></td>
      <td>${escapeHtml(r.condition.field)} ${escapeHtml(r.condition.operator)} ${escapeHtml(String(r.condition.threshold))}</td>
      <td>${(Number(r.savings_percentage.expected) * 100).toFixed(0)}%</td>
      <td>${(Number(r.max_reduction) * 100).toFixed(0)}%</td>
      <td><span class="badge ${r.active ? 'badge-success' : 'badge-danger'}">${r.active ? 'Active' : 'Inactive'}</span></td>
    </tr>`).join('');
}

function addLocalKey() {
  const key = value('key-value');
  if (!key) return showNotification('Enter a provider API key.', 'error');
  apiKeysService.addKey(value('key-provider'), key, value('key-label'));
  document.getElementById('key-value').value = '';
  document.getElementById('key-label').value = '';
  renderKeysList();
  showNotification('Local provider key added.', 'success');
}

function renderKeysList() {
  const body = document.getElementById('keys-list-body');
  const keys = apiKeysService.getKeys();
  body.innerHTML = '';
  Object.entries(keys).forEach(([provider, entries]) => entries.forEach(key => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${escapeHtml(provider)}</td><td>${escapeHtml(key.label)}</td>
      <td class="mono">${escapeHtml(key.key.slice(0, 8))}…</td>
      <td><span class="badge ${key.exhausted ? 'badge-danger' : 'badge-success'}">${key.exhausted ? 'Exhausted' : 'Active'}</span></td>
      <td><button class="btn btn-danger btn-sm">Remove</button></td>`;
    tr.querySelector('button').addEventListener('click', () => {
      apiKeysService.removeKey(provider, key.id);
      renderKeysList();
    });
    body.appendChild(tr);
  }));
}

function value(id) { return document.getElementById(id).value.trim(); }
function number(id) { return Number(document.getElementById(id).value) || 0; }
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function showNotification(message, type = 'success') {
  const el = document.getElementById('notification');
  el.textContent = message;
  el.style.background = type === 'error' ? 'var(--danger)' : 'var(--success)';
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 3500);
}
