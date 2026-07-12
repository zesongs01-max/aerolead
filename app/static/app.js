// Application State
const state = {
    activeTenantId: "",
    tenants: [],
    stats: {},
    activeView: "view-dashboard",
    directoryMode: false,
    lastDiscoveredCompanyIds: null,
    lastDiscoveredPersonIds: null,
    
    // Search parameters
    searchTab: "people",
    searchQuery: "",
    searchFilters: {
        company_locations: [],
        seniorities: [],
        email_status: [],
        technologies_any: [],
        employee_ranges: [],
        revenue_ranges: [],
        industries: []
    },
    selectedLeadIds: [],
    selectedCompanyIds: [],
    
    // Saved Lists
    lists: [],
    activeListId: "",
    
    // CRM config
    activeCrm: "salesforce",
    crmConfigs: {},
    
    // Chart reference
    industryChart: null
};

// Default CRM mappings from server config
const DEFAULT_CRM_MAPPINGS = {
    salesforce: {
        first_name: "FirstName",
        last_name: "LastName",
        email: "Email",
        title: "Title",
        company_name: "Company",
        phone: "Phone",
        linkedin_url: "LinkedIn_Profile_URL__c",
        confidence_score: "Confidence_Score__c"
    },
    hubspot: {
        first_name: "firstname",
        last_name: "lastname",
        email: "email",
        title: "jobtitle",
        company_name: "company",
        phone: "phone",
        linkedin_url: "linkedin_profile_url",
        confidence_score: "confidence_score"
    }
};

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
    initRouter();
    initTenantSelector();
    initSearchEvents();
    initEnrichmentEvents();
    initCrmEvents();
    initBillingEvents();
    initDevConsoleEvents();
    initModals();
    initDiscoveryPanel();
});

// View Routing Router
function initRouter() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach(item => {
        item.addEventListener("click", () => {
            navItems.forEach(ni => ni.classList.remove("active"));
            item.classList.add("active");
            
            const target = item.getAttribute("data-target");
            switchView(target);
        });
    });
}

function switchView(viewId) {
    state.activeView = viewId;
    
    // Toggle active view panel
    document.querySelectorAll(".view-panel").forEach(panel => {
        panel.classList.remove("active");
    });
    
    let targetViewId = viewId;
    if (viewId === "view-directory") {
        targetViewId = "view-search";
        state.directoryMode = true;
        
        // Hide discovery button and panel
        const btnDiscover = document.getElementById("btn-discover-web");
        if (btnDiscover) btnDiscover.style.display = "none";
        const panel = document.getElementById("discovery-panel");
        if (panel) panel.style.display = "none";
    } else {
        if (viewId === "view-search") {
            state.directoryMode = false;
            // Show discovery button
            const btnDiscover = document.getElementById("btn-discover-web");
            if (btnDiscover) btnDiscover.style.display = "inline-flex";
        }
    }
    
    const activePanel = document.getElementById(targetViewId);
    if (activePanel) activePanel.classList.add("active");
    
    // Update Header Page Title
    const titleMap = {
        "view-dashboard": "Dashboard Overview",
        "view-search": "Prospect Prospecting Hub",
        "view-directory": "Internal Database Directory",
        "view-enrichment": "Enrichment Waterfall Pipeline",
        "view-lists": "Saved Audience Segments",
        "view-crm": "GTM Integrations Setup",
        "view-billing": "Usage Metering & Billing",
        "view-developer": "Developer API Console"
    };
    document.getElementById("page-title").textContent = titleMap[viewId] || "AeroLead Intelligence";
    
    // Trigger view-specific loads
    if (viewId === "view-dashboard") {
        loadDashboardStats();
    } else if (viewId === "view-search" || viewId === "view-directory") {
        triggerSearch();
    } else if (viewId === "view-lists") {
        loadSavedLists();
    } else if (viewId === "view-crm") {
        loadCrmConfig();
    }
}

// Tenant Organization Selector
async function initTenantSelector() {
    const select = document.getElementById("tenant-select");
    select.addEventListener("change", (e) => {
        state.activeTenantId = e.target.value;
        loadTenantData();
    });
    
    try {
        const res = await fetch("/web/tenants");
        state.tenants = await res.json();
        
        select.innerHTML = "";
        state.tenants.forEach(t => {
            const opt = document.createElement("option");
            opt.value = t.tenant_id;
            opt.textContent = `${t.name} (${t.billing_plan.toUpperCase()})`;
            select.appendChild(opt);
        });
        
        if (state.tenants.length > 0) {
            state.activeTenantId = state.tenants[0].tenant_id;
            loadTenantData();
        }
    } catch (err) {
        console.error("Failed to load tenants", err);
    }
}

async function loadTenantData() {
    if (!state.activeTenantId) return;
    
    try {
        const res = await fetch(`/web/stats/${state.activeTenantId}`);
        state.stats = await res.json();
        
        // Update header fields
        document.getElementById("header-credits").textContent = state.stats.credit_balance.toFixed(1);
        document.getElementById("header-user-role").textContent = state.stats.billing_plan;
        
        // Upgrade visual meters
        const plans = { starter: 100, growth: 500, pro: 2000 };
        const maxCredits = plans[state.stats.billing_plan] || 100;
        const usedCredits = maxCredits - state.stats.credit_balance;
        
        // Update billing page elements if active
        const fill = document.getElementById("billing-credits-fill");
        const ratio = document.getElementById("billing-credits-used-ratio");
        if (fill && ratio) {
            ratio.textContent = `${Math.max(0, usedCredits).toFixed(0)} / ${maxCredits}`;
            fill.style.width = `${Math.min(100, Math.max(0, (usedCredits / maxCredits) * 100))}%`;
        }

        // Display active key on Dev Console
        const keyDisplay = document.getElementById("dev-api-key-display");
        if (keyDisplay) {
            keyDisplay.value = state.stats.api_key || "No key generated. Click generate.";
            document.querySelectorAll(".placeholder-key").forEach(span => {
                span.textContent = state.stats.api_key || "YOUR_KEY";
            });
        }
        
        // Refresh active views
        if (state.activeView === "view-dashboard") {
            updateDashboardDOM();
        }
    } catch (err) {
        console.error("Failed loading stats", err);
    }
}

// Dashboard Overview Loader
async function loadDashboardStats() {
    await loadTenantData();
}

function updateDashboardDOM() {
    const stats = state.stats;
    if (!stats.database_metrics) return;
    
    document.getElementById("stat-total-people").textContent = stats.database_metrics.total_people;
    document.getElementById("stat-total-companies").textContent = stats.database_metrics.total_companies;
    document.getElementById("stat-enrichments").textContent = stats.database_metrics.enrichments_processed;
    document.getElementById("stat-lists").textContent = stats.database_metrics.lists_created;
    
    // Draw Audit Log lists
    loadAuditLogsList();
    
    // Render chart
    renderIndustryChart();
}

