import React, { useState, useEffect } from 'react';
import { adminApiFetch } from '../../services/api';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './Admin.module.css';

export default function PricingPage() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [pricingData, setPricingData] = useState({
    input_per_1m: 0,
    output_per_1m: 0,
    cached_input_per_1m: 0,
    batch_input_per_1m: 0,
    batch_output_per_1m: 0
  });

  // History state
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyData, setHistoryData] = useState([]);

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      setLoading(true);
      const data = await adminApiFetch('/admin/models');
      setModels(data);
    } catch (err) {
      setError(err.message || 'Failed to load models');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenEdit = (model) => {
    setError(null);
    setEditingModel(model);
    setPricingData({
      input_per_1m: model.pricing?.input_per_1m || 0,
      output_per_1m: model.pricing?.output_per_1m || 0,
      cached_input_per_1m: model.pricing?.cached_input_per_1m || 0,
      batch_input_per_1m: model.pricing?.batch_input_per_1m || 0,
      batch_output_per_1m: model.pricing?.batch_output_per_1m || 0
    });
    setIsModalOpen(true);
  };

  const handleCloseEdit = () => {
    setIsModalOpen(false);
    setEditingModel(null);
    setError(null);
  };

  const handlePricingChange = (field, value) => {
    setPricingData(prev => ({
      ...prev,
      [field]: parseFloat(value) || 0
    }));
  };

  const handleSave = async () => {
    setError(null);
    try {
      await adminApiFetch(`/admin/models/${editingModel.model_id}?provider=${editingModel.provider}`, {
        method: 'PATCH',
        body: JSON.stringify(pricingData)
      });
      handleCloseEdit();
      fetchModels();
    } catch (err) {
      setError(err.message || 'Failed to update pricing');
    }
  };

  const handleViewHistory = async (model) => {
    try {
      const history = await adminApiFetch(`/admin/models/${model.model_id}/pricing-history`);
      setHistoryData(history);
      setHistoryOpen(true);
    } catch (err) {
      setError(err.message || 'Failed to fetch pricing history');
    }
  };

  if (loading && models.length === 0) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Loading pricing data...</div>
      </div>
    );
  }

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader}>
        <h2>Pricing Management</h2>
        <p>Update input and output token costs per 1M tokens across all registered models.</p>
      </header>

      {error && !isModalOpen && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Provider</th>
                <th>Model ID</th>
                <th>Input / 1M</th>
                <th>Output / 1M</th>
                <th>Cached Input / 1M</th>
                <th>Batch In / 1M</th>
                <th>Batch Out / 1M</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.map(m => (
                <tr key={`${m.provider}-${m.model_id}`}>
                  <td>{m.provider}</td>
                  <td><code>{m.model_id}</code></td>
                  <td>${Number(m.pricing?.input_per_1m || 0).toFixed(4)}</td>
                  <td>${Number(m.pricing?.output_per_1m || 0).toFixed(4)}</td>
                  <td>${Number(m.pricing?.cached_input_per_1m || 0).toFixed(4)}</td>
                  <td>${Number(m.pricing?.batch_input_per_1m || 0).toFixed(4)}</td>
                  <td>${Number(m.pricing?.batch_output_per_1m || 0).toFixed(4)}</td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => handleOpenEdit(m)}>Edit</button>
                    <button className={styles.actionBtn} onClick={() => handleViewHistory(m)}>History</button>
                  </td>
                </tr>
              ))}
              {models.length === 0 && (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center' }}>No models found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {isModalOpen && editingModel && (
        <div className={styles.modalOverlay}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h3>Update Pricing: {editingModel.model_id}</h3>
              <button 
                onClick={handleCloseEdit}
                style={{ background: 'transparent', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text)' }}
              >✕</button>
            </div>
            
            <div className={styles.modalBody}>
              {error && <div className={styles.error}>{error}</div>}

              <div className={styles.formGroup}>
                <label>Input Price (per 1M tokens)</label>
                <input 
                  type="number"
                  step="0.0001"
                  className={styles.input}
                  value={pricingData.input_per_1m}
                  onChange={e => handlePricingChange('input_per_1m', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Output Price (per 1M tokens)</label>
                <input 
                  type="number"
                  step="0.0001"
                  className={styles.input}
                  value={pricingData.output_per_1m}
                  onChange={e => handlePricingChange('output_per_1m', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Cached Input Price (per 1M tokens)</label>
                <input 
                  type="number"
                  step="0.0001"
                  className={styles.input}
                  value={pricingData.cached_input_per_1m}
                  onChange={e => handlePricingChange('cached_input_per_1m', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Batch Input Price (per 1M tokens)</label>
                <input 
                  type="number"
                  step="0.0001"
                  className={styles.input}
                  value={pricingData.batch_input_per_1m}
                  onChange={e => handlePricingChange('batch_input_per_1m', e.target.value)}
                />
              </div>

              <div className={styles.formGroup}>
                <label>Batch Output Price (per 1M tokens)</label>
                <input 
                  type="number"
                  step="0.0001"
                  className={styles.input}
                  value={pricingData.batch_output_per_1m}
                  onChange={e => handlePricingChange('batch_output_per_1m', e.target.value)}
                />
              </div>
            </div>
            
            <div className={styles.modalFooter}>
              <button className={styles.btnSecondary} onClick={handleCloseEdit}>Cancel</button>
              <button className={styles.btnPrimary} onClick={handleSave}>Save Pricing</button>
            </div>
          </div>
        </div>
      )}

      {historyOpen && (
        <div className={styles.modalOverlay}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h3>Pricing History</h3>
              <button 
                onClick={() => setHistoryOpen(false)}
                style={{ background: 'transparent', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text)' }}
              >✕</button>
            </div>
            
            <div className={styles.modalBody}>
              {historyData.length === 0 ? (
                <p>No history found.</p>
              ) : (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Changed At</th>
                      <th>Changed By</th>
                      <th>Previous Input</th>
                      <th>New Input</th>
                      <th>Previous Output</th>
                      <th>New Output</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historyData.map(h => (
                      <tr key={h.pricing_version}>
                        <td>v{h.pricing_version}</td>
                        <td>{new Date(h.changed_at).toLocaleString()}</td>
                        <td>{h.changed_by}</td>
                        <td>${Number(h.previous_pricing?.input_per_1m).toFixed(4)}</td>
                        <td>${Number(h.new_pricing?.input_per_1m).toFixed(4)}</td>
                        <td>${Number(h.previous_pricing?.output_per_1m).toFixed(4)}</td>
                        <td>${Number(h.new_pricing?.output_per_1m).toFixed(4)}</td>
                        <td>{h.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
