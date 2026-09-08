import React, { useState, useEffect } from 'react';
import { adminApiFetch } from '../../services/api';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './Admin.module.css';

// Enum values below MUST mirror backend/src/schemas.py exactly
// (COMPLEXITY_TIER_VALUES, REASONING_COMPLEXITY_VALUES, OUTPUT_QUALITY_VALUES,
// PRIMARY_USE_VALUES) — the backend rejects (422) any other value, and
// pricing sub-fields must match ModelPricing exactly (all 5 required).
const COMPLEXITY_TIERS = ['simple', 'moderate', 'complex', 'frontier'];
const REASONING_COMPLEXITIES = ['direct', 'single-step', 'multi-step', 'deep-reasoning'];
const OUTPUT_QUALITIES = ['draft', 'standard', 'high-fidelity', 'expert-grade'];
const PRIMARY_USES = [
  'extraction', 'classification', 'summarization', 'code-generation',
  'reasoning', 'instruction-following', 'long-context', 'multimodal'
];

const DEFAULT_MODEL = {
  provider: '',
  model_id: '',
  display_name: '',
  context_window: 128000,
  capabilities: [],
  pricing: {
    input_per_1m: 0,
    output_per_1m: 0,
    cached_input_per_1m: 0,
    batch_input_per_1m: 0,
    batch_output_per_1m: 0
  },
  complexity_tier: 'simple',
  reasoning_complexity: 'direct',
  output_quality: 'draft',
  primary_use: []
};

