import { apiKeysService } from './services/api_keys.js';

// Application State
const state = {
    activeTab: 'dashboard',
    sharedSecret: 'test_shared_app_secret_123', // Defaults to match seed configuration
    backendUrl: 'http://127.0.0.1:8000',
    models: [],
    rules: [],
    providers: [],
    phases: [],
    
    // Transient session configurations
    project: {
        description: '',
        documentSummaries: [],
        provider: 'openai',
        modelId: 'gpt-4o',
        phasesConfig: [],
        estimateResult: null,
        optimizeResult: null,
        discoverResult: null
    }
};

// Eager Initialization
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    setupFileProcessing();
    
    // Load config from backend
    await refreshCatalogs();
    
    // Bind buttons
    document.getElementById("btn-get-estimate").addEventListener("click", handleGetEstimate);
    document.getElementById("btn-submit-estimate").addEventListener("click", handleSubmitEstimate);
    document.getElementById("btn-run-discover").addEventListener("click", handleRunDiscover);
    document.getElementById("select-provider").addEventListener("change", () => {
        populateModelSelectors();
    });
    
    
    renderKeysList();
}

// --- CATALOG DATA FETCH ---
async function refreshCatalogs() {
    try {
        // Public, read-only catalog endpoints. Administrative routes are isolated from the Dashboard.
        const [modelsRes, rulesRes] = await Promise.all([
            fetch(`${state.backendUrl}/models`),
            fetch(`${state.backendUrl}/optimizer-rules`)
        ]);

        if (!modelsRes.ok || !rulesRes.ok) {
            throw new Error("Unable to load public optimizer configuration.");
        }

        state.models = await modelsRes.json();
        state.rules = await rulesRes.json();
        populateModelSelectors();
    } catch (e) {
        console.error("Failed to load backend catalogs:", e);
        showNotification("Backend server unreachable. Run local uvicorn instance.", "error");
    }
}

// --- KEY ROTATION & API RELAY CALLING ---
async function callBackendWithRotation(endpoint, method, payload, provider) {
    let attempts = 0;
    const maxAttempts = 5;
    
    while (attempts < maxAttempts) {
        const activeKey = apiKeysService.getActiveKey(provider);
        if (!activeKey) {
            throw new Error(`All configured API keys for provider '${provider}' are exhausted or missing. Please configure an active provider key in the Admin Console.`);
        }
        
        const headers = {
            "Content-Type": "application/json",
            "X-Shared-Secret": state.sharedSecret,
            "X-Provider-Key": activeKey.key
        };
        try {
            const response = await fetch(`${state.backendUrl}${endpoint}`, {
                method: method,
                headers: headers,
                body: JSON.stringify(payload)
            });
            
            if (response.status === 429 || response.status === 401) {
                // Key exhausted or invalid
                console.warn(`Key '${activeKey.label}' failed with status ${response.status}. Rotating key...`);
                apiKeysService.markKeyExhausted(provider, activeKey.id);
                attempts++;
                continue;
            }
            
            if (!response.ok) {
                const errDetail = await response.json();
                throw new Error(errDetail.detail || "Server error occurred");
            }
            
            return await response.json();
        } catch (e) {
            if (e.message.includes("Rotat")) {
                continue;
            }
            throw e;
        }
    }
    throw new Error("Failed to execute request after exhausting all rotating key attempts.");
}

// --- FILE PRE-PROCESSING IN BROWSER ---
function setupFileProcessing() {
    const fileInput = document.getElementById("file-docs");
    fileInput.addEventListener("change", (e) => {
        const files = e.target.files;
        state.project.documentSummaries = [];
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const sizeKB = Math.round(file.size / 1024);
            // Simulate document extraction in browser client-side
            state.project.documentSummaries.push({
                filename: file.name,
                page_count: Math.max(1, Math.round(sizeKB / 20)), // Estimate pages
                summary: `Processed locally. File type: ${file.type}, size: ${sizeKB}KB.`
            });
        }
        showNotification(`Processed ${files.length} document(s) locally. Ready for extraction.`, "success");
    });
}

