import React, { useState, useEffect, useMemo } from 'react';
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

  // Model Details state (Read-Only)
  const [models, setModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState(null);

  // Model search and filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('all');
  const [selectedTier, setSelectedTier] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');

  // Modal inspection state
  const [inspectingModel, setInspectingModel] = useState(null);

  useEffect(() => {
    async function loadInitialData() {
      try {
        const [providersData, modelsData] = await Promise.all([
          apiFetch('/providers'),
          apiFetch('/models?include_inactive=true').catch(() => apiFetch('/models'))
        ]);
        
        setProviders(providersData);
        setModels(modelsData);

        // Initialize form state for API keys
        const initialForms = {};
        providersData.forEach(p => {
          initialForms[p.provider_id] = { key: '', label: '' };
        });
        setForms(initialForms);

        // Load keys from local storage
        setKeys(getKeys());
      } catch (err) {
        setError(err.message || 'Failed to load providers or models');
        setModelsError(err.message || 'Failed to load model catalog');
      } finally {
        setLoading(false);
        setModelsLoading(false);
      }
    }

    loadInitialData();
  }, []);

  // Handle smooth scroll if navigating to #model-details anchor
  useEffect(() => {
    if (!modelsLoading && window.location.hash === '#model-details') {
      const el = document.getElementById('model-details');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [modelsLoading]);

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
    const form = forms[providerId] || {};
    const key = form.key || '';
    const label = form.label || '';
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

  // Format price helper
  const formatPrice = (val) => {
    const num = Number(val);
    return isNaN(num) ? '$0.0000' : `$${num.toFixed(4)}`;
  };

  // Tier badge styling
  const getTierClass = (tier) => {
    switch (tier) {
      case 'simple': return styles.tierSimple;
      case 'moderate': return styles.tierModerate;
      case 'complex': return styles.tierComplex;
      case 'frontier': return styles.tierFrontier;
      default: return '';
    }
  };

  // Unique providers list from models
  const uniqueModelProviders = useMemo(() => {
    const set = new Set(models.map(m => m.provider).filter(Boolean));
    return Array.from(set).sort();
  }, [models]);

  // Filtered models
  const filteredModels = useMemo(() => {
    return models.filter(m => {
      const query = searchQuery.trim().toLowerCase();
      const matchesQuery = !query ||
        (m.model_id && m.model_id.toLowerCase().includes(query)) ||
        (m.display_name && m.display_name.toLowerCase().includes(query)) ||
        (m.provider && m.provider.toLowerCase().includes(query)) ||
        (m.capabilities && m.capabilities.some(c => c.toLowerCase().includes(query))) ||
        (m.primary_use && m.primary_use.some(u => u.toLowerCase().includes(query)));

      const matchesProvider = selectedProvider === 'all' || m.provider === selectedProvider;
      const matchesTier = selectedTier === 'all' || m.complexity_tier === selectedTier;
      const matchesStatus = selectedStatus === 'all' ||
        (selectedStatus === 'active' ? m.active : !m.active);

      return matchesQuery && matchesProvider && matchesTier && matchesStatus;
    });
  }, [models, searchQuery, selectedProvider, selectedTier, selectedStatus]);

  if (loading && providers.length === 0) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div className={styles.loading}>Loading providers and models...</div>
      </div>
    );
  }

  const hasAnyKeys = Object.values(keys).some(providerKeys => providerKeys.length > 0);

  return (
    <div className={layoutStyles.contentWrapper}>
      {/* SECTION 1: API Keys */}
      <header className={layoutStyles.pageHeader} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2>API Keys</h2>
          <p>Manage your provider API keys. Keys are stored locally in your browser and never sent to our servers except when dispatching LLM calls.</p>
        </div>
        <a 
          href="#model-details" 
          className={styles.viewBtn} 
          style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <span>↓ Jump to Model Details</span>
        </a>
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
                  value={form.key || ''}
                  onChange={(e) => handleInputChange(provider.provider_id, 'key', e.target.value)}
                />
                <input
                  type="text"
                  placeholder="Label (optional)"
                  className={`${styles.input} ${styles.labelInput}`}
                  value={form.label || ''}
                  onChange={(e) => handleInputChange(provider.provider_id, 'label', e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAddKey(provider.provider_id);
                  }}
                />
                <button 
                  className={styles.btnPrimary}
                  onClick={() => handleAddKey(provider.provider_id)}
                  disabled={!form.key || !form.key.trim()}
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

      <hr className={styles.sectionDivider} />

      {/* SECTION 2: Model Details (Read-Only) */}
      <section id="model-details" className={styles.modelSection}>
        <div className={styles.modelSectionHeader}>
          <div>
            <h3>Model Details</h3>
            <p>Comprehensive specifications, capability tags, and pricing breakdown for all registered models.</p>
          </div>
          <div className={styles.readOnlyNotice}>
            <span>🔒 Read-only view</span>
          </div>
        </div>

        {modelsError && (
          <div className={styles.error}>{modelsError}</div>
        )}

        {/* Search & Filters */}
        <div className={styles.modelFilters}>
          <input
            type="text"
            className={`${styles.input} ${styles.searchBox}`}
            placeholder="Search models by ID, name, provider, capabilities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />

          <select
            className={styles.filterSelect}
            value={selectedProvider}
            onChange={(e) => setSelectedProvider(e.target.value)}
          >
            <option value="all">All Providers ({uniqueModelProviders.length})</option>
            {uniqueModelProviders.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>

          <select
            className={styles.filterSelect}
            value={selectedTier}
            onChange={(e) => setSelectedTier(e.target.value)}
          >
            <option value="all">All Tiers</option>
            <option value="simple">Simple</option>
            <option value="moderate">Moderate</option>
            <option value="complex">Complex</option>
            <option value="frontier">Frontier</option>
          </select>

          <select
            className={styles.filterSelect}
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>

        {/* Model Catalog Table */}
        <div className={styles.modelTableContainer}>
          <table className={styles.modelTable}>
            <thead>
              <tr>
                <th>Provider</th>
                <th>Model ID & Display Name</th>
                <th>Status</th>
                <th>Context Window</th>
                <th>Capability Profile</th>
                <th>Pricing (/ 1M tokens)</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {modelsLoading && models.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '32px' }}>
                    Loading model details...
                  </td>
                </tr>
              ) : filteredModels.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '32px', color: 'var(--text)' }}>
                    No models match your current filters.
                  </td>
                </tr>
              ) : (
                filteredModels.map(m => (
                  <tr key={`${m.provider}-${m.model_id}`}>
                    <td>
                      <span style={{ fontWeight: 600, color: 'var(--text-h)', textTransform: 'capitalize' }}>
                        {m.provider}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <code style={{ fontSize: '13px', color: 'var(--accent)' }}>{m.model_id}</code>
                        <span style={{ fontSize: '13px', color: 'var(--text-h)', fontWeight: 500 }}>
                          {m.display_name}
                        </span>
                      </div>
                    </td>
                    <td>
                      <span className={`${styles.badge} ${m.active ? styles.statusActive : styles.statusInactive}`}>
                        {m.active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: '13px' }}>
                        {Number(m.context_window || 0).toLocaleString()}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div>
                          <span className={`${styles.badge} ${styles.tierBadge} ${getTierClass(m.complexity_tier)}`}>
                            {m.complexity_tier || 'simple'}
                          </span>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text)' }}>
                          <span>Reasoning: <b>{m.reasoning_complexity}</b></span> · <span>Output: <b>{m.output_quality}</b></span>
                        </div>
                        {m.primary_use && m.primary_use.length > 0 && (
                          <div className={styles.tagChipList}>
                            {m.primary_use.map(u => (
                              <span key={u} className={styles.tagChip}>{u}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className={styles.priceSnippet}>
                        <div>Input: <span>{formatPrice(m.pricing?.input_per_1m)}</span></div>
                        <div>Output: <span>{formatPrice(m.pricing?.output_per_1m)}</span></div>
                        <div>Cached In: <span>{formatPrice(m.pricing?.cached_input_per_1m)}</span></div>
                        <div>Batch: <span>{formatPrice(m.pricing?.batch_input_per_1m)}</span> / <span>{formatPrice(m.pricing?.batch_output_per_1m)}</span></div>
                      </div>
                    </td>
                    <td>
                      <button 
                        className={styles.viewBtn}
                        onClick={() => setInspectingModel(m)}
                        title="View complete specifications and pricing"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* READ-ONLY MODEL DETAIL MODAL */}
      {inspectingModel && (
        <div className={styles.modalOverlay} onClick={() => setInspectingModel(null)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>
                <span>{inspectingModel.display_name}</span>
                <span className={`${styles.badge} ${inspectingModel.active ? styles.statusActive : styles.statusInactive}`}>
                  {inspectingModel.active ? 'Active' : 'Inactive'}
                </span>
              </h3>
              <button 
                onClick={() => setInspectingModel(null)}
                style={{ background: 'transparent', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text)' }}
              >✕</button>
            </div>

            <div className={styles.modalBody}>
              <div className={styles.readOnlyNotice}>
                <span role="img" aria-label="shield">🛡️</span>
                <span><b>Read-Only Specifications:</b> Regular users cannot modify model parameters, capability tags, or pricing rates. Contact an administrator to update model definitions.</span>
              </div>

              {/* General Model Information */}
              <div>
                <h4 className={styles.modalSectionTitle}>General Information</h4>
                <div className={styles.detailGrid}>
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>Provider</span>
                    <span className={styles.detailValue} style={{ textTransform: 'capitalize' }}>{inspectingModel.provider}</span>
                  </div>
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>Model ID</span>
                    <code className={styles.detailValue} style={{ fontFamily: 'var(--mono)' }}>{inspectingModel.model_id}</code>
                  </div>
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>Context Window</span>
                    <span className={styles.detailValue}>{Number(inspectingModel.context_window || 0).toLocaleString()} tokens</span>
                  </div>
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>Pricing Version</span>
                    <span className={styles.detailValue}>v{inspectingModel.pricing_version || 1}</span>
                  </div>
                </div>
              </div>

              {/* Capabilities */}
              {inspectingModel.capabilities && inspectingModel.capabilities.length > 0 && (
                <div>
                  <h4 className={styles.modalSectionTitle}>Model Capabilities</h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {inspectingModel.capabilities.map(cap => (
                      <span key={cap} className={styles.tagChip} style={{ padding: '4px 10px', fontSize: '12px' }}>
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Capability & Routing Tags */}
              <div>
                <h4 className={styles.modalSectionTitle}>Capability Tags</h4>
                <div className={styles.detailGrid}>
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>Complexity Tier</span>
                    <span className={`${styles.badge} ${styles.tierBadge} ${getTierClass(inspectingModel.complexity_tier)}`} style={{ alignSelf: 'flex-start', marginTop: '4px' }}>
                      {inspectingModel.complexity_tier}
                    </span>
                  </div>
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>Reasoning Complexity</span>
                    <span className={styles.detailValue}>{inspectingModel.reasoning_complexity}</span>
                  </div>
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>Output Quality</span>
                    <span className={styles.detailValue}>{inspectingModel.output_quality}</span>
                  </div>
                </div>

                {inspectingModel.primary_use && inspectingModel.primary_use.length > 0 && (
                  <div style={{ marginTop: '12px' }}>
                    <span className={styles.detailLabel} style={{ display: 'block', marginBottom: '6px' }}>Primary Use Cases</span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {inspectingModel.primary_use.map(use => (
                        <span key={use} className={styles.tagChip} style={{ padding: '4px 10px', fontSize: '12px' }}>
                          {use}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Complete Pricing Breakdown */}
              <div>
                <h4 className={styles.modalSectionTitle}>Pricing Matrix (per 1,000,000 Tokens)</h4>
                <table className={styles.pricingTable}>
                  <thead>
                    <tr>
                      <th>Pricing Category</th>
                      <th>Rate per 1M Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Input Tokens</td>
                      <td>{formatPrice(inspectingModel.pricing?.input_per_1m)}</td>
                    </tr>
                    <tr>
                      <td>Output Tokens</td>
                      <td>{formatPrice(inspectingModel.pricing?.output_per_1m)}</td>
                    </tr>
                    <tr>
                      <td>Cached Input Tokens</td>
                      <td>{formatPrice(inspectingModel.pricing?.cached_input_per_1m)}</td>
                    </tr>
                    <tr>
                      <td>Batch Input Tokens</td>
                      <td>{formatPrice(inspectingModel.pricing?.batch_input_per_1m)}</td>
                    </tr>
                    <tr>
                      <td>Batch Output Tokens</td>
                      <td>{formatPrice(inspectingModel.pricing?.batch_output_per_1m)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {inspectingModel.effective_from && (
                <div style={{ fontSize: '12px', color: 'var(--text)', textAlign: 'right' }}>
                  Effective Since: {new Date(inspectingModel.effective_from).toLocaleString()}
                </div>
              )}
            </div>

            <div className={styles.modalFooter}>
              <button 
                className={styles.viewBtn}
                onClick={() => setInspectingModel(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
