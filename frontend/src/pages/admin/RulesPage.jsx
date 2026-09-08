import React, { useState, useEffect } from 'react';
import { adminApiFetch } from '../../services/api';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './Admin.module.css';

// Shape below MUST mirror backend/src/schemas.py OptimizerRuleIn exactly:
//   rule_id, version, name, description, category,
//   condition: { field, operator, threshold },
//   token_pool: "input" | "output" | "both"   (regex-enforced, required),
//   savings_percentage: { low, expected, high }  (0 <= low <= expected <= high <= 1),
//   max_reduction, affected_phases, active
const TOKEN_POOLS = ['input', 'output', 'both'];
const OPERATORS = ['gt', 'gte', 'lt', 'lte', 'eq'];

const DEFAULT_RULE = {
  rule_id: '',
  version: 1,
  name: '',
  description: '',
  category: '',
  condition: {
    field: '',
    operator: 'gte',
    threshold: 0
  },
  token_pool: 'both',
  savings_percentage: {
    low: 0,
    expected: 0,
    high: 0
  },
  max_reduction: 0,
  affected_phases: [],
  active: true
};

export default function RulesPage() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState(DEFAULT_RULE);

  useEffect(() => {
    fetchRules();
  }, []);

  const fetchRules = async () => {
    try {
      setLoading(true);
      const data = await adminApiFetch('/admin/optimizer-rules');
      setRules(data);
    } catch (err) {
      setError(err.message || 'Failed to load rules');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = (rule = null) => {
    setError(null);
    if (rule) {
      setEditingId(rule.rule_id);
      setFormData({
        rule_id: rule.rule_id,
        version: rule.version ?? 1,
        name: rule.name || '',
        description: rule.description || '',
        category: rule.category || '',
        condition: {
          field: rule.condition?.field || '',
          operator: rule.condition?.operator || 'gte',
          threshold: rule.condition?.threshold ?? 0
        },
        token_pool: rule.token_pool || 'both',
        savings_percentage: {
          low: rule.savings_percentage?.low ?? 0,
          expected: rule.savings_percentage?.expected ?? 0,
          high: rule.savings_percentage?.high ?? 0
        },
        max_reduction: rule.max_reduction ?? 0,
        affected_phases: rule.affected_phases || [],
        active: rule.active
      });
    } else {
      setEditingId(null);
      setFormData(DEFAULT_RULE);
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

  const handleConditionChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      condition: {
        ...prev.condition,
        [field]: field === 'threshold' ? (parseFloat(value) || 0) : value
      }
    }));
  };

  const handleSavingsChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      savings_percentage: {
        ...prev.savings_percentage,
        [field]: parseFloat(value) || 0
      }
    }));
  };

  const handleToggleStatus = async (rule) => {
    try {
      const endpoint = rule.active 
        ? `/admin/optimizer-rules/${rule.rule_id}/deactivate` 
        : `/admin/optimizer-rules/${rule.rule_id}/activate`;
        
      await adminApiFetch(endpoint, { method: 'POST' });
      fetchRules();
    } catch (err) {
      setError(err.message || 'Failed to toggle status');
    }
  };

  const handleSave = async () => {
    setError(null);

    // Mirror backend OptimizerRuleSavings.validate_bounds so the user gets an
    // immediate, specific error instead of a generic 422 from the API.
    const { low, expected, high } = formData.savings_percentage;
    if (!(low <= expected && expected <= high)) {
      setError('Savings percentage must satisfy: low <= expected <= high.');
      return;
    }

    try {
      const payload = {
        name: formData.name,
        description: formData.description,
        category: formData.category,
        condition: {
          field: formData.condition.field,
          operator: formData.condition.operator,
          threshold: formData.condition.threshold
        },
        token_pool: formData.token_pool,
        savings_percentage: formData.savings_percentage,
        max_reduction: parseFloat(formData.max_reduction) || 0,
        affected_phases: formData.affected_phases,
        active: formData.active
      };

      if (!editingId) {
        payload.rule_id = formData.rule_id;
        payload.version = parseInt(formData.version) || 1;
        await adminApiFetch('/admin/optimizer-rules', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
      } else {
        await adminApiFetch(`/admin/optimizer-rules/${editingId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload)
        });
      }

      handleCloseModal();
      fetchRules();
    } catch (err) {
      setError(err.message || 'Failed to save rule');
    }
  };

  if (loading && rules.length === 0) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Loading rules...</div>
      </div>
    );
  }

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Optimizer Rules</h2>
          <p>Manage deterministic cost-reduction rules and their trigger conditions.</p>
        </div>
        <button className={styles.btnPrimary} onClick={() => handleOpenModal()}>
          + Add Rule
        </button>
      </header>

      {error && !isModalOpen && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Rule ID</th>
                <th>Name</th>
                <th>Category</th>
                <th>Token Pool</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rules.map(r => (
                <tr key={r.rule_id}>
                  <td><code>{r.rule_id}</code> (v{r.version})</td>
                  <td>{r.name}</td>
                  <td>{r.category}</td>
                  <td>{r.token_pool}</td>
                  <td>
                    <span className={`${styles.statusBadge} ${r.active ? styles.statusActive : styles.statusInactive}`}>
                      {r.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => handleOpenModal(r)}>Edit</button>
                    <button 
                      className={styles.actionBtn} 
                      onClick={() => handleToggleStatus(r)}
                    >
                      {r.active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center' }}>No rules found.</td>
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
              <h3>{editingId ? 'Edit Rule' : 'Add Rule'}</h3>
              <button 
                onClick={handleCloseModal}
                style={{ background: 'transparent', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text)' }}
              >✕</button>
            </div>
            
            <div className={styles.modalBody}>
              {error && <div className={styles.error}>{error}</div>}

              {!editingId && (
                <>
                  <div className={styles.formGroup}>
                    <label>Rule ID</label>
                    <input 
                      className={styles.input}
                      value={formData.rule_id}
                      onChange={e => handleChange('rule_id', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Version</label>
                    <input 
                      type="number"
                      className={styles.input}
                      value={formData.version}
                      onChange={e => handleChange('version', e.target.value)}
                    />
                  </div>
                </>
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
                <label>Description</label>
                <textarea 
                  className={styles.textarea}
                  value={formData.description}
                  onChange={e => handleChange('description', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Category</label>
                <input 
                  className={styles.input}
                  value={formData.category}
                  onChange={e => handleChange('category', e.target.value)}
                  placeholder="e.g. caching, batching, model-downgrade"
                />
              </div>

              <div className={styles.formGroup}>
                <label>Token Pool</label>
                <select 
                  className={styles.select}
                  value={formData.token_pool}
                  onChange={e => handleChange('token_pool', e.target.value)}
                >
                  {TOKEN_POOLS.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>

              <h4 style={{ margin: '10px 0 0', color: 'var(--text-h)' }}>Trigger Condition</h4>
              <div className={styles.formGroup}>
                <label>Field</label>
                <input 
                  className={styles.input}
                  value={formData.condition.field}
                  onChange={e => handleConditionChange('field', e.target.value)}
                  placeholder="e.g. context_input_tokens"
                />
              </div>
              <div className={styles.formGroup}>
                <label>Operator</label>
                <select 
                  className={styles.select}
                  value={formData.condition.operator}
                  onChange={e => handleConditionChange('operator', e.target.value)}
                >
                  {OPERATORS.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>Threshold</label>
                <input 
                  type="number"
                  step="0.01"
                  className={styles.input}
                  value={formData.condition.threshold}
                  onChange={e => handleConditionChange('threshold', e.target.value)}
                />
              </div>

              <h4 style={{ margin: '10px 0 0', color: 'var(--text-h)' }}>Savings Percentage (0-1, low &lt;= expected &lt;= high)</h4>
              <div className={styles.formGroup}>
                <label>Low</label>
                <input 
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  className={styles.input}
                  value={formData.savings_percentage.low}
                  onChange={e => handleSavingsChange('low', e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label>Expected</label>
                <input 
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  className={styles.input}
                  value={formData.savings_percentage.expected}
                  onChange={e => handleSavingsChange('expected', e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label>High</label>
                <input 
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  className={styles.input}
                  value={formData.savings_percentage.high}
                  onChange={e => handleSavingsChange('high', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Max Reduction Constraint</label>
                <input 
                  type="number"
                  step="0.01"
                  className={styles.input}
                  value={formData.max_reduction}
                  onChange={e => handleChange('max_reduction', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Affected Phases (comma separated)</label>
                <input 
                  className={styles.input}
                  value={formData.affected_phases.join(', ')}
                  onChange={e => handleChange('affected_phases', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  placeholder="e.g. design, development"
                />
              </div>

            </div>
            <div className={styles.modalFooter}>
              <button className={styles.btnSecondary} onClick={handleCloseModal}>Cancel</button>
              <button 
                className={styles.btnPrimary} 
                onClick={handleSave}
                disabled={!formData.name || (!editingId && !formData.rule_id)}
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