async function loadAuditLogsList() {
    try {
        const res = await fetch(`/web/audit-logs/${state.activeTenantId}`);
        const logs = await res.json();
        
        const list = document.getElementById("dashboard-audit-logs");
        list.innerHTML = "";
        
        if (logs.length === 0) {
            list.innerHTML = `<div class="audit-item"><span class="audit-action">No actions logged yet</span></div>`;
            return;
        }
        
        logs.forEach(log => {
            const time = new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const item = document.createElement("div");
            item.className = "audit-item";
            item.innerHTML = `
                <span class="audit-action"><i class="fa-solid fa-angle-right text-indigo"></i> ${log.details || log.action}</span>
                <span class="audit-time">${time}</span>
            `;
            list.appendChild(item);
        });
    } catch (err) {
        console.error(err);
    }
}

function renderIndustryChart() {
    const ctx = document.getElementById("industry-chart").getContext("2d");
    if (state.industryChart) {
        state.industryChart.destroy();
    }
    
    state.industryChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["Software & SaaS", "Financial Services", "Manufacturing", "Healthcare"],
            datasets: [{
                data: [42, 28, 18, 12],
                backgroundColor: [
                    "#6366f1",
                    "#a855f7",
                    "#3b82f6",
                    "#10b981"
                ],
                borderWidth: 1,
                borderColor: "#27272a"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        color: "#a1a1aa",
                        font: { family: "Inter", size: 11 }
                    }
                }
            }
        }
    });
}

// Prospect Search Hub Logic
function initSearchEvents() {
    // Tab switching: People Search vs Company Search
    const tabPeople = document.getElementById("search-tab-people");
    const tabCompanies = document.getElementById("search-tab-companies");
    
    if (tabPeople && tabCompanies) {
        tabPeople.addEventListener("click", () => {
            tabPeople.classList.add("active");
            tabCompanies.classList.remove("active");
            state.searchTab = "people";
            
            // Adjust visible filters
            document.getElementById("filter-group-seniority").style.display = "block";
            document.getElementById("filter-group-email-status").style.display = "block";
            document.getElementById("filter-group-employees").style.display = "none";
            document.getElementById("filter-group-revenue").style.display = "none";
            
            // Toggle tables
            document.getElementById("search-results-table").style.display = "table";
            document.getElementById("company-results-table").style.display = "none";
            
            triggerSearch();
        });
        
        tabCompanies.addEventListener("click", () => {
            tabCompanies.classList.add("active");
            tabPeople.classList.remove("active");
            state.searchTab = "companies";
            
            // Adjust visible filters
            document.getElementById("filter-group-seniority").style.display = "none";
            document.getElementById("filter-group-email-status").style.display = "none";
            document.getElementById("filter-group-employees").style.display = "block";
            document.getElementById("filter-group-revenue").style.display = "block";
            
            // Toggle tables
            document.getElementById("company-results-table").style.display = "table";
            document.getElementById("search-results-table").style.display = "none";
            
            triggerSearch();
        });
    }

    document.getElementById("btn-search-trigger").addEventListener("click", () => {
        state.searchQuery = document.getElementById("search-query").value;
        triggerSearch();
    });
    
    document.getElementById("search-query").addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            state.searchQuery = e.target.value;
            triggerSearch();
        }
    });

    document.getElementById("btn-add-tech-filter").addEventListener("click", () => {
        const input = document.getElementById("search-tech-input");
        const val = input.value.trim();
        if (val && !state.searchFilters.technologies_any.includes(val)) {
            state.searchFilters.technologies_any.push(val);
            input.value = "";
            renderTechTags();
            triggerSearch();
        }
    });

    document.getElementById("btn-clear-filters").addEventListener("click", () => {
        state.searchFilters = {
            company_locations: [],
            seniorities: [],
            email_status: [],
            technologies_any: [],
            employee_ranges: [],
            revenue_ranges: [],
            industries: []
        };
        document.getElementById("search-query").value = "";
        state.searchQuery = "";
        renderTechTags();
        triggerSearch();
    });

    // Bulk select People
    document.getElementById("select-all-results").addEventListener("change", (e) => {
        const checked = e.target.checked;
        const checkboxes = document.querySelectorAll(".lead-select-checkbox");
        state.selectedLeadIds = [];
        checkboxes.forEach(cb => {
            cb.checked = checked;
            if (checked) {
                state.selectedLeadIds.push(cb.value);
            }
        });
        toggleBulkButtons();
    });

    // Bulk select Companies
    const selectAllComp = document.getElementById("select-all-companies");
    if (selectAllComp) {
        selectAllComp.addEventListener("change", (e) => {
            const checked = e.target.checked;
            const checkboxes = document.querySelectorAll(".company-select-checkbox");
            state.selectedCompanyIds = [];
            checkboxes.forEach(cb => {
                cb.checked = checked;
                if (checked) {
                    state.selectedCompanyIds.push(cb.value);
                }
            });
            toggleBulkButtons();
        });
    }

    document.getElementById("btn-bulk-save").addEventListener("click", () => {
        openSaveToListModal();
    });

    document.getElementById("btn-bulk-crm").addEventListener("click", () => {
        triggerBulkCrmSync();
    });
    
    // Close profile drawer click
    document.getElementById("btn-close-drawer").addEventListener("click", closeProfileDrawer);
}

function renderTechTags() {
    const box = document.getElementById("search-active-techs");
    box.innerHTML = "";
    state.searchFilters.technologies_any.forEach(tech => {
        const tag = document.createElement("span");
        tag.className = "tech-tag";
        tag.innerHTML = `${tech} <i class="fa-solid fa-xmark" onclick="removeTechFilter('${tech}')"></i>`;
        box.appendChild(tag);
    });
}

window.removeTechFilter = function(tech) {
    state.searchFilters.technologies_any = state.searchFilters.technologies_any.filter(t => t !== tech);
    renderTechTags();
    triggerSearch();
};

async function triggerSearch() {
    const endpoint = state.searchTab === "people" ? "/web/search/people" : "/web/search/companies";
    const payload = {
        query: state.searchQuery,
        filters: {
            ...state.searchFilters,
            only_discovered: !state.directoryMode,
            only_seeds: state.directoryMode
        },
        page: 1,
        page_size: 25
    };
    
    try {
        const res = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        
        if (state.searchTab === "people") {
            renderSearchResults(result.data);
            renderFacets(result.facets);
        } else {
            renderCompanySearchResults(result.data);
            renderCompanyFacets(result.facets);
        }
        
        document.getElementById("search-results-count").textContent = `Showing ${result.meta.total_estimate} results`;
    } catch (err) {
        console.error(err);
    }
}