// --- API ACTIONS HANDLERS ---
async function handleGetEstimate() {
    const desc = document.getElementById("input-description").value.trim();
    if (!desc) {
        showNotification("Please enter a project description first.", "error");
        return;
    }
    
    const provider = document.getElementById("select-provider").value;
    const modelId = document.getElementById("select-model").value;
    
    state.project.description = desc;
    state.project.provider = provider;
    state.project.modelId = modelId;
    
    setLoading(true, "Extracting tokens from description...");
    try {
        const result = await callBackendWithRotation("/extract", "POST", {
            project_description: desc,
            document_summaries: state.project.documentSummaries,
            provider: provider,
            model_id: modelId
        }, provider);
        
        state.project.phasesConfig = result.phases.map(p => ({
            ...p,
            assigned_model_id: modelId,
            assigned_provider: provider
        }));
        
        renderPhaseTable();
        showNotification("Token extraction complete. Review variables in the table.", "success");
    } catch (e) {
        showNotification(e.message, "error");
    } finally {
        setLoading(false);
    }
}

async function handleSubmitEstimate() {
    if (state.project.phasesConfig.length === 0) {
        showNotification("No phase configuration loaded. Run extraction first.", "error");
        return;
    }
    
    setLoading(true, "Calculating costs and applying rules...");
    try {
        // Collect edits from editable table input fields
        updateStateFromTable();
        
        const estimatePayload = {
            phases: state.project.phasesConfig,
            ams_config: {
                runs_per_year: parseInt(document.getElementById("ams-runs").value) || 12,
                annual_growth_rate: parseFloat(document.getElementById("ams-growth").value) / 100 || 0.1,
                horizon_years: parseInt(document.getElementById("ams-horizon").value) || 3
            }
        };
        
        // 1. Submit to /estimate
        const headers = {
            "Content-Type": "application/json",
            "X-Shared-Secret": state.sharedSecret
        };
        const estRes = await fetch(`${state.backendUrl}/estimate`, {
            method: "POST",
            headers,
            body: JSON.stringify(estimatePayload)
        });
        
        if (!estRes.ok) {
            const err = await estRes.json();
            throw new Error(estRes.status === 503 ? "pricing snapshot lookup failed. Atlas connection offline." : err.detail);
        }
        
        state.project.estimateResult = await estRes.json();
        
        // 2. Submit to /optimize
        const optRes = await fetch(`${state.backendUrl}/optimize`, {
            method: "POST",
            headers,
            body: JSON.stringify({
                pricing_snapshot: state.project.estimateResult.pricing_snapshot,
                phase_results: state.project.estimateResult.phase_results,
                phases: state.project.phasesConfig
            })
        });
        
        if (!optRes.ok) {
            const err = await optRes.json();
            throw new Error(err.detail);
        }
        
        state.project.optimizeResult = await optRes.json();
        
        // Update Panel UI
        renderMetricsDashboard();
        renderOptimizationRulesPanel();
        showNotification("Calculations and optimization rules applied.", "success");
    } catch (e) {
        showNotification(e.message, "error");
    } finally {
        setLoading(false);
    }
}

async function handleRunDiscover() {
    if (!state.project.estimateResult || !state.project.optimizeResult) {
        showNotification("Run standard calculations before executing AI discovery.", "error");
        return;
    }
    
    setLoading(true, "Analyzing with dynamic FinOps advisor...");
    try {
        const discoverPayload = {
            project_description: state.project.description,
            document_summaries: state.project.documentSummaries,
            phases: state.project.phasesConfig,
            pricing_snapshot: state.project.estimateResult.pricing_snapshot,
            estimate_result: state.project.estimateResult,
            optimize_result: state.project.optimizeResult,
            active_rules: state.rules
        };
        
        const res = await callBackendWithRotation(
            "/discover-optimizations",
            "POST",
            discoverPayload,
            state.project.provider
        );
        
        state.project.discoverResult = res;
        renderAiDiscoveryPanel();
        showNotification("AI discovery complete.", "success");
    } catch (e) {
        showNotification(e.message, "error");
    } finally {
        setLoading(false);
    }
}