export default function ModelsPage() {
  const [models, setModels] = useState([]);
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingMode, setEditingMode] = useState(null); // 'create', 'tags', 'pricing'
  const [formData, setFormData] = useState(DEFAULT_MODEL);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [modelsData, providersData] = await Promise.all([
        adminApiFetch('/admin/models'),
        adminApiFetch('/admin/providers')
      ]);
      setModels(modelsData);
      setProviders(providersData);
    } catch (err) {
      setError(err.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = (mode, model = null) => {
    setError(null);
    setEditingMode(mode);
    if (model) {
      setFormData({
        provider: model.provider,
        model_id: model.model_id,
        display_name: model.display_name,
        context_window: model.context_window,
        capabilities: model.capabilities || [],
        pricing: { ...model.pricing },
        complexity_tier: model.complexity_tier || 'simple',
        reasoning_complexity: model.reasoning_complexity || 'direct',
        output_quality: model.output_quality || 'draft',
        primary_use: model.primary_use || []
      });
    } else {
      setFormData({
        ...DEFAULT_MODEL,
        provider: providers.length > 0 ? providers[0].provider_id : ''
      });
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setError(null);
  };

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handlePricingChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      pricing: { ...prev.pricing, [field]: parseFloat(value) || 0 }
    }));
  };

  const handlePrimaryUseChange = (e) => {
    const options = e.target.options;
    const selected = [];
    for (let i = 0; i < options.length; i++) {
      if (options[i].selected) {
        selected.push(options[i].value);
      }
    }
    handleChange('primary_use', selected);
  };

  const handleToggleStatus = async (model) => {
    try {
      const endpoint = model.active 
        ? `/admin/models/${model.model_id}/deactivate` 
        : `/admin/models/${model.model_id}/activate`;
      
      await adminApiFetch(endpoint, {
        method: 'POST'
      });
      fetchData();
    } catch (err) {
      setError(err.message || 'Failed to toggle status');
    }
  };

  const handleSave = async () => {
    setError(null);
    try {
      if (editingMode === 'create') {
        await adminApiFetch('/admin/models', {
          method: 'POST',
          body: JSON.stringify(formData)
        });
      } else if (editingMode === 'tags') {
        const payload = {
          complexity_tier: formData.complexity_tier,
          reasoning_complexity: formData.reasoning_complexity,
          output_quality: formData.output_quality,
          primary_use: formData.primary_use
        };
        await adminApiFetch(`/admin/models/${formData.model_id}/tags?provider=${formData.provider}`, {
          method: 'PATCH',
          body: JSON.stringify(payload)
        });
      } else if (editingMode === 'pricing') {
        await adminApiFetch(`/admin/models/${formData.model_id}?provider=${formData.provider}`, {
          method: 'PATCH',
          body: JSON.stringify(formData.pricing)
        });
      }

      handleCloseModal();
      fetchData();
    } catch (err) {
      setError(err.message || 'Failed to save model');
    }
  };

  if (loading && models.length === 0) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Loading models...</div>
      </div>
    );
  }

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Models</h2>
          <p>Manage model capability tags and pricing per provider.</p>
        </div>
        <button className={styles.btnPrimary} onClick={() => handleOpenModal('create')}>
          + Add Model
        </button>
      </header>

      {error && !isModalOpen && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Provider</th>
                <th>Model ID</th>
                <th>Display Name</th>
                <th>Status</th>
                <th>Capability Tags</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.map(m => (
                <tr key={`${m.provider}-${m.model_id}`}>
                  <td>{m.provider}</td>
                  <td><code>{m.model_id}</code></td>
                  <td>{m.display_name}</td>
                  <td>
                    <span className={`${styles.statusBadge} ${m.active ? styles.statusActive : styles.statusInactive}`}>
                      {m.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ fontSize: '12px' }}>
                    <div><b>Tier:</b> {m.complexity_tier}</div>
                    <div><b>Reasoning:</b> {m.reasoning_complexity}</div>
                    <div><b>Output:</b> {m.output_quality}</div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      <button className={styles.actionBtn} onClick={() => handleOpenModal('tags', m)}>Tags</button>
                      <button className={styles.actionBtn} onClick={() => handleOpenModal('pricing', m)}>Pricing</button>
                      <button 
                        className={styles.actionBtn} 
                        onClick={() => handleToggleStatus(m)}
                      >
                        {m.active ? 'Deactivate' : 'Activate'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {models.length === 0 && (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center' }}>No models found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {isModalOpen && (
        <div className={styles.modalOverlay}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h3>
                {editingMode === 'create' && 'Add Model'}
                {editingMode === 'tags' && `Edit Tags: ${formData.model_id}`}
                {editingMode === 'pricing' && `Edit Pricing: ${formData.model_id}`}
              </h3>
              <button 
                onClick={handleCloseModal}
                style={{ background: 'transparent', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text)' }}
              >✕</button>
            </div>
            
            <div className={styles.modalBody}>
              {error && <div className={styles.error}>{error}</div>}

              {editingMode === 'create' && (
                <>
                  <div className={styles.formGroup}>
                    <label>Provider</label>
                    <select 
                      className={styles.select}
                      value={formData.provider}
                      onChange={e => handleChange('provider', e.target.value)}
                    >
                      <option value="">Select Provider...</option>
                      {providers.map(p => <option key={p.provider_id} value={p.provider_id}>{p.display_name}</option>)}
                    </select>
                  </div>
                  <div className={styles.formGroup}>
                    <label>Model ID</label>
                    <input 
                      className={styles.input}
                      value={formData.model_id}
                      onChange={e => handleChange('model_id', e.target.value)}
                      placeholder="e.g. gpt-4"
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Display Name</label>
                    <input 
                      className={styles.input}
                      value={formData.display_name}
                      onChange={e => handleChange('display_name', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Context Window</label>
                    <input 
                      type="number"
                      className={styles.input}
                      value={formData.context_window}
                      onChange={e => handleChange('context_window', parseInt(e.target.value) || 0)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Capabilities (comma separated, e.g. text, vision, tool_use)</label>
                    <input 
                      className={styles.input}
                      value={formData.capabilities.join(', ')}
                      onChange={e => handleChange('capabilities', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                      placeholder="text, vision, tool_use"
                    />
                  </div>
                </>
              )}

              {(editingMode === 'create' || editingMode === 'pricing') && (
                <>
                  <h4 style={{ margin: '10px 0 0', color: 'var(--text-h)' }}>Pricing Setup</h4>
                  <div className={styles.formGroup}>
                    <label>Input Price (per 1M tokens)</label>
                    <input 
                      type="number"
                      step="0.001"
                      className={styles.input}
                      value={formData.pricing.input_per_1m}
                      onChange={e => handlePricingChange('input_per_1m', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Output Price (per 1M tokens)</label>
                    <input 
                      type="number"
                      step="0.001"
                      className={styles.input}
                      value={formData.pricing.output_per_1m}
                      onChange={e => handlePricingChange('output_per_1m', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Cached Input Price (per 1M tokens)</label>
                    <input 
                      type="number"
                      step="0.001"
                      className={styles.input}
                      value={formData.pricing.cached_input_per_1m}
                      onChange={e => handlePricingChange('cached_input_per_1m', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Batch Input Price (per 1M tokens)</label>
                    <input 
                      type="number"
                      step="0.001"
                      className={styles.input}
                      value={formData.pricing.batch_input_per_1m}
                      onChange={e => handlePricingChange('batch_input_per_1m', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Batch Output Price (per 1M tokens)</label>
                    <input 
                      type="number"
                      step="0.001"
                      className={styles.input}
                      value={formData.pricing.batch_output_per_1m}
                      onChange={e => handlePricingChange('batch_output_per_1m', e.target.value)}
                    />
                  </div>
                </>
              )}

              {(editingMode === 'create' || editingMode === 'tags') && (
                <>
                  <h4 style={{ margin: '10px 0 0', color: 'var(--text-h)' }}>Capability Tags</h4>
                  <div className={styles.formGroup}>
                    <label>Complexity Tier</label>
                    <select 
                      className={styles.select}
                      value={formData.complexity_tier}
                      onChange={e => handleChange('complexity_tier', e.target.value)}
                    >
                      {COMPLEXITY_TIERS.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </div>
                  <div className={styles.formGroup}>
                    <label>Reasoning Complexity</label>
                    <select 
                      className={styles.select}
                      value={formData.reasoning_complexity}
                      onChange={e => handleChange('reasoning_complexity', e.target.value)}
                    >
                      {REASONING_COMPLEXITIES.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </div>
                  <div className={styles.formGroup}>
                    <label>Output Quality</label>
                    <select 
                      className={styles.select}
                      value={formData.output_quality}
                      onChange={e => handleChange('output_quality', e.target.value)}
                    >
                      {OUTPUT_QUALITIES.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </div>
                  <div className={styles.formGroup}>
                    <label>Primary Use (Multi-select)</label>
                    <select 
                      multiple
                      className={styles.select}
                      style={{ height: '120px' }}
                      value={formData.primary_use}
                      onChange={handlePrimaryUseChange}
                    >
                      {PRIMARY_USES.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                    <small style={{ color: 'var(--text)', fontSize: '12px' }}>Hold Ctrl/Cmd to select multiple. At least one value is required.</small>
                  </div>
                </>
              )}

            </div>
            <div className={styles.modalFooter}>
              <button className={styles.btnSecondary} onClick={handleCloseModal}>Cancel</button>
              <button 
                className={styles.btnPrimary} 
                onClick={handleSave}
                disabled={
                  (editingMode === 'create' && (!formData.model_id || !formData.provider || !formData.display_name || formData.capabilities.length === 0)) ||
                  ((editingMode === 'create' || editingMode === 'tags') && formData.primary_use.length === 0)
                }
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