function renderSearchResults(data) {
    const tbody = document.getElementById("search-results-tbody");
    tbody.innerHTML = "";
    state.selectedLeadIds = [];
    document.getElementById("select-all-results").checked = false;
    toggleBulkButtons();
    
    if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 40px;">No leads found matching your criteria. Try running the Enrichment Waterfall!</td></tr>`;
        return;
    }
    
    data.forEach(lead => {
        const tr = document.createElement("tr");
        
        const statusBadges = {
            verified: '<span class="badge badge-verified"><i class="fa-solid fa-check"></i> Verified</span>',
            likely_valid: '<span class="badge badge-likely"><i class="fa-solid fa-circle-question"></i> Likely Valid</span>',
            bouncing: '<span class="badge badge-bounce"><i class="fa-solid fa-xmark"></i> Bouncing</span>',
            unknown: '<span class="badge badge-unknown">Unknown</span>'
        };
        const statusBadge = statusBadges[lead.contactability.email_status] || statusBadges.unknown;
        
        tr.innerHTML = `
            <td><input type="checkbox" class="lead-select-checkbox" value="${lead.person.person_id}" onclick="event.stopPropagation(); handleLeadSelect(this)"></td>
            <td>
                <div style="font-weight: 600; color: var(--text-primary);">${lead.person.full_name}</div>
                <div style="font-size: 11px; color: var(--text-muted);">${lead.contactability.work_email || "No email available"}</div>
            </td>
            <td>
                <div style="font-weight: 500;">${lead.person.title}</div>
                <div style="font-size: 11px; color: var(--accent-color);">${lead.company.name || "Unassociated"}</div>
            </td>
            <td>${lead.company.hq_country || "Unknown"}</td>
            <td>${statusBadge}</td>
            <td><span class="badge badge-score">${lead.scores.confidence.toFixed(2)}</span></td>
            <td>
                <button type="button" class="btn btn-secondary btn-icon" onclick="event.stopPropagation(); inspectLead('${lead.lead_id}')"><i class="fa-solid fa-eye"></i></button>
            </td>
        `;
        
        tr.addEventListener("click", () => {
            inspectLead(lead.lead_id);
        });
        tbody.appendChild(tr);
    });
}

function renderCompanySearchResults(data) {
    const tbody = document.getElementById("company-results-tbody");
    tbody.innerHTML = "";
    state.selectedCompanyIds = [];
    const selectAllComp = document.getElementById("select-all-companies");
    if (selectAllComp) selectAllComp.checked = false;
    toggleBulkButtons();
    
    if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 40px;">No companies found matching your criteria. Try running the Enrichment Waterfall!</td></tr>`;
        return;
    }
    
    data.forEach(comp => {
        const tr = document.createElement("tr");
        const techsBadge = (comp.technologies || []).slice(0, 3).map(t => `<span class="badge badge-gray" style="margin-right:2px; font-size:10px;">${t}</span>`).join("");
        const moreTech = comp.technologies.length > 3 ? `<span class="badge badge-gray" style="font-size:10px;">+${comp.technologies.length - 3}</span>` : "";
        
        tr.innerHTML = `
            <td><input type="checkbox" class="company-select-checkbox" value="${comp.company_id}" onclick="event.stopPropagation(); handleCompanySelect(this)"></td>
            <td>
                <strong style="color: var(--text-primary);">${comp.legal_name}</strong>
                <div style="font-size:11px; margin-top:2px;">
                    <a href="https://${comp.domain}" target="_blank" rel="noopener" style="color: var(--accent-color); text-decoration: none;" onclick="event.stopPropagation()">
                        <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px;"></i> ${comp.domain}
                    </a>
                </div>
            </td>
            <td>${comp.hq_city ? comp.hq_city + ', ' : ''}${comp.hq_country || "Unknown"}</td>
            <td>
                <div>Size: ${comp.employee_range || "N/A"}</div>
                <div style="font-size:11px; color: var(--text-muted);">${comp.revenue_range || "N/A"}</div>
            </td>
            <td>
                <div style="font-weight: 500; font-size:11px; margin-bottom:4px; color: var(--accent-color);">${comp.industry || "General"}</div>
                <div>${techsBadge}${moreTech}</div>
            </td>
            <td><span class="badge badge-score">${comp.confidence_score.toFixed(2)}</span></td>
            <td>
                <button type="button" class="btn btn-secondary btn-icon" onclick="event.stopPropagation(); inspectCompany('${comp.company_id}')" title="View Company Details"><i class="fa-solid fa-eye"></i></button>
            </td>
        `;
        tr.addEventListener("click", () => {
            inspectCompany(comp.company_id);
        });
        tbody.appendChild(tr);
    });
}

window.handleLeadSelect = function(checkbox) {
    if (checkbox.checked) {
        state.selectedLeadIds.push(checkbox.value);
    } else {
        state.selectedLeadIds = state.selectedLeadIds.filter(id => id !== checkbox.value);
    }
    toggleBulkButtons();
};

window.handleCompanySelect = function(checkbox) {
    if (checkbox.checked) {
        state.selectedCompanyIds.push(checkbox.value);
    } else {
        state.selectedCompanyIds = state.selectedCompanyIds.filter(id => id !== checkbox.value);
    }
    toggleBulkButtons();
};

function toggleBulkButtons() {
    const hasSelections = (state.searchTab === "people" && state.selectedLeadIds.length > 0) ||
                          (state.searchTab === "companies" && state.selectedCompanyIds.length > 0);
    document.getElementById("btn-bulk-save").disabled = !hasSelections;
    document.getElementById("btn-bulk-crm").disabled = !hasSelections;
}

function renderFacets(facets) {
    if (!facets) return;
    renderFacetList("facet-locations", facets.company_locations, "company_locations");
    renderFacetList("facet-seniorities", facets.seniorities, "seniorities");
    renderFacetList("facet-email-status", facets.email_status, "email_status");
    renderFacetList("facet-industries", facets.industries, "industries");
}

function renderCompanyFacets(facets) {
    if (!facets) return;
    renderFacetList("facet-locations", facets.company_locations, "company_locations");
    renderFacetList("facet-employee-ranges", facets.employee_ranges, "employee_ranges");
    renderFacetList("facet-revenue-ranges", facets.revenue_ranges, "revenue_ranges");
    renderFacetList("facet-industries", facets.industries, "industries");
}

function renderFacetList(elementId, facetMap, filterKey) {
    const container = document.getElementById(elementId);
    if (!container) return;
    container.innerHTML = "";
    if (!facetMap || Object.keys(facetMap).length === 0) {
        container.innerHTML = `<span style="color: var(--text-muted); font-size: 11px;">No facets</span>`;
        return;
    }
    
    Object.entries(facetMap).forEach(([val, count]) => {
        const row = document.createElement("div");
        row.className = "facet-row";
        const isChecked = state.searchFilters[filterKey].includes(val);
        
        row.innerHTML = `
            <label style="display: flex; align-items: center; cursor: pointer;">
                <input type="checkbox" value="${val}" ${isChecked ? "checked" : ""} onchange="handleFacetChange(this, '${filterKey}')">
                <span>${val}</span>
            </label>
            <span class="facet-count">(${count})</span>
        `;
        container.appendChild(row);
    });
}

