import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../services/api';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './EstimatePage.module.css';

export default function EstimatePage() {
  const navigate = useNavigate();

  const [phases, setPhases] = useState([]);
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [suggestingFor, setSuggestingFor] = useState(null); // track which phase is loading a suggestion

  // AMS Config state
  const [amsConfig, setAmsConfig] = useState({
    runs_per_year: 12,
    annual_growth_rate: 0.1,
    horizon_years: 3
  });

  // Load models and initial phase data
  useEffect(() => {
    async function initData() {
      try {
        // 1. Fetch all models from the catalog
        const catalogModels = await apiFetch('/models');
        setModels(catalogModels);

        // 2. Load extraction result from session storage
        const storedExtract = sessionStorage.getItem('extractResult');
        let initialPhases = [];

        if (storedExtract) {
          try {
            const extractData = JSON.parse(storedExtract);
            if (extractData.phases) {
              // Convert extracted phases to editable phase state
              initialPhases = extractData.phases.map(p => ({
                phase: p.phase,
                agent_role: p.agent_role || 'Agent',
                base_input_tokens: p.base_input_tokens || 1000,
                context_input_tokens: p.context_input_tokens || 0,
                cacheable_fraction: parseFloat(p.cacheable_fraction) || 0,
                tool_call_tokens: p.tool_call_tokens || 0,
                output_tokens: p.output_tokens || 500,
                estimated_calls: p.estimated_calls || 1,
                assigned_model_id: '',
                assigned_provider: '', // Stored as composite or we can deduce it from the model
                source: p.source || 'llm_extracted',
                id: crypto.randomUUID() // local ID for rendering
              }));
            }
          } catch (e) {
            console.error("Failed to parse stored extract result", e);
          }
        }

        // If no stored phases, add a default manual one
        if (initialPhases.length === 0) {
          initialPhases.push({
            phase: 'manual-phase',
            agent_role: 'Agent',
            base_input_tokens: 1000,
            context_input_tokens: 0,
            cacheable_fraction: 0,
            tool_call_tokens: 0,
            output_tokens: 500,
            estimated_calls: 1,
            assigned_model_id: '',
            assigned_provider: '',
            source: 'manual',
            id: crypto.randomUUID()
          });
        }
        
        // Auto-assign the first available model as default if exists
        if (catalogModels.length > 0) {
          const defaultModel = catalogModels[0];
          initialPhases = initialPhases.map(p => ({
            ...p,
            assigned_model_id: defaultModel.model_id,
            assigned_provider: defaultModel.provider
          }));
        }

        setPhases(initialPhases);
      } catch (err) {
        setError(err.message || 'Failed to load catalog models');
      } finally {
        setLoading(false);
      }
    }
    initData();
  }, []);

  // Group models by provider for the <select> optgroup rendering
  const groupedModels = useMemo(() => {
    const groups = {};
    models.forEach(m => {
      if (!groups[m.provider]) groups[m.provider] = [];
      groups[m.provider].push(m);
    });
    return groups;
  }, [models]);

  const handlePhaseChange = (id, field, value) => {
    setPhases(prev => prev.map(p => {
      if (p.id === id) {
        const updated = { ...p, [field]: value };
        // If the model changed, we need to update the provider too
        if (field === 'assigned_model_id') {
          const selectedModel = models.find(m => m.model_id === value);
          if (selectedModel) {
            updated.assigned_provider = selectedModel.provider;
          }
        }
        return updated;
      }
      return p;
    }));
  };

  const addPhase = () => {
    const defaultModel = models.length > 0 ? models[0] : null;
    
    setPhases(prev => [...prev, {
      phase: `phase-${prev.length + 1}`,
      agent_role: 'Agent',
      base_input_tokens: 1000,
      context_input_tokens: 0,
      cacheable_fraction: 0,
      tool_call_tokens: 0,
      output_tokens: 500,
      estimated_calls: 1,
      assigned_model_id: defaultModel ? defaultModel.model_id : '',
      assigned_provider: defaultModel ? defaultModel.provider : '',
      source: 'manual',
      id: crypto.randomUUID()
    }]);
  };

  const removePhase = (id) => {
    if (phases.length <= 1) return; // Keep at least one
    setPhases(prev => prev.filter(p => p.id !== id));
  };

  const handleSuggestModel = async (phaseRow) => {
    // Only suggest if we know the provider we want to ask, or just use the extraction context's provider.
    // US5: "Suggest model" button per row that calls POST /route-model {phase_id, provider_id}
    // We'll use the provider currently assigned to that row, or the first provider if none.
    
    let targetProvider = phaseRow.assigned_provider;
    if (!targetProvider && models.length > 0) {
      targetProvider = models[0].provider;
    }
    
    if (!targetProvider) {
      setError("No provider available for suggestion routing.");
      return;
    }

    setSuggestingFor(phaseRow.id);
    setError(null);

    try {
      const resp = await apiFetch('/route-model', {
        method: 'POST',
        body: JSON.stringify({
          phase_id: phaseRow.phase,
          provider_id: targetProvider
        })
      });

      if (resp.model_id) {
        // Update the row with the suggested model
        setPhases(prev => prev.map(p => {
          if (p.id === phaseRow.id) {
            return {
              ...p,
              assigned_model_id: resp.model_id,
              assigned_provider: targetProvider
            };
          }
          return p;
        }));
      } else {
        // match_type: "none"
        setError(`No suitable model found from provider ${targetProvider} for phase ${phaseRow.phase}.`);
      }
    } catch (err) {
      setError(`Routing failed: ${err.message}`);
    } finally {
      setSuggestingFor(null);
    }
  };

  const handleSubmitEstimate = async () => {
    setIsSubmitting(true);
    setError(null);

    // Prepare payload
    const payload = {
      phases: phases.map(p => ({
        phase: p.phase,
        agent_role: p.agent_role,
        base_input_tokens: parseInt(p.base_input_tokens) || 0,
        context_input_tokens: parseInt(p.context_input_tokens) || 0,
        cacheable_fraction: parseFloat(p.cacheable_fraction) || 0,
        tool_call_tokens: parseInt(p.tool_call_tokens) || 0,
        output_tokens: parseInt(p.output_tokens) || 0,
        estimated_calls: parseInt(p.estimated_calls) || 1,
        assigned_model_id: p.assigned_model_id,
        assigned_provider: p.assigned_provider,
        source: p.source
      })),
      ams_config: {
        runs_per_year: parseInt(amsConfig.runs_per_year) || 1,
        annual_growth_rate: parseFloat(amsConfig.annual_growth_rate) || 0,
        horizon_years: parseInt(amsConfig.horizon_years) || 1
      }
    };

    try {
      const response = await apiFetch('/estimate', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      // POST /optimize requires `phases` (the assigned-model phase configs) in
      // addition to `pricing_snapshot` and `phase_results` — the /estimate
      // response alone doesn't include `phases`, so it's bundled in here too.
      sessionStorage.setItem('estimateResult', JSON.stringify({ ...response, phases: payload.phases }));
      navigate('/optimize');
    } catch (err) {
      setError(err.message || 'Failed to calculate estimate');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Loading phase and catalog data...</div>
      </div>
    );
  }

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader}>
        <h2>Cost Estimate</h2>
        <p>Review and adjust the extracted phases. Assign models from any provider to optimize your architecture's baseline cost before applying rules.</p>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        
        {/* Phase Table */}
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Phase ID</th>
                <th>Role</th>
                <th>Base In</th>
                <th>Ctx In</th>
                <th>Cache %</th>
                <th>Tool Out</th>
                <th>Output</th>
                <th>Calls</th>
                <th>Assigned Model</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {phases.map(phase => (
                <tr key={phase.id}>
                  <td>
                    <input 
                      className={`${styles.input} ${styles.phaseInput}`}
                      value={phase.phase}
                      placeholder="Phase ID"
                      onChange={e => handlePhaseChange(phase.id, 'phase', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      className={`${styles.input} ${styles.roleInput}`}
                      value={phase.agent_role}
                      placeholder="Agent role"
                      onChange={e => handlePhaseChange(phase.id, 'agent_role', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="number"
                      className={`${styles.input} ${styles.inputToken}`}
                      value={phase.base_input_tokens}
                      onChange={e => handlePhaseChange(phase.id, 'base_input_tokens', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="number"
                      className={`${styles.input} ${styles.inputToken}`}
                      value={phase.context_input_tokens}
                      onChange={e => handlePhaseChange(phase.id, 'context_input_tokens', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="number"
                      step="0.1"
                      min="0"
                      max="1"
                      className={`${styles.input} ${styles.inputNum}`}
                      value={phase.cacheable_fraction}
                      onChange={e => handlePhaseChange(phase.id, 'cacheable_fraction', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="number"
                      className={`${styles.input} ${styles.inputToken}`}
                      value={phase.tool_call_tokens}
                      onChange={e => handlePhaseChange(phase.id, 'tool_call_tokens', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="number"
                      className={`${styles.input} ${styles.inputToken}`}
                      value={phase.output_tokens}
                      onChange={e => handlePhaseChange(phase.id, 'output_tokens', e.target.value)}
                    />
                  </td>
                  <td>
                    <input 
                      type="number"
                      className={`${styles.input} ${styles.inputNum}`}
                      value={phase.estimated_calls}
                      onChange={e => handlePhaseChange(phase.id, 'estimated_calls', e.target.value)}
                    />
                  </td>
                  <td>
                    <div className={styles.modelSelectGroup}>
                      <select 
                        className={styles.select}
                        value={phase.assigned_model_id}
                        onChange={e => handlePhaseChange(phase.id, 'assigned_model_id', e.target.value)}
                      >
                        {Object.entries(groupedModels).map(([provider, providerModels]) => (
                          <optgroup key={provider} label={provider}>
                            {providerModels.map(m => (
                              <option key={m.model_id} value={m.model_id}>
                                {m.display_name}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                      <button 
                        className={styles.suggestBtn}
                        onClick={() => handleSuggestModel(phase)}
                        disabled={suggestingFor === phase.id}
                      >
                        {suggestingFor === phase.id ? 'Routing...' : 'Suggest best fit'}
                      </button>
                    </div>
                  </td>
                  <td>
                    <button 
                      onClick={() => removePhase(phase.id)}
                      style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer' }}
                      disabled={phases.length <= 1}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          
          <div style={{ padding: '16px', borderTop: '1px solid var(--border)' }}>
            <button 
              className={styles.suggestBtn} 
              style={{ background: 'transparent', color: 'var(--text-h)' }}
              onClick={addPhase}
            >
              + Add Phase Manually
            </button>
          </div>
        </div>

        {/* AMS Config */}
        <div className={styles.amsCard}>
          <div className={styles.amsGroup}>
            <label>Runs per Year</label>
            <input 
              type="number"
              className={styles.input}
              value={amsConfig.runs_per_year}
              onChange={e => setAmsConfig(prev => ({...prev, runs_per_year: e.target.value}))}
            />
          </div>
          <div className={styles.amsGroup}>
            <label>Annual Growth Rate</label>
            <input 
              type="number"
              step="0.01"
              className={styles.input}
              value={amsConfig.annual_growth_rate}
              onChange={e => setAmsConfig(prev => ({...prev, annual_growth_rate: e.target.value}))}
            />
          </div>
          <div className={styles.amsGroup}>
            <label>Horizon (Years)</label>
            <input 
              type="number"
              className={styles.input}
              value={amsConfig.horizon_years}
              onChange={e => setAmsConfig(prev => ({...prev, horizon_years: e.target.value}))}
            />
          </div>
        </div>

        <button 
          className={styles.btnPrimary} 
          onClick={handleSubmitEstimate}
          disabled={isSubmitting || phases.some(p => !p.assigned_model_id)}
        >
          {isSubmitting ? 'Calculating...' : 'Calculate Estimate'}
        </button>

      </div>
    </div>
  );
}
