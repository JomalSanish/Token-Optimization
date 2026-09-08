import React, { useState, useEffect } from 'react';
import { adminApiFetch } from '../../services/api';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './Admin.module.css';

// Enum values below MUST mirror backend/src/schemas.py exactly
// (COMPLEXITY_TIER_VALUES, REASONING_COMPLEXITY_VALUES, OUTPUT_QUALITY_VALUES) —
// these are the SAME three enums used by models.complexity_tier /
// reasoning_complexity / output_quality (see data-model.md: "Enum values
// match the model capability tag enums exactly"). The backend rejects (422)
// any other value.
const COMPLEXITY_TIERS = ['simple', 'moderate', 'complex', 'frontier'];
const REASONING_COMPLEXITIES = ['direct', 'single-step', 'multi-step', 'deep-reasoning'];
const OUTPUT_QUALITIES = ['draft', 'standard', 'high-fidelity', 'expert-grade'];

const DEFAULT_PHASE = {
  phase_id: '',
  name: '',
  sort_order: 10,
  default_agent_role: 'Agent',
  default_cacheable_fraction: 0.0,
  ams_classified: false,
  default_complexity_tier: 'simple',
  default_reasoning_complexity: 'direct',
  default_output_quality: 'draft'
};

export default function PhasesPage() {
  const [phases, setPhases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState(DEFAULT_PHASE);

  useEffect(() => {
    fetchPhases();
  }, []);

  const fetchPhases = async () => {
    try {
      setLoading(true);
      const data = await adminApiFetch('/admin/phases');
      setPhases(data);
    } catch (err) {
      setError(err.message || 'Failed to load phases');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = (phase = null) => {
    setError(null);
    if (phase) {
      setEditingId(phase.phase_id);
      setFormData({
        phase_id: phase.phase_id,
        name: phase.name,
        sort_order: phase.sort_order,
        default_agent_role: phase.default_agent_role,
        default_cacheable_fraction: phase.default_cacheable_fraction,
        ams_classified: phase.ams_classified,
        default_complexity_tier: phase.default_complexity_tier || 'simple',
        default_reasoning_complexity: phase.default_reasoning_complexity || 'direct',
        default_output_quality: phase.default_output_quality || 'draft'
      });
    } else {
      setEditingId(null);
      setFormData(DEFAULT_PHASE);
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

  const handleSave = async () => {
    setError(null);
    try {
      const payload = {
        name: formData.name,
        sort_order: parseInt(formData.sort_order) || 0,
        default_agent_role: formData.default_agent_role,
        default_cacheable_fraction: parseFloat(formData.default_cacheable_fraction) || 0,
        ams_classified: formData.ams_classified,
        default_complexity_tier: formData.default_complexity_tier,
        default_reasoning_complexity: formData.default_reasoning_complexity,
        default_output_quality: formData.default_output_quality
      };

      if (!editingId) {
        payload.phase_id = formData.phase_id;
        await adminApiFetch('/admin/phases', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
      } else {
        await adminApiFetch(`/admin/phases/${editingId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload)
        });
      }

      handleCloseModal();
      fetchPhases();
    } catch (err) {
      setError(err.message || 'Failed to save phase');
    }
  };

  if (loading && phases.length === 0) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Loading phases...</div>
      </div>
    );
  }

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Phases</h2>
          <p>Manage default architectural phases and their baseline LLM capability requirements.</p>
        </div>
        <button className={styles.btnPrimary} onClick={() => handleOpenModal()}>
          + Add Phase
        </button>
      </header>

      {error && !isModalOpen && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Order</th>
                <th>Phase ID</th>
                <th>Name</th>
                <th>Role</th>
                <th>Default Requirements</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {phases.map(p => (
                <tr key={p.phase_id}>
                  <td>{p.sort_order}</td>
                  <td><code>{p.phase_id}</code></td>
                  <td>{p.name}</td>
                  <td>{p.default_agent_role}</td>
                  <td style={{ fontSize: '12px' }}>
                    <div><b>Tier:</b> {p.default_complexity_tier}</div>
                    <div><b>Reasoning:</b> {p.default_reasoning_complexity}</div>
                    <div><b>Quality:</b> {p.default_output_quality}</div>
                  </td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => handleOpenModal(p)}>Edit</button>
                  </td>
                </tr>
              ))}
              {phases.length === 0 && (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center' }}>No phases found.</td>
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
              <h3>{editingId ? 'Edit Phase' : 'Add Phase'}</h3>
              <button 
                onClick={handleCloseModal}
                style={{ background: 'transparent', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text)' }}
              >✕</button>
            </div>
            
            <div className={styles.modalBody}>
              {error && <div className={styles.error}>{error}</div>}

              {!editingId && (
                <div className={styles.formGroup}>
                  <label>Phase ID</label>
                  <input 
                    className={styles.input}
                    value={formData.phase_id}
                    onChange={e => handleChange('phase_id', e.target.value)}
                  />
                </div>
              )}

              <div className={styles.formGroup}>
                <label>Name</label>
                <input 
                  className={styles.input}
                  value={formData.name}
                  onChange={e => handleChange('name', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Sort Order</label>
                <input 
                  type="number"
                  className={styles.input}
                  value={formData.sort_order}
                  onChange={e => handleChange('sort_order', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Default Agent Role</label>
                <input 
                  className={styles.input}
                  value={formData.default_agent_role}
                  onChange={e => handleChange('default_agent_role', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Default Cacheable Fraction</label>
                <input 
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  className={styles.input}
                  value={formData.default_cacheable_fraction}
                  onChange={e => handleChange('default_cacheable_fraction', e.target.value)}
                />
              </div>

              <div className={styles.formGroup} style={{ flexDirection: 'row', alignItems: 'center' }}>
                <input 
                  type="checkbox" 
                  id="amsPhaseCheck"
                  checked={formData.ams_classified}
                  onChange={e => handleChange('ams_classified', e.target.checked)}
                  style={{ width: '16px', height: '16px' }}
                />
                <label htmlFor="amsPhaseCheck" style={{ margin: 0, cursor: 'pointer' }}>AMS Classified</label>
              </div>

              <h4 style={{ margin: '10px 0 0', color: 'var(--text-h)' }}>Default Capability Requirements</h4>
              
              <div className={styles.formGroup}>
                <label>Complexity Tier</label>
                <select 
                  className={styles.select}
                  value={formData.default_complexity_tier}
                  onChange={e => handleChange('default_complexity_tier', e.target.value)}
                >
                  {COMPLEXITY_TIERS.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>Reasoning Complexity</label>
                <select 
                  className={styles.select}
                  value={formData.default_reasoning_complexity}
                  onChange={e => handleChange('default_reasoning_complexity', e.target.value)}
                >
                  {REASONING_COMPLEXITIES.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>Output Quality</label>
                <select 
                  className={styles.select}
                  value={formData.default_output_quality}
                  onChange={e => handleChange('default_output_quality', e.target.value)}
                >
                  {OUTPUT_QUALITIES.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>

            </div>
            <div className={styles.modalFooter}>
              <button className={styles.btnSecondary} onClick={handleCloseModal}>Cancel</button>
              <button 
                className={styles.btnPrimary} 
                onClick={handleSave}
                disabled={!formData.name || (!editingId && !formData.phase_id)}
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