window.handleFacetChange = function(checkbox, filterKey) {
    const val = checkbox.value;
    if (checkbox.checked) {
        if (!state.searchFilters[filterKey].includes(val)) {
            state.searchFilters[filterKey].push(val);
        }
    } else {
        state.searchFilters[filterKey] = state.searchFilters[filterKey].filter(v => v !== val);
    }
    triggerSearch();
};

// Profile Detail slide drawer
async function inspectLead(leadId) {
    const drawer = document.getElementById("profile-drawer");
    const body = document.getElementById("profile-drawer-body");
    
    body.innerHTML = `
        <div style="display: flex; justify-content: center; padding: 40px; color: var(--text-secondary);">
            <i class="fa-solid fa-spinner fa-spin" style="font-size: 24px; margin-right: 12px;"></i> Resolving entity...
        </div>
    `;
    drawer.classList.add("open");
    
    try {
        const res = await fetch(`/web/leads/${leadId}`);
        
        if (!res.ok) {
            body.innerHTML = `<div style="padding: 20px; color: var(--red-text)">Failed to fetch profile details.</div>`;
            return;
        }
        
        const lead = await res.json();
        
        // Render detailed card body
        let signalHtml = "";
        if (lead.signals.tech_changes_90d) {
            lead.signals.tech_changes_90d.forEach(tc => {
                signalHtml += `<div class="audit-item"><span class="audit-action">${tc.technology} ${tc.change}</span> <span class="audit-time">${tc.detected_at}</span></div>`;
            });
        }
        
        let crmLinksHtml = "";
        lead.crm_links.forEach(link => {
            crmLinksHtml += `<span class="badge badge-score" style="margin-right:6px;"><i class="fa-brands fa-${link.system}"></i> ${link.record_type}: ${link.record_id}</span>`;
        });
        
        body.innerHTML = `
            <div style="text-align: center; margin-bottom: 24px;">
                <div class="avatar" style="width: 64px; height: 64px; font-size: 24px; margin: 0 auto 12px auto;"><i class="fa-solid fa-user"></i></div>
                <h2 style="font-size: 20px;">${lead.person.full_name}</h2>
                <p style="color: var(--accent-color); font-weight: 500; font-size: 14px; margin-top: 4px;">${lead.person.title}</p>
                <p style="color: var(--text-secondary); font-size: 13px;">${lead.company.name || "No Company Link"}</p>
            </div>
            
            <div class="card" style="padding: 16px; margin-bottom: 20px;">
                <h4 style="margin-bottom: 12px; font-size: 14px; text-transform: uppercase; color: var(--text-muted);">Contact Details</h4>
                <div style="display: flex; flex-direction: column; gap: 8px; font-size: 13px;">
                    <div><i class="fa-solid fa-envelope text-indigo" style="width: 20px;"></i> ${lead.person.email || "No email"}</div>
                    <div><i class="fa-solid fa-phone text-indigo" style="width: 20px;"></i> ${lead.person.phone || "No phone"}</div>
                    <div><i class="fa-solid fa-location-dot text-indigo" style="width: 20px;"></i> ${lead.company.hq_country || "USA"}</div>
                    <div><i class="fa-brands fa-linkedin text-indigo" style="width: 20px;"></i> <a href="${lead.person.linkedin_url || '#'}" target="_blank" style="color: var(--text-secondary);">LinkedIn Profile</a></div>
                </div>
            </div>
            
            <div class="card" style="padding: 16px; margin-bottom: 20px;">
                <h4 style="margin-bottom: 12px; font-size: 14px; text-transform: uppercase; color: var(--text-muted);">Company Firmographics</h4>
                <div style="display: flex; flex-direction: column; gap: 8px; font-size: 13px;">
                    <div><span style="color: var(--text-secondary);">Domain:</span> ${lead.company.domain}</div>
                    <div><span style="color: var(--text-secondary);">Industry:</span> ${lead.company.industry || "Technology"}</div>
                    <div><span style="color: var(--text-secondary);">Employees:</span> ${lead.company.employee_range || "N/A"}</div>
                </div>
            </div>

            <div class="card" style="padding: 16px; margin-bottom: 20px;">
                <h4 style="margin-bottom: 12px; font-size: 14px; text-transform: uppercase; color: var(--text-muted);">CRM Mapped Links</h4>
                <div style="margin-top: 8px;">
                    ${crmLinksHtml || "No CRM associations sync'd yet"}
                </div>
            </div>

            <div class="card" style="padding: 16px; margin-bottom: 20px;">
                <h4 style="margin-bottom: 12px; font-size: 14px; text-transform: uppercase; color: var(--text-muted);">Intent & Signals</h4>
                <div style="display: flex; flex-direction: column; gap: 8px; font-size: 13px; margin-bottom: 12px;">
                    <div><span style="color: var(--text-secondary);">Website Visits (30d):</span> ${lead.signals.website_visits_30d}</div>
                    <div><span style="color: var(--text-secondary);">Intent Topics:</span> ${lead.signals.intent_topics.join(", ")}</div>
                </div>
                <h5 style="margin-bottom: 6px; font-size: 12px; color: var(--text-secondary);">Tech Stack Installs</h5>
                ${signalHtml}
            </div>

            <div class="card" style="padding: 16px;">
                <h4 style="margin-bottom: 12px; font-size: 14px; text-transform: uppercase; color: var(--text-muted);">Audit Timeline</h4>
                <div class="audit-list">
                    ${lead.timeline.map(t => `<div class="audit-item"><span>${t.type.replace(/_/g, " ").toUpperCase()}</span> <span>${t.at.split('T')[0]}</span></div>`).join("")}
                </div>
            </div>
        `;
    } catch (err) {
        console.error(err);
    }
}

function closeProfileDrawer() {
    document.getElementById("profile-drawer").classList.remove("open");
}

