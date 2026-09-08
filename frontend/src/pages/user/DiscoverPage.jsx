import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../services/api';
import { getActiveKey } from '../../services/apiKeysService';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './DiscoverPage.module.css';

export default function DiscoverPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [discoverResult, setDiscoverResult] = useState(null);
  const [context, setContext] = useState(null);

  useEffect(() => {
    const storedContext = sessionStorage.getItem('extractionContext');
    if (storedContext) {
      try {
        setContext(JSON.parse(storedContext));
      } catch (e) {
        // invalid context
      }
    }
  }, []);

  const handleDiscover = async () => {
    if (!context || !context.provider || !context.model_id || !context.project_description) {
      setError("Invalid extraction context. Please go back to the Project phase.");
      return;
    }

    const keyObj = getActiveKey(context.provider);
    if (!keyObj) {
      setError(`No active key found for provider ${context.provider}. Please add one in the API Keys page.`);
      return;
    }

    // DiscoverRequest requires the full estimate + optimize results and the
    // active rule catalog (see backend/src/schemas.py DiscoverRequest) — not
    // just the provider/model used for extraction.
    const storedEstimateStr = sessionStorage.getItem('estimateResult');
    const storedOptimizeStr = sessionStorage.getItem('optimizeResult');
    if (!storedEstimateStr || !storedOptimizeStr) {
      setError("Please complete the Estimate and Optimize steps before discovering features.");
      return;
    }

    let estimateResult, optimizeResult;
    try {
      estimateResult = JSON.parse(storedEstimateStr);
      optimizeResult = JSON.parse(storedOptimizeStr);
    } catch (e) {
      setError("Stored estimate/optimize data is corrupted. Please redo the Estimate step.");
      return;
    }

    if (!estimateResult.pricing_snapshot || !estimateResult.pricing_snapshot.models || estimateResult.pricing_snapshot.models.length === 0) {
      setError("No priced models found in the estimate. Please redo the Estimate step.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // active_rules is the raw rule catalog (from /optimizer-rules), used by
      // the advisor to know which deterministic rules already exist.
      const activeRules = await apiFetch('/optimizer-rules');

      const payload = {
        project_description: context.project_description,
        document_summaries: context.document_summaries || [],
        phases: estimateResult.phases || [],
        pricing_snapshot: estimateResult.pricing_snapshot,
        estimate_result: estimateResult,
        optimize_result: optimizeResult,
        active_rules: activeRules
      };

      const response = await apiFetch('/discover-optimizations', {
        method: 'POST',
        headers: {
          'X-Provider-Key': keyObj.key
        },
        body: JSON.stringify(payload)
      });
      setDiscoverResult(response);
    } catch (err) {
      setError(err.message || 'Failed to discover features.');
    } finally {
      setLoading(false);
    }
  };

  if (!context) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <header className={layoutStyles.pageHeader}>
          <h2>Discover Next-Gen Features</h2>
        </header>
        <div className={styles.emptyState}>
          No project context found. Please start by defining a project.
          <br /><br />
          <button className={styles.btnPrimary} onClick={() => navigate('/project')}>
            Go to Project
          </button>
        </div>
      </div>
    );
  }

  // Actual /discover-optimizations response shape (see backend/src/schemas.py
  // DiscoverResponse): { ai_strategies, unquantified_opportunities }
  const aiStrategies = discoverResult?.ai_strategies || [];
  const unquantifiedOpportunities = discoverResult?.unquantified_opportunities || [];

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader}>
        <h2>Discover Next-Gen Features</h2>
        <p>Ask our AI architect to analyze your project context and recommend novel, cutting-edge optimizations beyond our standard ruleset.</p>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h3>AI-Assisted Feature Discovery</h3>
            <p>Using the context from your initial project description, the AI will search for advanced architectural patterns.</p>
          </div>

          <button
            className={styles.btnPrimary}
            onClick={handleDiscover}
            disabled={loading}
          >
            {loading ? 'Discovering...' : 'Discover Features'}
          </button>

          {discoverResult && (
            <div className={styles.discoveryList}>
              {aiStrategies.length === 0 && unquantifiedOpportunities.length === 0 ? (
                <p style={{ color: 'var(--text)' }}>No additional features discovered at this time.</p>
              ) : (
                <>
                  {aiStrategies.map((strategy, idx) => (
                    <div key={`strategy-${idx}`} className={styles.discoveryItem}>
                      <div className={styles.discoveryHeader}>
                        <span className={styles.featureName}>{strategy.name}</span>
                        <span className={`${styles.impactBadge} ${strategy.confidence === 'high' ? styles.impactBadgeHigh : ''}`}>
                          {strategy.confidence} confidence
                        </span>
                      </div>
                      <p className={styles.featureDesc}>{strategy.description}</p>
                      <p className={styles.featureDesc}>
                        Estimated savings: {(Number(strategy.estimated_savings.low_percent) * 100).toFixed(0)}%–
                        {(Number(strategy.estimated_savings.high_percent) * 100).toFixed(0)}%
                        (not included in official totals above)
                      </p>
                    </div>
                  ))}

                  {unquantifiedOpportunities.map((opp, idx) => (
                    <div key={`opp-${idx}`} className={styles.discoveryItem}>
                      <div className={styles.discoveryHeader}>
                        <span className={styles.featureName}>{opp.name}</span>
                      </div>
                      <p className={styles.featureDesc}>{opp.description}</p>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