// --- UI RENDER HANDLERS ---
function renderPhaseTable() {
    const tbody = document.getElementById("table-phases-body");
    tbody.innerHTML = "";
    
    state.project.phasesConfig.forEach((p, idx) => {
        const tr = document.createElement("tr");
        
        const isEdited = p.source === "user_edited" || p.source === "user-edited";
        const tagHTML = `<span class="badge ${isEdited ? 'badge-edited' : 'badge-extracted'}">${isEdited ? 'Edited' : 'Extracted'}</span>`;
        
        // Options for models dropdown
        const modelOptions = state.models
            .map(m => `<option value="${m.model_id}" ${m.model_id === p.assigned_model_id ? 'selected' : ''}>${m.display_name}</option>`)
            .join("");
            
        tr.innerHTML = `
            <td><strong>${p.phase}</strong></td>
            <td><input type="text" value="${p.agent_role}" class="table-text-input" data-field="agent_role" data-idx="${idx}"></td>
            <td><input type="number" value="${p.base_input_tokens}" class="table-input" data-field="base_input_tokens" data-idx="${idx}"></td>
            <td><input type="number" value="${p.context_input_tokens}" class="table-input" data-field="context_input_tokens" data-idx="${idx}"></td>
            <td><input type="number" step="0.1" value="${p.cacheable_fraction}" class="table-input" data-field="cacheable_fraction" data-idx="${idx}"></td>
            <td><input type="number" value="${p.tool_call_tokens}" class="table-input" data-field="tool_call_tokens" data-idx="${idx}"></td>
            <td><input type="number" value="${p.output_tokens}" class="table-input" data-field="output_tokens" data-idx="${idx}"></td>
            <td><input type="number" value="${p.estimated_calls}" class="table-input" style="width: 60px" data-field="estimated_calls" data-idx="${idx}"></td>
            <td>
                <select class="table-select" data-field="assigned_model_id" data-idx="${idx}">
                    ${modelOptions}
                </select>
            </td>
            <td>${tagHTML}</td>
        `;
        
        // Bind change listener to update source status
        tr.querySelectorAll("input, select").forEach(el => {
            el.addEventListener("change", (e) => {
                const targetIdx = parseInt(e.target.dataset.idx);
                const field = e.target.dataset.field;
                const val = e.target.value;
                
                // Update value
                const row = state.project.phasesConfig[targetIdx];
                if (e.target.type === "number") {
                    row[field] = Number(val);
                } else {
                    row[field] = val;
                }
                
                // Mark edited
                row.source = "user_edited";
                renderPhaseTable();
            });
        });
        
        tbody.appendChild(tr);
    });
}

function updateStateFromTable() {
    state.project.phasesConfig.forEach((p, idx) => {
        const rowElements = document.querySelectorAll(`[data-idx="${idx}"]`);
        rowElements.forEach(el => {
            const field = el.dataset.field;
            const val = el.value;
            if (el.type === "number") {
                p[field] = Number(val);
            } else {
                p[field] = val;
            }
        });
    });
}

function renderMetricsDashboard() {
    const rawTotal = parseFloat(state.project.estimateResult.project_total_cost);
    const optimizedCost = rawTotal - parseFloat(state.project.optimizeResult.total_savings_amount);
    const amsCost = parseFloat(state.project.estimateResult.ams_multi_year_total_cost);
    
    document.getElementById("cost-raw").innerText = `$${rawTotal.toFixed(2)}`;
    document.getElementById("cost-optimized").innerText = `$${optimizedCost.toFixed(2)}`;
    document.getElementById("cost-ams").innerText = `$${amsCost.toFixed(2)}`;
    
    const pct = parseFloat(state.project.optimizeResult.total_savings_percentage) * 100;
    document.getElementById("cost-savings").innerText = `${pct.toFixed(1)}%`;
}