async function inspectCompany(companyId) {
    const drawer = document.getElementById("profile-drawer");
    const body = document.getElementById("profile-drawer-body");
    
    body.innerHTML = `
        <div style="display: flex; justify-content: center; padding: 40px; color: var(--text-secondary);">
            <i class="fa-solid fa-spinner fa-spin" style="font-size: 24px; margin-right: 12px;"></i> Resolving company intelligence...
        </div>
    `;
    drawer.classList.add("open");
    
    try {
        const res = await fetch(`/web/companies/${companyId}`);
        if (!res.ok) {
            body.innerHTML = `<div style="padding: 20px; color: var(--red-text)">Failed to fetch company details.</div>`;
            return;
        }
        
        const comp = await res.json();
        
        let employeeListHtml = "";
        if (comp.employees && comp.employees.length > 0) {
            comp.employees.forEach(emp => {
                const emailStatusColor = emp.email_status === 'verified' ? 'var(--green-text, #4ade80)' : emp.email_status === 'likely_valid' ? '#f59e0b' : 'var(--text-muted)';
                const emailIcon = emp.email_status === 'verified' ? 'fa-check-circle' : 'fa-circle-question';
                employeeListHtml += `
                    <div style="background: var(--bg-secondary); border-radius: 10px; padding: 14px; margin-bottom: 10px; border: 1px solid var(--border-subtle);">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                            <div style="width: 36px; height: 36px; border-radius: 50%; background: var(--accent-gradient); display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; flex-shrink: 0;">${emp.full_name.charAt(0)}</div>
                            <div>
                                <div style="font-weight: 600; font-size: 14px; color: var(--text-primary);">${emp.full_name}</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">${emp.title || 'Unknown Role'}</div>
                            </div>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 5px; font-size: 12px; padding-left: 4px;">
                            ${emp.email ? `
                            <div style="display: flex; align-items: center; gap: 6px;">
                                <i class="fa-solid ${emailIcon}" style="color: ${emailStatusColor}; font-size: 11px;"></i>
                                <a href="mailto:${emp.email}" style="color: var(--accent-color); text-decoration: none;">${emp.email}</a>
                                <span style="color: ${emailStatusColor}; font-size: 10px;">(${emp.email_status})</span>
                                <button onclick="navigator.clipboard.writeText('${emp.email}'); this.innerHTML='<i class=\'fa-solid fa-check\'></i>'; setTimeout(()=>this.innerHTML='<i class=\'fa-solid fa-copy\'></i>',1500)" style="background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 0;" title="Copy email"><i class="fa-solid fa-copy"></i></button>
                            </div>` : '<div style="color:var(--text-muted); font-size:11px;"><i class="fa-solid fa-envelope-slash"></i> Email not available</div>'}
                        </div>
                    </div>
                `;
            });
        } else {
            employeeListHtml = `<div style="font-size:12px; color:var(--text-muted); padding: 12px; text-align: center;"><i class="fa-solid fa-user-slash" style="margin-right:6px;"></i>No employee records found in DB</div>`;
        }
        
        let techsHtml = (comp.technologies || []).map(t => `<span class="badge badge-gray" style="margin:2px 4px 2px 0;">${t}</span>`).join("");
        const websiteDisplay = comp.website_url || `https://${comp.domain}`;
        const linkedinDisplay = comp.linkedin_url;

        body.innerHTML = `
            <div style="text-align: center; margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--border-subtle);">
                <div style="width: 70px; height: 70px; border-radius: 16px; background: var(--accent-gradient); display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 14px auto;"><i class="fa-solid fa-building"></i></div>
                <h2 style="font-size: 20px; margin-bottom: 6px;">${comp.legal_name}</h2>
                <p style="color: var(--text-secondary); font-size: 13px; margin-bottom: 10px;">${comp.industry || "General Industry"} &bull; ${comp.sub_industry || ""}</p>
                <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                    <a href="${websiteDisplay}" target="_blank" rel="noopener" style="display: inline-flex; align-items: center; gap: 5px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 5px 10px; font-size: 12px; color: var(--accent-color); text-decoration: none;">
                        <i class="fa-solid fa-globe"></i> ${comp.domain}
                    </a>
                    ${linkedinDisplay ? `<a href="${linkedinDisplay}" target="_blank" rel="noopener" style="display: inline-flex; align-items: center; gap: 5px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 5px 10px; font-size: 12px; color: #0a66c2; text-decoration: none;"><i class="fa-brands fa-linkedin"></i> LinkedIn</a>` : ''}
                </div>
            </div>

            <div class="card" style="padding: 16px; margin-bottom: 16px;">
                <h4 style="margin-bottom: 12px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted);"><i class="fa-solid fa-chart-bar" style="margin-right:6px;"></i>Company Details</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 13px;">
                    <div><span style="color: var(--text-muted); font-size:11px; display:block;">HQ Location</span><span style="font-weight:500;">${comp.hq_city ? comp.hq_city + ', ' : ''}${comp.hq_country || 'N/A'}</span></div>
                    <div><span style="color: var(--text-muted); font-size:11px; display:block;">Employees</span><span style="font-weight:500;">${comp.employee_range || 'N/A'}</span></div>
                    <div><span style="color: var(--text-muted); font-size:11px; display:block;">Revenue</span><span style="font-weight:500;">${comp.revenue_range || 'N/A'}</span></div>
                    <div><span style="color: var(--text-muted); font-size:11px; display:block;">Founded</span><span style="font-weight:500;">${comp.founded_year || 'N/A'}</span></div>
                    <div><span style="color: var(--text-muted); font-size:11px; display:block;">Type</span><span style="font-weight:500; text-transform: capitalize;">${comp.public_private || 'N/A'}</span></div>
                    <div><span style="color: var(--text-muted); font-size:11px; display:block;">Funding Stage</span><span style="font-weight:500; text-transform: capitalize;">${(comp.funding_stage || 'N/A').replace('_', ' ')}</span></div>
                </div>
            </div>

            <div class="card" style="padding: 16px; margin-bottom: 16px;">
                <h4 style="margin-bottom: 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted);"><i class="fa-solid fa-microchip" style="margin-right:6px;"></i>Tech Stack</h4>
                <div>${techsHtml || '<span style="color:var(--text-muted); font-size:12px;">No technologies detected</span>'}</div>
            </div>

            <div class="card" style="padding: 16px; margin-bottom: 16px;">
                <h4 style="margin-bottom: 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted);">
                    <i class="fa-solid fa-users" style="margin-right:6px;"></i>Key Contacts (${comp.employees ? comp.employees.length : 0})
                </h4>
                <div>${employeeListHtml}</div>
            </div>
        `;
    } catch (err) {
        console.error(err);
    }
}

window.inspectCompany = inspectCompany;

// ============================================================
// 🌐 Web Discovery Engine
// ============================================================
let _discoveryJobId = null;
let _discoveryPollInterval = null;

function initDiscoveryPanel() {
    const btnDiscover = document.getElementById("btn-discover-web");
    if (btnDiscover) {
        btnDiscover.addEventListener("click", () => {
            const panel = document.getElementById("discovery-panel");
            panel.style.display = panel.style.display === "none" ? "block" : "none";
        });
    }
    const btnClose = document.getElementById("btn-close-discovery");
    if (btnClose) {
        btnClose.addEventListener("click", () => {
            document.getElementById("discovery-panel").style.display = "none";
        });
    }
    const btnRun = document.getElementById("btn-run-discovery");
    if (btnRun) {
        btnRun.addEventListener("click", runDiscovery);
    }
}

