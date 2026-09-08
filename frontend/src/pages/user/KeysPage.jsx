import React, { useState, useEffect } from 'react';
import { apiFetch } from '../../services/api';
import { getKeys, addKey, removeKey } from '../../services/apiKeysService';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './KeysPage.module.css';

export default function KeysPage() {
  const [providers, setProviders] = useState([]);
  const [keys, setKeys] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Form state per provider: { [provider_id]: { key: '', label: '' } }
  const [forms, setForms] = useState({});

  useEffect(() => {
    async function fetchProviders() {
      try {
        const data = await apiFetch('/providers');
        setProviders(data);
        
        // Initialize form state
        const initialForms = {};
        data.forEach(p => {
          initialForms[p.provider_id] = { key: '', label: '' };
        });
        setForms(initialForms);
        
        // Load keys from local storage
        setKeys(getKeys());
      } catch (err) {
        setError(err.message || 'Failed to load providers');
      } finally {
        setLoading(false);
      }
    }
    fetchProviders();
  }, []);

  const handleInputChange = (providerId, field, value) => {
    setForms(prev => ({
      ...prev,
      [providerId]: {
        ...prev[providerId],
        [field]: value
      }
    }));
  };

  const handleAddKey = (providerId) => {
    const { key, label } = forms[providerId];
    if (!key.trim()) return;

    addKey(providerId, key.trim(), label.trim());
    
    // Refresh keys and clear form
    setKeys(getKeys());
    setForms(prev => ({
      ...prev,
      [providerId]: { key: '', label: '' }
    }));
  };

  const handleRemoveKey = (providerId, keyId) => {
    removeKey(providerId, keyId);
    setKeys(getKeys());
  };

  // Mask key for display
  const maskKey = (keyString) => {
    if (!keyString || keyString.length < 8) return '********';
    return `${keyString.slice(0, 4)}...${keyString.slice(-4)}`;
  };

  if (loading) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div className={styles.loading}>Loading providers...</div>
      </div>
    );
  }

  const hasAnyKeys = Object.values(keys).some(providerKeys => providerKeys.length > 0);

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader}>
        <h2>API Keys</h2>
        <p>Manage your provider API keys. Keys are stored locally in your browser and never sent to our servers except when dispatching LLM calls.</p>
      </header>

      {error && (
        <div className={styles.error}>{error}</div>
      )}

      {!hasAnyKeys && (
        <div className={styles.emptyState} style={{ marginBottom: '24px', padding: '24px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', borderRadius: '8px', border: '1px solid #10b981', textAlign: 'center' }}>
          Add your first API key to get started
        </div>
      )}

      <div className={styles.container}>
        {providers.map(provider => {
          const providerKeys = keys[provider.provider_id] || [];
          const form = forms[provider.provider_id] || { key: '', label: '' };

          return (
            <div key={provider.provider_id} className={styles.providerCard}>
              <div className={styles.providerHeader}>
                <h3>{provider.display_name}</h3>
              </div>

              <div className={styles.addKeyForm}>
                <input
                  type="text"
                  placeholder="API Key (e.g. sk-...)"
                  className={styles.input}
                  value={form.key}
                  onChange={(e) => handleInputChange(provider.provider_id, 'key', e.target.value)}
                />
                <input
                  type="text"
                  placeholder="Label (optional)"
                  className={`${styles.input} ${styles.labelInput}`}
                  value={form.label}
                  onChange={(e) => handleInputChange(provider.provider_id, 'label', e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAddKey(provider.provider_id);
                  }}
                />
                <button 
                  className={styles.btnPrimary}
                  onClick={() => handleAddKey(provider.provider_id)}
                  disabled={!form.key.trim()}
                >
                  Add
                </button>
              </div>

              {providerKeys.length > 0 && (
                <div className={styles.keysList}>
                  {providerKeys.map(k => (
                    <div key={k.id} className={styles.keyItem}>
                      <div className={styles.keyInfo}>
                        <span className={styles.keyLabel}>
                          {k.label || 'Unnamed Key'}
                          {k.isExhausted && ' (Exhausted)'}
                        </span>
                        <span className={styles.keyValue}>{maskKey(k.key)}</span>
                      </div>
                      <button 
                        className={styles.btnDanger}
                        onClick={() => handleRemoveKey(provider.provider_id, k.id)}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {providers.length === 0 && !error && (
          <p>No active providers available.</p>
        )}
      </div>
    </div>
  );
}