function renderOptimizationRulesPanel() {
    const rulesContainer = document.getElementById("opt-rules-list");
    rulesContainer.innerHTML = "";
    
    const optRes = state.project.optimizeResult;
    optRes.phase_optimizations.forEach(opt => {
        if (opt.triggered_rules.length === 0) return;
        
        opt.triggered_rules.forEach(rule => {
            const card = document.createElement("div");
            card.className = "rule-card";
            card.innerHTML = `
                <div class="rule-info">
                    <h4>${rule.rule_id} [Phase: ${opt.phase}]</h4>
                    <p>Affected: ${rule.pool} token pool</p>
                </div>
                <div class="rule-reduction">
                    -${(parseFloat(rule.reduction_applied) * 100).toFixed(0)}%
                </div>
            `;
            rulesContainer.appendChild(card);
        });
    });
    
    // Render advisory
    const advContainer = document.getElementById("advisory-section");
    advContainer.innerHTML = "";
    if (optRes.advisory_recommendations.length > 0) {
        optRes.advisory_recommendations.forEach(adv => {
            const div = document.createElement("div");
            div.className = "advisory-box";
            div.innerHTML = `
                <div class="advisory-title">Advisory Action (Not added to total)</div>
                <div class="advisory-desc">${adv.description}</div>
            `;
            advContainer.appendChild(div);
        });
    }
}

function renderAiDiscoveryPanel() {
    const container = document.getElementById("ai-discover-list");
    container.innerHTML = "";
    
    const disc = state.project.discoverResult;
    disc.ai_strategies.forEach(strategy => {
        const div = document.createElement("div");
        div.className = "rule-card";
        div.style.borderColor = "rgba(6, 182, 212, 0.3)";
        div.innerHTML = `
            <div class="rule-info">
                <h4 style="color: var(--accent-cyan)">${strategy.name}</h4>
                <p>${strategy.description}</p>
                <p style="font-size: 0.75rem">Phases: ${strategy.affected_phases.join(", ")}</p>
            </div>
            <div class="rule-reduction" style="color: var(--accent-cyan)">
                +${(parseFloat(strategy.estimated_savings.expected_percent) * 100).toFixed(0)}% Potential
            </div>
        `;
        container.appendChild(div);
    });
    
    // Unquantified opportunities
    disc.unquantified_opportunities.forEach(opp => {
        const div = document.createElement("div");
        div.className = "advisory-box";
        div.style.borderColor = "rgba(6, 182, 212, 0.2)";
        div.style.background = "rgba(6, 182, 212, 0.02)";
        div.innerHTML = `
            <div class="advisory-title" style="color: var(--accent-cyan)">Opportunity: ${opp.name}</div>
            <div class="advisory-desc">${opp.description}</div>
        `;
        container.appendChild(div);
    });
}

// --- ADMIN & KEY MANAGEMENT HANDLERS ---
// --- UTILS ---
function populateModelSelectors() {
    const provider = document.getElementById("select-provider").value;
    const sel = document.getElementById("select-model");
    sel.innerHTML = "";
    state.models.filter(m => m.provider === provider).forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.model_id;
        opt.innerText = m.display_name;
        sel.appendChild(opt);
    });
}

function setLoading(isLoading, text = "Processing...") {
    const indicator = document.getElementById("loading-indicator");
    const label = document.getElementById("loading-label");
    if (isLoading) {
        label.innerText = text;
        indicator.style.display = "flex";
    } else {
        indicator.style.display = "none";
    }
}

function showNotification(msg, type = "success") {
    const notifier = document.getElementById("notification");
    notifier.innerText = msg;
    notifier.style.background = type === "error" ? "rgba(239, 68, 68, 0.9)" : "rgba(16, 185, 129, 0.9)";
    notifier.style.display = "block";
    
    setTimeout(() => {
        notifier.style.display = "none";
    }, 4000);
}