async function runDiscovery() {
    const query = document.getElementById("discovery-query").value.trim();
    const location = document.getElementById("discovery-location").value.trim();
    const techsRaw = document.getElementById("discovery-techs").value.trim();
    const required_techs = techsRaw ? techsRaw.split(",").map(t => t.trim()).filter(Boolean) : [];

    if (!query) {
        alert("Please enter what type of companies to find (e.g. 'auto parts')");
        return;
    }

    const progDiv = document.getElementById("discovery-progress");
    const logDiv = document.getElementById("discovery-log");
    const spinner = document.getElementById("discovery-spinner");
    progDiv.style.display = "block";
    logDiv.innerHTML = "";
    spinner.style.display = "inline-block";

    const btnRun = document.getElementById("btn-run-discovery");
    btnRun.disabled = true;
    btnRun.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin" style="margin-right:6px;"></i>Scanning...';

    try {
        const startRes = await fetch("/web/discover/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, location, required_techs, max_results: 15 }),
        });
        const startData = await startRes.json();
        if (startData.error) {
            _logDiscovery("❌ Error: " + startData.error);
            _finishDiscovery();
            return;
        }
        _discoveryJobId = startData.job_id;
        _logDiscovery(`🚀 Started scanning for: "${query}" in "${location || 'anywhere'}"...`);
        _discoveryPollInterval = setInterval(_pollDiscovery, 2000);
    } catch (err) {
        _logDiscovery("❌ Failed to start discovery: " + err.message);
        _finishDiscovery();
    }
}

async function _pollDiscovery() {
    if (!_discoveryJobId) return;
    try {
        const res = await fetch(`/web/discover/status/${_discoveryJobId}`);
        const data = await res.json();

        const logDiv = document.getElementById("discovery-log");
        if (data.progress && data.progress.length > 0) {
            const currentCount = logDiv.querySelectorAll(".log-line").length;
            for (let i = currentCount; i < data.progress.length; i++) {
                _logDiscovery(data.progress[i]);
            }
        }

        if (data.status === "complete") {
            clearInterval(_discoveryPollInterval);
            _discoveryPollInterval = null;
            _finishDiscovery();
            const result = data.result || {};
            _logDiscovery(`🎉 Done! Found ${result.companies_found || 0} matching companies with ${result.contacts_found || 0} contacts.`);
            
            const companyIds = (result.companies || []).map(c => c.company_id);
            const personIds = [];
            (result.companies || []).forEach(c => {
                if (c.contacts) {
                    c.contacts.forEach(p => {
                        if (p.person_id) personIds.push(p.person_id);
                    });
                }
            });
            state.lastDiscoveredCompanyIds = companyIds.length > 0 ? companyIds : ["__none__"];
            state.lastDiscoveredPersonIds = personIds.length > 0 ? personIds : ["__none__"];

            if (result.companies_found > 0) {
                _logDiscovery("🔄 Refreshing results...");
                state.searchTab = "companies";
                const tabC = document.getElementById("search-tab-companies");
                const tabP = document.getElementById("search-tab-people");
                if (tabC && tabP) {
                    tabC.classList.add("active"); tabP.classList.remove("active");
                    document.getElementById("company-results-table").style.display = "table";
                    document.getElementById("search-results-table").style.display = "none";
                }
                state.searchQuery = "";
                state.searchFilters = { company_locations:[], seniorities:[], email_status:[], technologies_any:[], employee_ranges:[], revenue_ranges:[], industries:[] };
                document.getElementById("search-query").value = "";
                await triggerSearch();
            }
        } else if (data.status === "error") {
            clearInterval(_discoveryPollInterval);
            _discoveryPollInterval = null;
            _logDiscovery("❌ Discovery failed: " + (data.error || "Unknown error"));
            _finishDiscovery();
        }
    } catch (err) {
        console.error("Poll error:", err);
    }
}

function _logDiscovery(msg) {
    const logDiv = document.getElementById("discovery-log");
    if (!logDiv) return;
    const line = document.createElement("div");
    line.className = "log-line";
    line.style.cssText = "border-bottom:1px solid rgba(255,255,255,0.04); padding-bottom:2px;";
    line.textContent = msg;
    logDiv.appendChild(line);
    logDiv.scrollTop = logDiv.scrollHeight;
}

function _finishDiscovery() {
    const btnRun = document.getElementById("btn-run-discovery");
    const spinner = document.getElementById("discovery-spinner");
    if (btnRun) { btnRun.disabled = false; btnRun.innerHTML = '<i class="fa-solid fa-satellite-dish" style="margin-right:6px;"></i>Discover'; }
    if (spinner) spinner.style.display = "none";
}

