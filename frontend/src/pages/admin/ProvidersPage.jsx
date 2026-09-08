import React, { useState, useEffect } from 'react';
import { adminApiFetch } from '../../services/api';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './Admin.module.css';

const NATIVE_KEYS = ['openai', 'anthropic', 'google'];

const DEFAULT_PROVIDER = {
  provider_id: '',
  display_name: '',
  active: true,
  implementation_type: 'openai_compatible',
  base_url: '',
  native_key: '',
  adapter_template: {
    request_url: '',
    http_method: 'POST',
    header_template: '{"Authorization": "Bearer {api_key}"}',
    body_template: '{"model": "{model_id}", "messages": [{"role": "user", "content": "{user_prompt}"}]}',
    response_text_path: 'choices[0].message.content',
    error_message_path: 'error.message'
  }
};

export default function ProvidersPage() {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState(DEFAULT_PROVIDER);

  useEffect(() => {
    fetchProviders();
  }, []);

  const fetchProviders = async () => {
    try {
      setLoading(true);
      const data = await adminApiFetch('/admin/providers');
      setProviders(data);
    } catch (err) {
      setError(err.message || 'Failed to load providers');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = (provider = null) => {
    setError(null);
    if (provider) {
      setEditingId(provider.provider_id);
      setFormData({
        provider_id: provider.provider_id,
        display_name: provider.display_name,
        active: provider.active,
        implementation_type: provider.implementation_type,
        base_url: provider.base_url || '',
        native_key: provider.native_key || '',
        adapter_template: provider.adapter_template ? {
          ...provider.adapter_template,
          header_template: JSON.stringify(provider.adapter_template.header_template, null, 2),
          body_template: JSON.stringify(provider.adapter_template.body_template, null, 2)
        } : DEFAULT_PROVIDER.adapter_template
      });
    } else {
      setEditingId(null);
      setFormData(DEFAULT_PROVIDER);
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

  const handleAdapterChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      adapter_template: {
        ...prev.adapter_template,
        [field]: value
      }
    }));
  };

  const handleToggleStatus = async (provider) => {
    try {
      await adminApiFetch(`/admin/providers/${provider.provider_id}`, {
        method: 'PATCH',
        body: JSON.stringify({ active: !provider.active })
      });
      fetchProviders();
    } catch (err) {
      setError(err.message || 'Failed to toggle status');
    }
  };

  const handleSave = async () => {
    setError(null);
    try {
      // Build payload based on implementation type
      const payload = {
        display_name: formData.display_name,
        active: formData.active,
        implementation_type: formData.implementation_type
      };

      if (!editingId) {
        payload.provider_id = formData.provider_id;
      }

      if (formData.implementation_type === 'native') {
        payload.native_key = formData.native_key;
      } else if (formData.implementation_type === 'openai_compatible') {
        payload.base_url = formData.base_url;
      } else if (formData.implementation_type === 'template') {
        let headerParsed = {};
        let bodyParsed = {};
        try {
          headerParsed = JSON.parse(formData.adapter_template.header_template);
          bodyParsed = JSON.parse(formData.adapter_template.body_template);
        } catch (e) {
          throw new Error("Invalid JSON in Header or Body Template");
        }

        payload.adapter_template = {
          request_url: formData.adapter_template.request_url,
          http_method: formData.adapter_template.http_method,
          header_template: headerParsed,
          body_template: bodyParsed,
          response_text_path: formData.adapter_template.response_text_path,
          error_message_path: formData.adapter_template.error_message_path
        };
      }

      const method = editingId ? 'PATCH' : 'POST';
      const url = editingId ? `/admin/providers/${editingId}` : '/admin/providers';

      await adminApiFetch(url, {
        method,
        body: JSON.stringify(payload)
      });

      handleCloseModal();
      fetchProviders();
    } catch (err) {
      setError(err.message || 'Failed to save provider');
    }
  };

  if (loading && providers.length === 0) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Loading providers...</div>
      </div>
    );
  }

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Providers</h2>
          <p>Manage the list of available LLM providers and their backend integrations.</p>
        </div>
        <button className={styles.btnPrimary} onClick={() => handleOpenModal()}>
          + Add Provider
        </button>
      </header>

      {error && !isModalOpen && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Display Name</th>
                <th>Implementation</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {providers.map(p => (
                <tr key={p.provider_id}>
                  <td><code>{p.provider_id}</code></td>
                  <td>{p.display_name}</td>
                  <td>{p.implementation_type}</td>
                  <td>
                    <span className={`${styles.statusBadge} ${p.active ? styles.statusActive : styles.statusInactive}`}>
                      {p.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => handleOpenModal(p)}>Edit</button>
                    <button 
                      className={styles.actionBtn} 
                      onClick={() => handleToggleStatus(p)}
                    >
                      {p.active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
              {providers.length === 0 && (
                <tr>
                  <td colSpan="5" style={{ textAlign: 'center' }}>No providers found.</td>
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
              <h3>{editingId ? 'Edit Provider' : 'Add Provider'}</h3>
              <button 
                onClick={handleCloseModal}
                style={{ background: 'transparent', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text)' }}
              >✕</button>
            </div>
            
            <div className={styles.modalBody}>
              {error && <div className={styles.error}>{error}</div>}

              {!editingId && (
                <div className={styles.formGroup}>
                  <label>Provider ID</label>
                  <input 
                    className={styles.input}
                    value={formData.provider_id}
                    onChange={e => handleChange('provider_id', e.target.value)}
                    placeholder="e.g. custom_oai"
                  />
                </div>
              )}

              <div className={styles.formGroup}>
                <label>Display Name</label>
                <input 
                  className={styles.input}
                  value={formData.display_name}
                  onChange={e => handleChange('display_name', e.target.value)}
                  placeholder="e.g. Custom OpenAI"
                />
              </div>

              <div className={styles.formGroup}>
                <label>Implementation Type</label>
                <select 
                  className={styles.select}
                  value={formData.implementation_type}
                  onChange={e => handleChange('implementation_type', e.target.value)}
                >
                  <option value="openai_compatible">OpenAI Compatible (Recommended)</option>
                  <option value="native">Native Client</option>
                  <option value="template">Custom Template</option>
                </select>
              </div>

              {formData.implementation_type === 'native' && (
                <div className={styles.formGroup}>
                  <label>Native Key</label>
                  <select 
                    className={styles.select}
                    value={formData.native_key}
                    onChange={e => handleChange('native_key', e.target.value)}
                  >
                    <option value="">Select a native key...</option>
                    {NATIVE_KEYS.map(key => <option key={key} value={key}>{key}</option>)}
                  </select>
                </div>
              )}

              {formData.implementation_type === 'openai_compatible' && (
                <div className={styles.formGroup}>
                  <label>Base URL</label>
                  <input 
                    className={styles.input}
                    value={formData.base_url}
                    onChange={e => handleChange('base_url', e.target.value)}
                    placeholder="https://api.example.com/v1"
                  />
                </div>
              )}

              {formData.implementation_type === 'template' && (
                <>
                  <div className={styles.formGroup}>
                    <label>Request URL</label>
                    <input 
                      className={styles.input}
                      value={formData.adapter_template.request_url}
                      onChange={e => handleAdapterChange('request_url', e.target.value)}
                      placeholder="https://api.example.com/completion"
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>HTTP Method</label>
                    <select 
                      className={styles.select}
                      value={formData.adapter_template.http_method}
                      onChange={e => handleAdapterChange('http_method', e.target.value)}
                    >
                      <option value="POST">POST</option>
                      <option value="GET">GET</option>
                      <option value="PUT">PUT</option>
                    </select>
                  </div>
                  <div className={styles.formGroup}>
                    <label>Header Template (JSON dict)</label>
                    <textarea 
                      className={styles.textarea}
                      value={formData.adapter_template.header_template}
                      onChange={e => handleAdapterChange('header_template', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Body Template (JSON structure)</label>
                    <textarea 
                      className={styles.textarea}
                      value={formData.adapter_template.body_template}
                      onChange={e => handleAdapterChange('body_template', e.target.value)}
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Response Text Path (dot notation)</label>
                    <input 
                      className={styles.input}
                      value={formData.adapter_template.response_text_path}
                      onChange={e => handleAdapterChange('response_text_path', e.target.value)}
                      placeholder="choices[0].message.content"
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Error Message Path (dot notation)</label>
                    <input 
                      className={styles.input}
                      value={formData.adapter_template.error_message_path}
                      onChange={e => handleAdapterChange('error_message_path', e.target.value)}
                      placeholder="error.message"
                    />
                  </div>
                </>
              )}

              <div className={styles.formGroup} style={{ flexDirection: 'row', alignItems: 'center' }}>
                <input 
                  type="checkbox" 
                  id="activeCheck"
                  checked={formData.active}
                  onChange={e => handleChange('active', e.target.checked)}
                  style={{ width: '16px', height: '16px' }}
                />
                <label htmlFor="activeCheck" style={{ margin: 0, cursor: 'pointer' }}>Active</label>
              </div>

            </div>
            <div className={styles.modalFooter}>
              <button className={styles.btnSecondary} onClick={handleCloseModal}>Cancel</button>
              <button 
                className={styles.btnPrimary} 
                onClick={handleSave}
                disabled={!formData.display_name || (formData.implementation_type === 'native' && !formData.native_key)}
              >
                Save Provider
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
