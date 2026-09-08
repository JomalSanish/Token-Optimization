import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../services/api';
import { getKeys, getActiveKey } from '../../services/apiKeysService';
import { PLAN_TIERS } from '../../config/planTiers';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './ProjectPage.module.css';

export default function ProjectPage() {
  const navigate = useNavigate();
  
  // State
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isExtracting, setIsExtracting] = useState(false);
  
  // Form State
  const [selectedProvider, setSelectedProvider] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [selectedTier, setSelectedTier] = useState('standard');
  const [projectDescription, setProjectDescription] = useState('');
  const [documents, setDocuments] = useState([]);

  // 1. Fetch active providers and intersect with available keys
  useEffect(() => {
    async function fetchProviders() {
      try {
        const activeProviders = await apiFetch('/providers');
        const availableKeys = getKeys();
        
        // Filter: only providers for which the user holds at least one key
        const usableProviders = activeProviders.filter(p => !!availableKeys[p.provider_id]);
        setProviders(usableProviders);
        
        if (usableProviders.length > 0) {
          setSelectedProvider(usableProviders[0].provider_id);
        }
      } catch (err) {
        setError(err.message || 'Failed to load providers');
      } finally {
        setLoading(false);
      }
    }
    fetchProviders();
  }, []);

  // 2. Fetch models when provider changes
  useEffect(() => {
    if (!selectedProvider) {
      setModels([]);
      setSelectedModel('');
      return;
    }

    async function fetchModels() {
      try {
        const providerModels = await apiFetch(`/providers/${selectedProvider}/models`);
        setModels(providerModels);
        
        // Initial selection handled via useMemo filtered models below
      } catch (err) {
        setError(err.message || 'Failed to load models');
      }
    }
    fetchModels();
  }, [selectedProvider]);

  // 3. Client-side filter models by Plan Tier
  const filteredModels = useMemo(() => {
    const allowedComplexities = PLAN_TIERS[selectedTier].allowedComplexityTiers;
    return models.filter(m => allowedComplexities.includes(m.complexity_tier));
  }, [models, selectedTier]);

  // Auto-select first available model if current selection becomes invalid
  useEffect(() => {
    if (filteredModels.length > 0) {
      if (!selectedModel || !filteredModels.find(m => m.model_id === selectedModel)) {
        setSelectedModel(filteredModels[0].model_id);
      }
    } else {
      setSelectedModel('');
    }
  }, [filteredModels, selectedModel]);

  // Handle file uploads (read as text for extraction)
  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files);
    
    const newDocs = await Promise.all(files.map(async file => {
      const text = await file.text();
      // Very basic page count estimation (1 page per 3000 chars roughly)
      const pageCount = Math.max(1, Math.ceil(text.length / 3000));
      return {
        filename: file.name,
        page_count: pageCount,
        summary: text
      };
    }));
    
    setDocuments(prev => [...prev, ...newDocs]);
    // Reset file input
    e.target.value = null;
  };

  const removeDocument = (index) => {
    setDocuments(prev => prev.filter((_, i) => i !== index));
  };

  // 4. Submit Extraction
  const handleExtract = async () => {
    if (!projectDescription.trim()) {
      setError("Project description is required.");
      return;
    }
    if (!selectedProvider || !selectedModel) {
      setError("Please select a provider and a model.");
      return;
    }

    const keyObj = getActiveKey(selectedProvider);
    if (!keyObj) {
      setError(`No active key found for provider ${selectedProvider}. Please add one in the API Keys page.`);
      return;
    }

    setIsExtracting(true);
    setError(null);

    const payload = {
      project_description: projectDescription,
      document_summaries: documents,
      provider: selectedProvider,
      model_id: selectedModel
    };

    try {
      const response = await apiFetch('/extract', {
        method: 'POST',
        headers: {
          'X-Provider-Key': keyObj.key
        },
        body: JSON.stringify(payload)
      });

      // Store in session storage per requirements
      sessionStorage.setItem('extractResult', JSON.stringify(response));
      sessionStorage.setItem('extractionContext', JSON.stringify({
        project_description: projectDescription,
        document_summaries: documents,
        provider: selectedProvider,
        model_id: selectedModel
      }));

      // Navigate to Estimate Phase 13 (Placeholder for now)
      navigate('/estimate');

    } catch (err) {
      setError(err.message || 'Extraction failed.');
    } finally {
      setIsExtracting(false);
    }
  };

  if (loading) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Loading project context...</div>
      </div>
    );
  }

  if (providers.length === 0) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <header className={layoutStyles.pageHeader}>
          <h2>Project Context</h2>
        </header>
        <div className={styles.error}>
          No API keys available. Please go to the API Keys page to add a provider key before starting an extraction.
        </div>
        <button className={styles.btnPrimary} onClick={() => navigate('/keys')}>
          Go to API Keys
        </button>
      </div>
    );
  }

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader}>
        <h2>Project Context</h2>
        <p>Define your project parameters, select a plan tier, and provide requirements to extract architectural phases.</p>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        {/* Model Selection Card */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h3>Extraction Model</h3>
            <p>Select the LLM that will analyze your requirements.</p>
          </div>

          <div className={styles.formGroup}>
            <label>Provider</label>
            <select 
              className={styles.select} 
              value={selectedProvider} 
              onChange={e => setSelectedProvider(e.target.value)}
            >
              {providers.map(p => (
                <option key={p.provider_id} value={p.provider_id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.formGroup}>
            <label>Plan Tier (Client-side Filter)</label>
            <select 
              className={styles.select}
              value={selectedTier}
              onChange={e => setSelectedTier(e.target.value)}
            >
              {Object.entries(PLAN_TIERS).map(([key, config]) => (
                <option key={key} value={key}>{config.label}</option>
              ))}
            </select>
          </div>

          <div className={styles.formGroup}>
            <label>Model</label>
            <select 
              className={styles.select}
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              disabled={filteredModels.length === 0}
            >
              {filteredModels.map(m => (
                <option key={m.model_id} value={m.model_id}>
                  {m.display_name} ({m.complexity_tier})
                </option>
              ))}
            </select>
            {filteredModels.length === 0 && (
              <small style={{ color: 'var(--text)' }}>No models available for this provider in the selected tier.</small>
            )}
          </div>
        </div>

        {/* Context Card */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h3>Requirements</h3>
            <p>Provide a textual description or upload documents.</p>
          </div>

          <div className={styles.formGroup}>
            <label>Project Description</label>
            <textarea 
              className={styles.textarea} 
              placeholder="Describe the system architecture, goals, and constraints..."
              value={projectDescription}
              onChange={e => setProjectDescription(e.target.value)}
            />
          </div>

          <div className={styles.formGroup}>
            <label>Supplemental Documents</label>
            <input 
              type="file" 
              multiple 
              onChange={handleFileChange}
              className={styles.input}
              accept=".txt,.md,.json,.csv"
            />
            {documents.length > 0 && (
              <div className={styles.fileList}>
                {documents.map((doc, idx) => (
                  <div key={idx} className={styles.fileItem}>
                    <span>{doc.filename} ({doc.page_count} pages)</span>
                    <button type="button" onClick={() => removeDocument(idx)} style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <button 
          className={styles.btnPrimary} 
          onClick={handleExtract}
          disabled={isExtracting || !projectDescription.trim() || !selectedModel}
        >
          {isExtracting ? 'Extracting Phases...' : 'Start Extraction'}
        </button>
      </div>
    </div>
  );
}