// Enrichment Waterfall Trigger UI
function initEnrichmentEvents() {
    // Tab switching Single vs Bulk
    const tabBtns = document.querySelectorAll("#view-enrichment .tab-btn");
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            
            const target = btn.getAttribute("data-tab");
            document.querySelectorAll("#view-enrichment .tab-content").forEach(tc => {
                tc.classList.remove("active");
            });
            document.getElementById(target).classList.add("active");
        });
    });

    // Form submit Single Enrichment
    document.getElementById("form-enrich-single").addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            tenant_id: state.activeTenantId,
            full_name: document.getElementById("enrich-name").value,
            company_domain: document.getElementById("enrich-domain").value,
            linkedin_url: document.getElementById("enrich-linkedin").value || null,
            email: document.getElementById("enrich-email").value || null
        };
        
        const resultPanel = document.getElementById("enrich-result-panel");
        resultPanel.style.display = "block";
        resultPanel.innerHTML = `<div style="text-align:center; color: var(--text-secondary);"><i class="fa-solid fa-spinner fa-spin"></i> Executing Enrichment Waterfall...</div>`;
        
        try {
            const res = await fetch("/web/enrich/person", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            if (res.status === 402) {
                resultPanel.innerHTML = `<div style="color: var(--red-text)"><i class="fa-solid fa-circle-xmark"></i> Out of enrichment credits. Purchase more on Billing view.</div>`;
                return;
            }
            
            const enriched = await res.json();
            
            resultPanel.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid var(--border-color); padding-bottom:12px; margin-bottom:12px;">
                    <h4 style="color: var(--green-text); font-size:15px;"><i class="fa-solid fa-circle-check"></i> Enrichment Complete</h4>
                    <span class="badge badge-score">Match Confidence: ${enriched.confidence_score.toFixed(2)}</span>
                </div>
                <div style="font-size:13px; display:flex; flex-direction:column; gap:8px;">
                    <div><strong style="color: var(--text-secondary);">Resolved Contact Name:</strong> ${enriched.full_name}</div>
                    <div><strong style="color: var(--text-secondary);">Title:</strong> ${enriched.title}</div>
                    <div><strong style="color: var(--text-secondary);">Verified Work Email:</strong> ${enriched.email || "Discovery failed"} (${enriched.email_status})</div>
                    <div><strong style="color: var(--text-secondary);">Direct Mobile:</strong> ${enriched.phone || "No phone found"}</div>
                </div>
            `;
            
            // Reload stats and search results
            loadTenantData();
        } catch (err) {
            console.error(err);
        }
    });

    // Mock CSV Import Upload Interaction
    const zone = document.getElementById("csv-drop-zone");
    const fileInput = document.getElementById("csv-file-input");
    
    zone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleMockCSVFile();
        }
    });
    
    document.getElementById("btn-process-csv").addEventListener("click", processMockCSVSync);
}

function handleMockCSVFile() {
    document.getElementById("csv-drop-zone").style.display = "none";
    document.getElementById("csv-preview-box").style.display = "block";
    
    const tbody = document.getElementById("csv-preview-tbody");
    tbody.innerHTML = `
        <tr>
            <td>Jane Doe</td>
            <td>acme.com</td>
            <td>jane.doe@acme.com</td>
        </tr>
        <tr>
            <td>John Smith</td>
            <td>stripe.com</td>
            <td>john.smith@stripe.com</td>
        </tr>
        <tr>
            <td>Alice Jones</td>
            <td>hubspot.com</td>
            <td>alice.jones@hubspot.com</td>
        </tr>
    `;
}

async function processMockCSVSync() {
    const btn = document.getElementById("btn-process-csv");
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processing Bulk Enrichment (3 Credits)...`;
    btn.disabled = true;
    
    // Trigger three simulated enrichments
    const mockList = [
        { full_name: "Jane Doe", company_domain: "acme.com", email: "jane.doe@acme.com" },
        { full_name: "John Smith", company_domain: "stripe.com", email: "john.smith@stripe.com" },
        { full_name: "Alice Jones", company_domain: "hubspot.com", email: "alice.jones@hubspot.com" }
    ];
    
    for (const payload of mockList) {
        await fetch("/web/enrich/person", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tenant_id: state.activeTenantId, ...payload })
        });
    }
    
    // Reset view
    btn.innerHTML = "Process List & Enrich";
    btn.disabled = false;
    document.getElementById("csv-preview-box").style.display = "none";
    document.getElementById("csv-drop-zone").style.display = "block";
    
    // Switch to search and reload
    switchView("view-search");
}

// CRM Sync configuration logic
function initCrmEvents() {
    const cards = document.querySelectorAll(".crm-card");
    cards.forEach(card => {
        card.addEventListener("click", () => {
            cards.forEach(c => c.classList.remove("active-crm"));
            card.classList.add("active-crm");
            state.activeCrm = card.getAttribute("data-crm");
            renderCrmMappingsTable();
        });
    });

    document.getElementById("btn-save-crm-config").addEventListener("click", async () => {
        const payload = {
            tenant_id: state.activeTenantId,
            crm_type: state.activeCrm,
            conflict_policy: document.getElementById("crm-conflict-policy").value,
            field_mapping: DEFAULT_CRM_MAPPINGS[state.activeCrm]
        };
        
        try {
            await fetch("/web/crm-sync/configure", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            alert(`${state.activeCrm.toUpperCase()} Integration configuration applied.`);
            loadCrmConfig();
        } catch (err) {
            console.error(err);
        }
    });

    document.getElementById("btn-crm-sync-trigger").addEventListener("click", async () => {
        const btn = document.getElementById("btn-crm-sync-trigger");
        btn.innerHTML = `<i class="fa-solid fa-rotate fa-spin"></i> Synchronizing data...`;
        btn.disabled = true;
        
        try {
            const res = await fetch("/web/crm-sync/trigger", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tenant_id: state.activeTenantId, crm_type: state.activeCrm })
            });
            const data = await res.json();
            alert(`Sync complete! Synchronized ${data.synced_leads} lead profiles.`);
            loadCrmConfig();
        } catch (err) {
            console.error(err);
        } finally {
            btn.innerHTML = `<i class="fa-solid fa-rotate"></i> Start Synchronization`;
            btn.disabled = false;
        }
    });
}

async function loadCrmConfig() {
    try {
        const res = await fetch(`/web/crm-sync/${state.activeTenantId}`);
        const configs = await res.json();
        
        // Reset badges
        document.getElementById("sf-status-badge").className = "badge badge-gray";
        document.getElementById("sf-status-badge").textContent = "Disconnected";
        document.getElementById("hs-status-badge").className = "badge badge-gray";
        document.getElementById("hs-status-badge").textContent = "Disconnected";
        
        const logsList = document.getElementById("crm-sync-logs-list");
        logsList.innerHTML = "";
        
        configs.forEach(c => {
            const badgeId = c.crm_type === "salesforce" ? "sf-status-badge" : "hs-status-badge";
            const badge = document.getElementById(badgeId);
            if (c.is_active) {
                badge.className = "badge badge-green";
                badge.textContent = "Connected";
            }
            
            // Populate logs
            if (c.sync_logs && c.crm_type === state.activeCrm) {
                c.sync_logs.forEach(log => {
                    const row = document.createElement("div");
                    row.className = "audit-item";
                    row.innerHTML = `
                        <span>Synced <strong>${log.synced_leads}</strong> accounts. Conflicts resolved: ${log.conflicts_resolved}</span>
                        <span class="audit-time">${log.timestamp.split('T')[0]}</span>
                    `;
                    logsList.appendChild(row);
                });
            }
        });
        
        if (logsList.innerHTML === "") {
            logsList.innerHTML = `<div class="audit-item">No sync runs processed yet</div>`;
        }
        
        renderCrmMappingsTable();
    } catch (err) {
        console.error(err);
    }
}

