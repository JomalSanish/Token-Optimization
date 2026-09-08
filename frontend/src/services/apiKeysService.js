const STORAGE_KEY = 'token_optimizer_api_keys';

// Schema: { [provider_id]: [ { id, key, label, isExhausted, createdAt } ] }

export function getKeys() {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : {};
  } catch (e) {
    console.error('Failed to read API keys from localStorage', e);
    return {};
  }
}

function saveKeys(keys) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(keys));
}

export function addKey(provider_id, key, label = '') {
  const keys = getKeys();
  if (!keys[provider_id]) {
    keys[provider_id] = [];
  }
  
  const newKey = {
    id: crypto.randomUUID(),
    key,
    label,
    isExhausted: false,
    createdAt: new Date().toISOString()
  };
  
  keys[provider_id].push(newKey);
  saveKeys(keys);
  return newKey;
}

export function removeKey(provider_id, keyId) {
  const keys = getKeys();
  if (!keys[provider_id]) return;
  
  keys[provider_id] = keys[provider_id].filter(k => k.id !== keyId);
  if (keys[provider_id].length === 0) {
    delete keys[provider_id];
  }
  saveKeys(keys);
}

export function getActiveKey(provider_id) {
  const keys = getKeys();
  if (!keys[provider_id]) return null;
  
  // Find the first unexhausted key
  return keys[provider_id].find(k => !k.isExhausted) || null;
}

export function markKeyExhausted(provider_id, keyId) {
  const keys = getKeys();
  if (!keys[provider_id]) return;
  
  const key = keys[provider_id].find(k => k.id === keyId);
  if (key) {
    key.isExhausted = true;
    saveKeys(keys);
  }
}
