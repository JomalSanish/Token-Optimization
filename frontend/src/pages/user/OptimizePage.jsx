import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../services/api';
import layoutStyles from '../../layouts/Layout.module.css';
import styles from './OptimizePage.module.css';

export default function OptimizePage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [optimizeResult, setOptimizeResult] = useState(null);
  const [originalTotalCost, setOriginalTotalCost] = useState(0);
  const [ruleCatalog, setRuleCatalog] = useState({});

  useEffect(() => {
    async function runOptimization() {
      const storedEstimateStr = sessionStorage.getItem('estimateResult');
      if (!storedEstimateStr) {
        setLoading(false);
        return;
      }

      try {
        const estimateResult = JSON.parse(storedEstimateStr);
        setOriginalTotalCost(estimateResult.project_total_cost || 0);

        // Fetch the rule catalog so triggered rules (which only carry a
        // rule_id from the backend) can show a human-readable name/description.
        try {
          const rules = await apiFetch('/optimizer-rules');
          setRuleCatalog(Object.fromEntries(rules.map(r => [r.rule_id, r])));
        } catch (catalogErr) {
          // Non-fatal: fall back to showing the raw rule_id.
        }

        // POST /optimize — the request body must contain pricing_snapshot,
        // phase_results, and phases; estimateResult carries all three
        // (phases was bundled in on the Estimate page).
        const response = await apiFetch('/optimize', {
          method: 'POST',
          body: JSON.stringify(estimateResult)
        });

        sessionStorage.setItem('optimizeResult', JSON.stringify(response));
        setOptimizeResult(response);
      } catch (err) {
        setError(err.message || 'Optimization failed.');
      } finally {
        setLoading(false);
      }
    }

    runOptimization();
  }, []);

  const formatCurrency = (val) => {
    if (val === undefined || val === null) return '$0.00';
    return `$${Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatPercent = (val) => {
    if (val === undefined || val === null) return '0%';
    return `${(Number(val) * 100).toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <div>Running optimization rules...</div>
      </div>
    );
  }

  if (!optimizeResult) {
    return (
      <div className={layoutStyles.contentWrapper}>
        <header className={layoutStyles.pageHeader}>
          <h2>Optimization Results</h2>
        </header>
        <div className={styles.emptyState}>
          No estimate found. Please complete the Estimate phase first.
          <br /><br />
          <button className={styles.btnPrimary} onClick={() => navigate('/estimate')}>
            Go to Estimate
          </button>
        </div>
      </div>
    );
  }

  // Actual /optimize response shape (see backend/src/schemas.py OptimizeResponse):
  // { phase_optimizations, total_savings_amount, total_savings_percentage, advisory_recommendations }
  const {
    phase_optimizations = [],
    total_savings_amount,
    total_savings_percentage,
    advisory_recommendations = []
  } = optimizeResult;

  const optimizedTotalCost = originalTotalCost - Number(total_savings_amount || 0);

  return (
    <div className={layoutStyles.contentWrapper}>
      <header className={layoutStyles.pageHeader}>
        <h2>Optimization Results</h2>
        <p>Review the applied architectural rules and see your projected savings.</p>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.container}>

        <div className={styles.summaryCard}>
          <div className={styles.summaryGrid}>
            <div className={styles.summaryStat}>
              <span className={styles.summaryLabel}>Original Cost</span>
              <span className={styles.summaryValue}>{formatCurrency(originalTotalCost)}</span>
            </div>
            <div className={styles.summaryStat}>
              <span className={styles.summaryLabel}>Optimized Cost</span>
              <span className={`${styles.summaryValue} ${styles.valueGreen}`}>
                {formatCurrency(optimizedTotalCost)}
              </span>
            </div>
            <div className={styles.summaryStat}>
              <span className={styles.summaryLabel}>Total Savings</span>
              <span className={`${styles.summaryValue} ${styles.valueGreen}`}>
                {formatCurrency(total_savings_amount)} ({formatPercent(total_savings_percentage)})
              </span>
            </div>
          </div>
        </div>

        <button className={styles.btnPrimary} onClick={() => navigate('/discover')}>
          Continue to Discover Next-Gen Features →
        </button>

        {phase_optimizations.map((phaseData, idx) => {
          const rules = phaseData.triggered_rules || [];
          const phaseAdvisory = advisory_recommendations.filter(a => a.phase === phaseData.phase);

          return (
            <div key={idx} className={styles.phaseCard}>
              <div className={styles.phaseHeader}>
                <h3>{phaseData.phase}</h3>
              </div>

              {rules.length === 0 && phaseAdvisory.length === 0 ? (
                <p style={{ color: 'var(--text)' }}>No optimization rules triggered for this phase.</p>
              ) : (
                <>
                  {rules.length > 0 && (
                    <div className={styles.rulesSection}>
                      <h4>Applied Optimizations</h4>
                      <div className={styles.ruleList}>
                        {rules.map((rule, rIdx) => {
                          const meta = ruleCatalog[rule.rule_id];
                          return (
                            <div key={rIdx} className={styles.ruleItem}>
                              <div className={styles.ruleHeader}>
                                <span className={styles.ruleName}>{meta?.name || rule.rule_id}</span>
                                <span className={styles.ruleSavings}>
                                  -{formatPercent(rule.reduction_applied)} ({rule.pool})
                                </span>
                              </div>
                              {meta?.description && <p className={styles.ruleDesc}>{meta.description}</p>}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {phaseAdvisory.length > 0 && (
                    <div className={styles.rulesSection}>
                      <h4>Advisory Recommendations</h4>
                      <div className={styles.ruleList}>
                        {phaseAdvisory.map((rec, rIdx) => (
                          <div key={rIdx} className={styles.ruleItem}>
                            <div className={styles.ruleHeader}>
                              <span className={styles.ruleName}>{rec.category}</span>
                              <span className={styles.advisoryBadge}>Advisory</span>
                            </div>
                            <p className={styles.ruleDesc}>{rec.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              <div style={{
                marginTop: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '14px',
                color: 'var(--text)'
              }}>
                <span>Optimized phase cost: {formatCurrency(phaseData.optimized_phase_cost)}</span>
                <span>Savings: {formatCurrency(phaseData.savings_amount)} ({formatPercent(phaseData.savings_percentage)})</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