function renderCrmMappingsTable() {
    const tbody = document.getElementById("crm-mapping-tbody");
    tbody.innerHTML = "";
    
    const mapping = DEFAULT_CRM_MAPPINGS[state.activeCrm];
    Object.entries(mapping).forEach(([localField, crmField]) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><code>${localField}</code></td>
            <td><input type="text" class="form-control" style="padding: 6px 12px; width: 240px;" value="${crmField}" readonly></td>
            <td><span class="badge badge-gray">Overwrite if newer</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// Bulk CRM Sync trigger helper
async function triggerBulkCrmSync() {
    alert(`Syncing ${state.selectedLeadIds.length} selected leads to connected CRM...`);
    // Simulate API call
    switchView("view-crm");
}

// Billing and Packages Buy Credit
function initBillingEvents() {
    const packs = document.querySelectorAll(".credits-packages .pack");
    const buyBtn = document.getElementById("btn-buy-credits");
    let selectedAmount = 0;
    
    packs.forEach(pack => {
        pack.addEventListener("click", () => {
            packs.forEach(p => p.classList.remove("selected-pack"));
            pack.classList.add("selected-pack");
            selectedAmount = parseInt(pack.getAttribute("data-amount"));
            buyBtn.disabled = false;
            buyBtn.textContent = `Buy ${selectedAmount} Credits`;
        });
    });

    buyBtn.addEventListener("click", async () => {
        if (selectedAmount <= 0) return;
        
        try {
            await fetch("/web/billing/topup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tenant_id: state.activeTenantId, credits: selectedAmount })
            });
            alert(`Purchase success! Credited ${selectedAmount} credits to organization account.`);
            
            // Clear selection
            packs.forEach(p => p.classList.remove("selected-pack"));
            buyBtn.disabled = true;
            buyBtn.textContent = "Select Package";
            selectedAmount = 0;
            
            loadTenantData();
        } catch (err) {
            console.error(err);
        }
    });

    document.getElementById("btn-upgrade-pro").addEventListener("click", async () => {
        try {
            await fetch("/web/billing/plan", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tenant_id: state.activeTenantId, plan: "pro" })
            });
            alert(`Organization account upgraded to PRO. Added 2,000 monthly credits!`);
            
            // Refresh organization options
            initTenantSelector();
        } catch (err) {
            console.error(err);
        }
    });
}

// Developer Public API Key generator
function initDevConsoleEvents() {
    document.getElementById("btn-generate-key").addEventListener("click", async () => {
        try {
            const res = await fetch("/web/api-keys/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tenant_id: state.activeTenantId })
            });
            const data = await res.json();
            
            document.getElementById("dev-api-key-display").value = data.api_key;
            document.querySelectorAll(".placeholder-key").forEach(span => {
                span.textContent = data.api_key;
            });
            
            alert("New API key generated successfully.");
        } catch (err) {
            console.error(err);
        }
    });
}

// Saved List Views and modal interactions
function initModals() {
    const listModal = document.getElementById("new-list-modal");
    
    document.getElementById("btn-new-list-modal").addEventListener("click", () => {
        listModal.style.display = "flex";
    });
    
    document.getElementById("btn-close-list-modal").addEventListener("click", () => {
        listModal.style.display = "none";
    });

    document.getElementById("form-create-list").addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            tenant_id: state.activeTenantId,
            name: document.getElementById("modal-list-name").value,
            type: document.getElementById("modal-list-type").value
        };
        
        try {
            const res = await fetch("/web/lists", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                listModal.style.display = "none";
                document.getElementById("modal-list-name").value = "";
                loadSavedLists();
            }
        } catch (err) {
            console.error(err);
        }
    });
}

// Saved list views mapping
async function loadSavedLists() {
    try {
        const res = await fetch(`/web/lists/${state.activeTenantId}`);
        const lists = await res.json();
        state.lists = lists;
        
        const ul = document.getElementById("saved-lists-ul");
        ul.innerHTML = "";
        
        if (lists.length === 0) {
            ul.innerHTML = `<li style="padding: 10px 16px; color: var(--text-muted); font-size:12px;">No lists found. Click plus to create.</li>`;
            return;
        }
        
        lists.forEach(lst => {
            const li = document.createElement("li");
            li.className = "nav-item";
            li.style.padding = "8px 12px";
            li.innerHTML = `<i class="fa-solid fa-tag text-indigo"></i><span>${lst.name}</span>`;
            li.addEventListener("click", () => {
                // Remove custom active classes
                ul.querySelectorAll("li").forEach(item => item.classList.remove("active"));
                li.classList.add("active");
                inspectSavedList(lst);
            });
            ul.appendChild(li);
        });
    } catch (err) {
        console.error(err);
    }
}

async function inspectSavedList(lst) {
    state.activeListId = lst.list_id;
    document.getElementById("active-list-title").textContent = lst.name;
    document.getElementById("active-list-meta").textContent = `List Type: ${lst.type.toUpperCase()} | Contains ${lst.entity_ids.length} contacts`;
    document.getElementById("btn-sync-active-list").style.display = "inline-flex";
    
    const table = document.getElementById("list-leads-table");
    const tbody = document.getElementById("list-leads-tbody");
    tbody.innerHTML = "";
    table.style.display = "table";

    if (lst.entity_ids.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">This list is empty. Check Prospect Search to add accounts.</td></tr>`;
        return;
    }

    // Load each entity details
    for (const pId of lst.entity_ids) {
        try {
            const res = await fetch(`/web/leads/ld_${pId.split('_')[1]}`);
            if (res.ok) {
                const lead = await res.json();
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${lead.person.full_name}</strong></td>
                    <td>${lead.person.title}</td>
                    <td>${lead.company.name || "N/A"}</td>
                    <td><code>${lead.person.email || "No email"}</code></td>
                    <td><span class="badge badge-score">${lead.person.confidence_score.toFixed(2)}</span></td>
                `;
                tbody.appendChild(tr);
            }
        } catch (err) {
            console.error(err);
        }
    }
}

// Bulk Save to List Modal launcher helper
function openSaveToListModal() {
    if (state.lists.length === 0) {
        alert("Please create a Saved List first in the 'Saved Lists' view!");
        switchView("view-lists");
        return;
    }
    
    const selectOptions = state.lists.map(lst => `<option value="${lst.list_id}">${lst.name}</option>`).join("");
    const modalHtml = `
        <div class="modal-backdrop" id="bulk-save-modal">
            <div class="modal">
                <div class="modal-header">
                    <h3>Save Selected Leads</h3>
                    <button type="button" class="close-btn" onclick="document.getElementById('bulk-save-modal').remove()"><i class="fa-solid fa-xmark"></i></button>
                </div>
                <div class="modal-body">
                    <p style="font-size:13px; color: var(--text-secondary); margin-bottom:12px;">Add ${state.selectedLeadIds.length} selected contacts to your list:</p>
                    <select id="bulk-save-list-select" class="form-control">
                        ${selectOptions}
                    </select>
                    <button type="button" class="btn btn-primary btn-full mt-20" onclick="processBulkSave()">Add to List</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML("beforeend", modalHtml);
}

window.processBulkSave = async function() {
    const listId = document.getElementById("bulk-save-list-select").value;
    const cleanIds = state.selectedLeadIds.map(id => `pr_${id.split('_')[1]}`);
    
    try {
        const res = await fetch("/web/lists/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ list_id: listId, entity_ids: cleanIds })
        });
        if (res.ok) {
            alert("Contacts successfully saved to your list.");
            document.getElementById("bulk-save-modal").remove();
            
            // Reset table checkboxes
            state.selectedLeadIds = [];
            document.querySelectorAll(".lead-select-checkbox").forEach(cb => cb.checked = false);
            document.getElementById("select-all-results").checked = false;
            toggleBulkButtons();
        }
    } catch (err) {
        console.error(err);
    }
};
