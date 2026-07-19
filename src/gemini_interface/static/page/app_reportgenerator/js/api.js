let nlogTablesLoaded = false;
let nlogTablesLoading = false;

document.addEventListener('DOMContentLoaded', async () => {
    await initializeNlogAdvancedOptions();

    // Then check the tagname files
    // await check_nlog_tagname_files();
});

async function initializeNlogAdvancedOptions() {
    nlogTablesLoaded = false;
    nlogTablesLoading = true;
    setNlogAdvancedButtonState("loading");

    try {
        // Wait for plant to load fully
        await load_plant();

        // Load all available units
        await loadAllAvailableUnits();

        // Then get and display the tagnames
        await show_nlog_tagnames();

        nlogTablesLoaded = true;
        setNlogAdvancedButtonState("ready");
    } catch (error) {
        console.error("Error loading NLOG advanced options:", error);
        nlogTablesLoaded = false;
        setNlogAdvancedButtonState("error");
    } finally {
        nlogTablesLoading = false;
    }
}


toggleButton.addEventListener('click', () => {
    const isVisible = advancedSection.style.display === 'block';
    advancedSection.style.display = isVisible ? 'none' : 'block';
});

button_nlog_advanced.addEventListener('click', () => {
    if (!nlogTablesLoaded || nlogTablesLoading) return;

    const isVisible = advancedNLOGSection.style.display === 'block';
    advancedNLOGSection.style.display = isVisible ? 'none' : 'block';
});

function setNlogAdvancedButtonState(state) {
    const button = document.getElementById('button_nlog_advanced');
    if (!button) return;

    if (state === "loading") {
        button.disabled = true;
        button.innerHTML = '<i class="fa fa-spinner fa-spin mr-1" aria-hidden="true"></i> Loading...';
        return;
    }

    if (state === "error") {
        button.disabled = true;
        button.textContent = 'Advanced Options unavailable';
        return;
    }

    button.disabled = false;
    button.textContent = 'Advanced Options';
}

// ===== UNIT SELECTION & MANAGEMENT =====

let allAvailableUnits = [];

async function loadAllAvailableUnits() {
    return new Promise(resolve => {
        $.ajax({
            type: "GET",
            url: "/app/reportgenerator/get_all_units",
            dataType: "json",
            timeout: 60000,
            success: function(resp) {
                allAvailableUnits = resp.units || [];
                resolve(allAvailableUnits);
            },
            error: function(xhr, status, error) {
                console.error("Error loading units:", error);
                resolve([]);
            }
        });
    });
}

// Get unit name from unit selection dropdown in row
function getUnitFromRow(rowElement) {
    const unitSelect = rowElement.querySelector("select.unit-name-select");
    return unitSelect?.value || "";
}

// Get original unit name from data attribute (for detecting changes)
function getOriginalUnitFromRow(rowElement) {
    const unitSelect = rowElement.querySelector("select.unit-name-select");
    return unitSelect?.dataset.originalValue || "";
}

// Make load_plant return a Promise so it can be awaited
async function load_plant() {
    const fieldID = $('#select_project').val();

    return new Promise((resolve, reject) => {
        $.ajax({
            type: 'POST',
            url: '/app/reportgenerator/load_plant',
            contentType: 'application/json',
            dataType: 'json',
            data: JSON.stringify({field_name: fieldID}),
            timeout: 60000,

            success: function (response) {
                // Resolve on success so caller can await
                if (response.message) {
                }
                resolve(response);
            },

            error: function (xhr, status, error) {
                // Log error and reject so caller can handle failures
                console.error('load_plant ERROR');
                console.error('HTTP status:', xhr.status);
                console.error('Status text:', xhr.statusText);

                if (xhr.responseJSON) {
                    console.error('Error type:', xhr.responseJSON.error);
                    console.error('Message:', xhr.responseJSON.message);
                    if (xhr.responseJSON.details) {
                        console.error('Details:', xhr.responseJSON.details);
                    }
                } else {
                    console.error('Raw response:', xhr.responseText);
                    console.error('jQuery error:', error);
                }

                reject(error || new Error('load_plant failed'));
            }
        });
    });
}


function get_esp_plot_options() {
    var inputs = {
        esp_flow: {
            checked: document.querySelector('[name="value_select_1"]').checked,
            min: document.querySelector('[name="min_value_1"]').value,
            max: document.querySelector('[name="max_value_1"]').value
        },
        esp_amperage: {
            checked: document.querySelector('[name="value_select_3"]').checked,
            min: document.querySelector('[name="min_value_3"]').value,
            max: document.querySelector('[name="max_value_3"]').value
        },
        esp_frequency: {
            checked: document.querySelector('[name="value_select_4"]').checked,
            min: document.querySelector('[name="min_value_4"]').value,
            max: document.querySelector('[name="max_value_4"]').value
        },
        esp_voltage: {
            checked: document.querySelector('[name="value_select_5"]').checked,
            min: document.querySelector('[name="min_value_5"]').value,
            max: document.querySelector('[name="max_value_5"]').value
        },
        esp_motor_temperature: {
            checked: document.querySelector('[name="value_select_7"]').checked,
            min: document.querySelector('[name="min_value_7"]').value,
            max: document.querySelector('[name="max_value_7"]').value
        },
        esp_vibration_x: {
            checked: document.querySelector('[name="value_select_8"]').checked,
            min: document.querySelector('[name="min_value_8"]').value,
            max: document.querySelector('[name="max_value_8"]').value
        },
        esp_vibration_y: {
            checked: document.querySelector('[name="value_select_9"]').checked,
            min: document.querySelector('[name="min_value_9"]').value,
            max: document.querySelector('[name="max_value_9"]').value
        },
        esp_intake_pressure: {
            checked: document.querySelector('[name="value_select_10"]').checked,
            min: document.querySelector('[name="min_value_10"]').value,
            max: document.querySelector('[name="max_value_10"]').value
        },
        esp_discharge_pressure: {
            checked: document.querySelector('[name="value_select_11"]').checked,
            min: document.querySelector('[name="min_value_11"]').value,
            max: document.querySelector('[name="max_value_11"]').value
        }
    };

    return inputs;
}

function get_inj_well_crossplot_options() {
    var inputs = {
        min_flow_plot: document.getElementById('min_flow_plot').value,
        max_flow_plot: document.getElementById('max_flow_plot').value,
        no_interval_flow_plot: document.getElementById('no_interval_flow_plot').value,
        min_skin_plot: document.getElementById('min_skin_plot').value,
        max_skin_plot: document.getElementById('max_skin_plot').value,
        no_interval_skin_plot: document.getElementById('no_interval_skin_plot').value
    };

    return inputs;
}


function generate_report() {
    inj_well_crossplot_options = get_inj_well_crossplot_options()

    esp_plots_options = get_esp_plot_options()

    range_time = document.getElementById("datetime").value
    range_time = range_time.split(" - ");
    start_time = range_time[0]
    end_time = range_time[1]

    var inputs = {
        StartTime: start_time,
        EndTime: end_time,
        AuthorName: document.getElementById("author_name").value,
        ProjectName: document.getElementById("select_project").value,
        InjectionReport: document.getElementById("injection_report").checked,
        ProductionReport: document.getElementById("production_report").checked,
        P_Q_date_crossplot: document.getElementById("P-Q-date_checkbox").checked,
        P_Q_T_crossplot: document.getElementById("P-Q-T_checkbox").checked,
        ESP_Q_Pow_date_crossplot: document.getElementById("ESP_Q-Pow-date_checkbox").checked,
        ESP_freq_I_date_crossplot: document.getElementById("ESP_freq-I-date_checkbox").checked,
        esp_plots_options: esp_plots_options,
        inj_well_crossplot_options: inj_well_crossplot_options,
        // User comments
        inj_report_comments: document.getElementById("InjReportComments").value,
        prod_report_comments: document.getElementById("ProdReportComments").value,
        esp_report_comments: document.getElementById("ESPReportComments").value,
    };


    // Call get_component_parameters python function
    $.ajax({
        type: 'POST',
        url: '/app/reportgenerator/generate_report',
        contentType: 'application/json',
        data: JSON.stringify(inputs),
        xhrFields: {
            responseType: 'blob'
        },
        success: function (data, status, xhr) {

            var blob = new Blob([data], {type: "application/pdf"});

            var url = window.URL.createObjectURL(blob);

            var a = document.createElement('a');
            a.href = url;
            a.download = "report.pdf";
            document.body.appendChild(a);
            a.click();

            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        },
        error: function (xhr, status, error) {
            console.error("Error generating PDF:", error);
        }
    });
}

function generate_nlog_report() {
    validateAllTagnames().then(result => {
        const warnings = result.warnings;
        const warningsBySection = result.warnings_by_section;

        const performGenerate = () => {
            const {rows_section1A, rows_section1B, rows_section2} = collect_all_nlog_rows()

            // Check that all rows have unit selected (safeguard)
            const allRows = rows_section1A.concat(rows_section1B, rows_section2);
            const missingUnit = allRows.find(row => row.enabled !== false && (!row.component_name || row.component_name.trim() === ""));
            if (missingUnit) {
                alert("All rows must have a Unit Name selected.");
                return;
            }

            var inputs = {
                ProjectName: document.getElementById("select_project").value,
                NlogPeriod: document.getElementById("nlog_period").value,
                LicenseHolder: document.getElementById("nlog_license_holder").value,
                rows_section1A: rows_section1A,
                rows_section1B: rows_section1B,
                rows_section2: rows_section2,
            };

            $.ajax({
                type: 'POST',
                url: '/app/reportgenerator/generate_nlog_report',
                contentType: 'application/json',
                data: JSON.stringify(inputs),
                xhrFields: {responseType: 'blob'},

                success: function (data, status, xhr) {
                    // 1) Try to get filename from server (Content-Disposition)
                    var disposition = xhr.getResponseHeader("Content-Disposition") || "";
                    var filename = "";

                    // RFC 5987 / filename*=UTF-8''...
                    var matchStar = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
                    if (matchStar && matchStar[1]) {
                        filename = decodeURIComponent(matchStar[1].replace(/["']/g, ""));
                    } else {
                        // filename="..."
                        var match = disposition.match(/filename\s*=\s*("?)([^";]+)\1/i);
                        if (match && match[2]) filename = match[2];
                    }

                    // 2) Fallback: build filename client-side if header missing
                    if (!filename) {
                        var licenseHolder = (inputs.LicenseHolder || "LicenseHolder").trim();
                        var projectName = (inputs.ProjectName || "Project").trim();
                        var nlogPeriod = (inputs.NlogPeriod || "YYYY-MM").trim();

                        function sanitizeFilenamePart(s) {
                            return s.replace(/[\/\\:*?"<>|]/g, "-").replace(/\s+/g, "_");
                        }

                        filename =
                            sanitizeFilenamePart(licenseHolder) + "_" +
                            sanitizeFilenamePart(projectName) + "_" +
                            sanitizeFilenamePart(nlogPeriod) + "_NLOG.xlsm";
                    }

                    // 3) Use server content type if present
                    var contentType = xhr.getResponseHeader("Content-Type") ||
                        "application/vnd.ms-excel.sheet.macroEnabled.12";

                    var blob = new Blob([data], {type: contentType});
                    var url = window.URL.createObjectURL(blob);

                    var a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();

                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                },

                error: function (xhr, status, error) {
                    console.error("Error generating NLOG report:", error);
                }
            });
        };

        showValidationWarnings(warnings, warningsBySection, performGenerate);
    });
}

// Load all sections (1A, 1B, 2) and render into their tables
async function show_nlog_tagnames() {
    const inputs = {
        ProjectName: document.getElementById("select_project")?.value || "",
        NlogPeriod: document.getElementById("nlog_period")?.value || "",
        LicenseHolder: document.getElementById("nlog_license_holder")?.value || ""
    };

    const resp = await $.ajax({
        type: "POST",
        url: "/app/reportgenerator/get_nlog_tagnames",
        contentType: "application/json",
        dataType: "json",
        data: JSON.stringify(inputs),
        timeout: 60000
    });


    // Clear tagname cache when reloading (safeguard)
    for (let key in tagnameCache) {
        delete tagnameCache[key];
    }

    await Promise.all([
        render_nlog_table("nlog_section1A_table", resp.section1A || []),
        render_nlog_table("nlog_section1B_table", resp.section1B || []),
        render_nlog_section2("nlog_section2_table", resp.section2 || {})
    ]);

    return resp;
}

// Mapping from internal parameter keys to nicer display titles
const PARAM_DISPLAY_LABELS = {
    // Production (section 1A)
    prod_vol_water: "Produced water volume [m³]",
    prod_temp_avg_weighted: "Average produced temperature [°C]",
    prod_pres_avg: "Production pressure – average [bar]",
    prod_pres_min: "Production pressure – minimum [bar]",
    prod_wh_pres: "Wellhead pressure [bar]",
    prod_oil_vol: "Produced oil volume [m³]",
    prod_gas_vol: "Produced gas volume [m³]",
    prod_condens_vol: "Produced condensate volume [m³]",
    prod_inhibit_vol: "Produced inhibitor volume [m³]",

    // Injection (section 1B)
    inj_vol_water: "Injected water volume [m³]",
    inj_temp_avg_weighted: "Average injection temperature [°C]",
    inj_pres_avg: "Injection pressure – average [bar]",
    inj_pres_max: "Injection pressure – maximum [bar]",
    inj_inhibit_vol: "Injected inhibitor volume [m³]",

    // Totals / Section 2
    tot_heat_MJ: "Total heat [MJ]",
    tot_heat_MJ_inlet_temp: "Heat exchanger inlet temperature [°C]",
    tot_heat_MJ_outlet_temp: "Heat exchanger outlet temperature [°C]",
    tot_heat_MJ_flow: "Heat exchanger flow [m³/h]",
    tot_oper_hours: "Total operating hours [h]",
    tot_oper_hours_flow: "Total operating hours – flow weighted [h]",
    tot_el_cons_KWh: "Total electric consumption [kWh]",
    tot_el_cons_KWh_power: "Electric consumption – cumulative energy meter [kWh]",
    tot_el_cons_KWh_voltage: "Electric consumption – voltage [V]",
    tot_el_cons_KWh_current: "Electric consumption – current [A]"
};

// Generic grouped renderer for section 1A and 1B (group by parameter)
async function render_nlog_table(tableId, rows) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const tableBody = table.querySelector("tbody");
    if (!tableBody) return;

    tableBody.innerHTML = "";

    // Show empty state
    if (!rows || rows.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 4; // Enabled, Parameter, Unit name, Tagname
        td.className = "text-muted";
        td.textContent = "No data found.";
        tr.appendChild(td);
        tableBody.appendChild(tr);
        return;
    }

    // Group rows by parameter so each parameter is shown once
    const groups = {};
    rows.forEach(r => {
        const param = r.parameter ?? "";
        if (!groups[param]) groups[param] = [];
        groups[param].push(r);
    });

    let globalIdx = 0; // global row index for data attributes
    const populationPromises = [];

    Object.keys(groups).forEach(parameter => {
        const groupRows = groups[parameter];

        groupRows.forEach((r, idxInGroup) => {
            const componentName = r.component_name ?? "";
            const componentType = r.component_type ?? "";
            const tagname = r.tagname ?? "";
            const isParameterEnabled = groupRows.some(row => row.enabled !== false);

            const tr = document.createElement("tr");

            const tdEnabled = document.createElement("td");
            tdEnabled.className = "text-center";
            if (idxInGroup === 0) {
                const enabledCheckbox = document.createElement("input");
                enabledCheckbox.type = "checkbox";
                enabledCheckbox.className = "nlog-enabled-checkbox";
                enabledCheckbox.dataset.parameter = parameter;
                enabledCheckbox.checked = isParameterEnabled;
                tdEnabled.appendChild(enabledCheckbox);
            }
            tr.appendChild(tdEnabled);

            // Parameter cell: only filled for first row in the group
            const tdParam = document.createElement("td");
            tdParam.textContent = (idxInGroup === 0)
                ? (PARAM_DISPLAY_LABELS[parameter] || parameter)
                : "";
            tr.appendChild(tdParam);

            // Unit name: create dropdown instead of static text
            const tdName = document.createElement("td");

            const unitSelect = document.createElement("select");
            unitSelect.className = "form-control form-control-sm unit-name-select";
            unitSelect.style.minWidth = "160px";
            unitSelect.dataset.originalValue = componentName; // Store original for detecting changes

            // Add placeholder
            const placeholderOpt = document.createElement("option");
            placeholderOpt.value = "";
            placeholderOpt.textContent = "-- Select Unit --";
            unitSelect.appendChild(placeholderOpt);

            // Add all available units
            allAvailableUnits.forEach(unit => {
                const opt = document.createElement("option");
                opt.value = unit;
                opt.textContent = unit;
                unitSelect.appendChild(opt);
            });

            // Pre-select if unit name exists
            if (componentName) {
                unitSelect.value = componentName;
            }

            // Store unit name in data attribute for tagname validation
            unitSelect.dataset.componentName = componentName;

            tdName.appendChild(unitSelect);
            tr.appendChild(tdName);

            // Tagname (with dropdown)
            const tdTag = document.createElement("td");
            tdTag.className = "tagname-cell";

            const tagnameSelect = document.createElement("select");
            tagnameSelect.className = "form-control form-control-sm tagname-select";
            tagnameSelect.style.minWidth = "240px";
            tagnameSelect.dataset.rowIndex = String(globalIdx);
            tagnameSelect.dataset.componentName = componentName;
            tagnameSelect.dataset.componentType = componentType;
            tagnameSelect.dataset.parameter = parameter;
            tagnameSelect.dataset.originalValue = tagname;

            // Add placeholder
            const placeholderTag = document.createElement("option");
            placeholderTag.value = "";
            placeholderTag.textContent = "-- Select Tagname --";
            tagnameSelect.appendChild(placeholderTag);

            tdTag.appendChild(tagnameSelect);
            tr.appendChild(tdTag);

            tableBody.appendChild(tr);

            // Populate tagname dropdown from current unit
            populationPromises.push(populateTagnameDropdown(tagnameSelect, componentName, tagname));

            // Highlight on edit for unit select
            unitSelect.addEventListener("change", async function() {
                // Mark as edited if changed from original value
                const originalValue = this.dataset.originalValue ?? "";
                if (this.value !== originalValue) {
                    this.classList.add("edited");
                } else {
                    this.classList.remove("edited");
                }

                // Clear cache for new unit (safeguard)
                if (this.value && tagnameCache[this.value]) {
                    delete tagnameCache[this.value];
                }

                // Repopulate tagname dropdown for new unit
                await populateTagnameDropdown(tagnameSelect, this.value, "");
            });

            // Highlight on edit for tagname
            const originalTag = tagnameSelect.dataset.originalValue ?? "";
            const toggleEditedTagClass = function () {
                const currentValue = tagnameSelect.value;
                if (currentValue !== originalTag) {
                    tagnameSelect.classList.add("edited");
                } else {
                    tagnameSelect.classList.remove("edited");
                }
            };
            tagnameSelect.addEventListener("change", function() {
                toggleEditedTagClass();
            });

            globalIdx += 1;
        });
    });

    await Promise.all(populationPromises);
}
async function render_nlog_section2(tableId, rows) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");
    if (!thead || !tbody) return;

    thead.innerHTML = "";
    tbody.innerHTML = "";

    // Empty state
    if (!rows || rows.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 6; // enabled, nlog_parameter, parameter, component_name, tagname, doublet
        td.className = "text-muted";
        td.textContent = "No data found.";
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    // Build header: Enabled | NLOG parameter | Parameter | Component name | Tagname | Doublet
    const headerTr = document.createElement("tr");

    const thEnabled = document.createElement("th");
    thEnabled.textContent = "Enabled";
    thEnabled.style.width = "80px";
    thEnabled.style.minWidth = "80px";
    headerTr.appendChild(thEnabled);

    const thNlogParam = document.createElement("th");
    thNlogParam.textContent = "Parameter";
    headerTr.appendChild(thNlogParam);

    const thParam = document.createElement("th");
    thParam.textContent = "Value required";
    headerTr.appendChild(thParam);

    const thComp = document.createElement("th");
    thComp.textContent = "Unit name";
    headerTr.appendChild(thComp);

    const thTag = document.createElement("th");
    thTag.textContent = "Tagname";
    headerTr.appendChild(thTag);

    const thDoublet = document.createElement("th");
    thDoublet.textContent = "Doublet";
    headerTr.appendChild(thDoublet);

    thead.appendChild(headerTr);

    // Group by nlog_parameter, then by parameter
    const groups = {};
    rows.forEach(r => {
        const nlogParam = r.nlog_parameter ?? "";
        const param = r.parameter ?? "";
        if (!groups[nlogParam]) groups[nlogParam] = {};
        if (!groups[nlogParam][param]) groups[nlogParam][param] = [];
        groups[nlogParam][param].push(r);
    });

    let globalIdx = 0; // global row index for data attributes
    const populationPromises = [];

    Object.keys(groups).forEach(nlogParam => {
        const perParam = groups[nlogParam];
        let isFirstRowForNlogParam = true;

        Object.keys(perParam).forEach(parameter => {
            const groupRows = perParam[parameter];
            let isFirstRowForParameter = true;

            groupRows.forEach(r => {
                const componentName = r.component_name ?? "";
                const tagname = r.tagname ?? "";
                const doublet = r.doublet ?? "";
                const componentType = r.component_type ?? "";
                const isNlogParameterEnabled = Object.values(perParam)
                    .flat()
                    .some(row => row.enabled !== false);

                const tr = document.createElement("tr");

                const tdEnabled = document.createElement("td");
                tdEnabled.className = "text-center";
                if (isFirstRowForNlogParam) {
                    const enabledCheckbox = document.createElement("input");
                    enabledCheckbox.type = "checkbox";
                    enabledCheckbox.className = "nlog-enabled-checkbox";
                    enabledCheckbox.dataset.nlogParameter = nlogParam;
                    enabledCheckbox.checked = isNlogParameterEnabled;
                    tdEnabled.appendChild(enabledCheckbox);
                }
                tr.appendChild(tdEnabled);

                // Nicer label for NLOG parameter
                const niceNlogParam = PARAM_DISPLAY_LABELS[nlogParam] || nlogParam;
                const tdNlogParam = document.createElement("td");
                tdNlogParam.textContent = isFirstRowForNlogParam ? niceNlogParam : "";
                tr.appendChild(tdNlogParam);

                // Nicer label for parameter
                const niceParam = PARAM_DISPLAY_LABELS[parameter] || parameter;
                const tdParam = document.createElement("td");
                tdParam.textContent = isFirstRowForParameter ? niceParam : "";
                tr.appendChild(tdParam);


                // Component name: create dropdown instead of static text
                const tdComp = document.createElement("td");

                const unitSelectSec2 = document.createElement("select");
                unitSelectSec2.className = "form-control form-control-sm unit-name-select";
                unitSelectSec2.style.minWidth = "160px";
                unitSelectSec2.dataset.originalValue = componentName;

                // Add placeholder
                const placeholderOptSec2 = document.createElement("option");
                placeholderOptSec2.value = "";
                placeholderOptSec2.textContent = "-- Select Unit --";
                unitSelectSec2.appendChild(placeholderOptSec2);

                // Add all available units
                allAvailableUnits.forEach(unit => {
                    const opt = document.createElement("option");
                    opt.value = unit;
                    opt.textContent = unit;
                    unitSelectSec2.appendChild(opt);
                });

                // Pre-select if unit name exists
                if (componentName) {
                    unitSelectSec2.value = componentName;
                }

                unitSelectSec2.dataset.componentName = componentName;

                tdComp.appendChild(unitSelectSec2);
                tr.appendChild(tdComp);

                // Tagname dropdown
                const tdTag = document.createElement("td");
                tdTag.className = "tagname-cell";
                const tagnameSelectSec2 = document.createElement("select");
                tagnameSelectSec2.className = "form-control form-control-sm tagname-select";
                tagnameSelectSec2.style.minWidth = "250px";
                tagnameSelectSec2.dataset.rowIndex = String(globalIdx);
                tagnameSelectSec2.dataset.nlogParameter = nlogParam;
                tagnameSelectSec2.dataset.parameter = parameter;
                tagnameSelectSec2.dataset.componentName = componentName;
                tagnameSelectSec2.dataset.componentType = componentType;
                tagnameSelectSec2.dataset.field = "tagname";
                tagnameSelectSec2.dataset.originalValue = tagname;

                // Add placeholder
                const placeholderTagSec2 = document.createElement("option");
                placeholderTagSec2.value = "";
                placeholderTagSec2.textContent = "-- Select Tagname --";
                tagnameSelectSec2.appendChild(placeholderTagSec2);

                tdTag.appendChild(tagnameSelectSec2);
                tr.appendChild(tdTag);

                // Populate tagname dropdown from current unit
                populationPromises.push(populateTagnameDropdown(tagnameSelectSec2, componentName, tagname));

                // Doublet input
                const tdDoublet = document.createElement("td");
                tdDoublet.className = "doublet-cell";
                const inputDoublet = document.createElement("input");
                inputDoublet.type = "text";
                inputDoublet.className = "form-control form-control-sm doublet-input";
                inputDoublet.value = doublet;
                inputDoublet.dataset.rowIndex = String(globalIdx);
                inputDoublet.dataset.nlogParameter = nlogParam;
                inputDoublet.dataset.parameter = parameter;
                inputDoublet.dataset.componentName = componentName;
                inputDoublet.dataset.componentType = componentType;
                inputDoublet.dataset.field = "doublet";
                inputDoublet.dataset.originalValue = doublet;
                inputDoublet.style.minWidth = "60px";
                tdDoublet.appendChild(inputDoublet);
                tr.appendChild(tdDoublet);

                tbody.appendChild(tr);

                // Unit select change listener for section 2
                unitSelectSec2.addEventListener("change", async function() {
                    const originalValue = this.dataset.originalValue ?? "";
                    if (this.value !== originalValue) {
                        this.classList.add("edited");
                    } else {
                        this.classList.remove("edited");
                    }

                    // Clear cache for new unit (safeguard)
                    if (this.value && tagnameCache[this.value]) {
                        delete tagnameCache[this.value];
                    }

                    // Repopulate tagname dropdown for new unit
                    await populateTagnameDropdown(tagnameSelectSec2, this.value, "");
                });

                // Highlight on edit for tagname select and doublet input
                const originalTag = tagnameSelectSec2.dataset.originalValue ?? "";
                const toggleEditedTagClass = function () {
                    const currentValue = tagnameSelectSec2.value;
                    if (currentValue !== originalTag) {
                        tagnameSelectSec2.classList.add("edited");
                    } else {
                        tagnameSelectSec2.classList.remove("edited");
                    }
                };
                tagnameSelectSec2.addEventListener("change", function() {
                    toggleEditedTagClass();
                });

                // Highlight on edit for doublet
                const addEditHighlight = (inputEl) => {
                    const original = inputEl.dataset.originalValue ?? "";
                    const toggleEditedClass = function () {
                        const currentValue = inputEl.value;
                        if (currentValue !== original) {
                            inputEl.classList.add("edited");
                        } else {
                            inputEl.classList.remove("edited");
                        }
                    };
                    inputEl.addEventListener("input", toggleEditedClass);
                    inputEl.addEventListener("change", toggleEditedClass);
                };

                addEditHighlight(inputDoublet);

                isFirstRowForNlogParam = false;
                isFirstRowForParameter = false;
                globalIdx += 1;
            });
        });
    });

    await Promise.all(populationPromises);
}

// Collect all three sections into 3 arrays with the same shape as the render inputs
function collect_all_nlog_rows() {
    const rows_section1A = collect_section1_rows("nlog_section1A_table");
    const rows_section1B = collect_section1_rows("nlog_section1B_table");
    const rows_section2  = collect_section2_rows("nlog_section2_table");

    return {
        rows_section1A,
        rows_section1B,
        rows_section2
    };
}

// Collector for section 1 tables (1A and 1B) rendered by render_nlog_table
function collect_section1_rows(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return [];

    const tbody = table.querySelector("tbody");
    if (!tbody) return [];

    const rows = [];
    const trs = Array.from(tbody.querySelectorAll("tr"));
    let currentEnabled = true;

    trs.forEach(tr => {
        const tds = tr.querySelectorAll("td");
        if (tds.length === 0) return;

        // Skip "No data found." row
        if (tds[0].hasAttribute("colspan")) return;

        const enabledCheckbox = tr.querySelector("input.nlog-enabled-checkbox");
        if (enabledCheckbox) {
            currentEnabled = enabledCheckbox.checked;
        }

        // Get tagname from dropdown (NEW)
        const tagnameSelect = tr.querySelector("select.tagname-select");
        if (!tagnameSelect) return;

        // Get unit from dropdown
        const unitSelect = tr.querySelector("select.unit-name-select");
        const componentName = unitSelect?.value ?? tagnameSelect.dataset.componentName ?? "";

        const componentType = tagnameSelect.dataset.componentType ?? "";
        const parameter     = tagnameSelect.dataset.parameter ?? "";
        const tagname       = tagnameSelect.value ?? "";

        rows.push({
            component_name: componentName,
            component_type: componentType,
            parameter: parameter,
            tagname: tagname,
            enabled: currentEnabled
        });
    });

    return rows;
}

// Collector for section 2 table rendered by render_nlog_section2
function collect_section2_rows(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return [];

    const tbody = table.querySelector("tbody");
    if (!tbody) return [];

    const rows = [];
    const trs = Array.from(tbody.querySelectorAll("tr"));
    let currentEnabled = true;

    trs.forEach(tr => {
        const tds = tr.querySelectorAll("td");
        if (tds.length === 0) return;

        // Skip "No data found." row
        if (tds[0].hasAttribute("colspan")) return;

        const enabledCheckbox = tr.querySelector("input.nlog-enabled-checkbox");
        if (enabledCheckbox) {
            currentEnabled = enabledCheckbox.checked;
        }

        // Get tagname from dropdown (NEW)
        const tagnameSelect = tr.querySelector("select.tagname-select");
        const inputDoublet = tr.querySelector("input.doublet-input");
        if (!tagnameSelect || !inputDoublet) return;

        // Get unit from dropdown
        const unitSelect = tr.querySelector("select.unit-name-select");
        const componentName = unitSelect?.value ?? tagnameSelect.dataset.componentName ?? "";

        const nlogParam     = tagnameSelect.dataset.nlogParameter ?? "";
        const parameter     = tagnameSelect.dataset.parameter ?? "";
        const componentType = tagnameSelect.dataset.componentType ?? "";
        const tagname       = tagnameSelect.value ?? "";
        const doublet       = inputDoublet.value ?? "";

        rows.push({
            component_name: componentName,
            component_type: componentType,
            nlog_parameter: nlogParam,
            parameter: parameter,
            tagname: tagname,
            doublet: doublet,
            enabled: currentEnabled
        });
    });

    return rows;
}

// Cache for available tagnames per unit
const tagnameCache = {};

// Get available tagnames for a unit in format "tagname.category"
async function getUnitTagnames(unitName) {
    if (!unitName) return [];

    if (tagnameCache[unitName]) {
        return tagnameCache[unitName];
    }


    return new Promise((resolve) => {
        $.ajax({
            type: "POST",
            url: "/app/reportgenerator/get_unit_tagnames",
            contentType: "application/json",
            data: JSON.stringify({ unit_name: unitName }),
            dataType: "json",
            timeout: 60000,
            success: function (resp) {
                const tagnames = resp.tagnames || [];
                tagnameCache[unitName] = tagnames;
                resolve(tagnames);
            },
            error: function (xhr, status, error) {
                console.error("Error loading unit tagnames:", unitName, status, error);
                resolve([]);
            }
        });
    });
}

// Helper: Populate tagname dropdown from available tagnames for a unit
async function populateTagnameDropdown(select, unitName, currentValue = "") {
    if (!select) return;

    // Clear existing options (except placeholder)
    while (select.options.length > 1) {
        select.remove(1);
    }

    if (!unitName) {
        // No unit selected, disable dropdown
        select.disabled = true;
        return;
    }

    select.disabled = false;
    const tagnames = await getUnitTagnames(unitName);

    tagnames.forEach(tagname => {
        const opt = document.createElement("option");
        opt.value = tagname;
        opt.textContent = tagname;
        select.appendChild(opt);
    });

    // Re-select current value if it exists
    if (currentValue) {
        select.value = currentValue;
    }
}

// Validate all rows for proper unit and tagname dropdown selection
// GREEN: tagname dropdown has value AND unit dropdown has value
// RED: tagname dropdown is empty OR unit dropdown is empty
function validateAllRows() {
    // Process section 1 tables
    ["nlog_section1A_table", "nlog_section1B_table"].forEach(tableId => {
        const table = document.getElementById(tableId);
        if (!table) return;

        table.querySelectorAll("tr").forEach(tr => {
            const unitSelect = tr.querySelector("select.unit-name-select");
            const tagnameSelect = tr.querySelector("select.tagname-select");
            if (!unitSelect || !tagnameSelect) return;

            const hasUnit = unitSelect.value && unitSelect.value.trim() !== "";
            const hasTagname = tagnameSelect.value && tagnameSelect.value.trim() !== "";

            // Remove old classes
            unitSelect.classList.remove("valid-selection", "invalid-selection");
            tagnameSelect.classList.remove("valid-selection", "invalid-selection");

            if (hasUnit && hasTagname) {
                // Both selected: GREEN
                tagnameSelect.classList.add("valid-selection");
                unitSelect.classList.add("valid-selection");
            } else if (!hasUnit || !hasTagname) {
                // Either empty: RED
                if (!hasUnit) {
                    unitSelect.classList.add("invalid-selection");
                }
                if (!hasTagname) {
                    tagnameSelect.classList.add("invalid-selection");
                }
            }
        });
    });

    // Process section 2 table
    const table2 = document.getElementById("nlog_section2_table");
    if (table2) {
        table2.querySelectorAll("tr").forEach(tr => {
            const unitSelect = tr.querySelector("select.unit-name-select");
            const tagnameSelect = tr.querySelector("select.tagname-select");
            if (!unitSelect || !tagnameSelect) return;

            const hasUnit = unitSelect.value && unitSelect.value.trim() !== "";
            const hasTagname = tagnameSelect.value && tagnameSelect.value.trim() !== "";

            // Remove old classes
            unitSelect.classList.remove("valid-selection", "invalid-selection");
            tagnameSelect.classList.remove("valid-selection", "invalid-selection");

            if (hasUnit && hasTagname) {
                // Both selected: GREEN
                tagnameSelect.classList.add("valid-selection");
                unitSelect.classList.add("valid-selection");
            } else if (!hasUnit || !hasTagname) {
                // Either empty: RED
                if (!hasUnit) {
                    unitSelect.classList.add("invalid-selection");
                }
                if (!hasTagname) {
                    tagnameSelect.classList.add("invalid-selection");
                }
            }
        });
    }
}

// Validate a single tagname input in format "tagname.category"
async function validateTagnameInput(inputEl) {
    if (!inputEl) return;

    // Get unit from dropdown in the same row
    const row = inputEl.closest("tr");
    const unitSelect = row?.querySelector("select.unit-name-select");
    const unitName = unitSelect?.value || inputEl.dataset.componentName || "";

    const tagname = inputEl.value.trim();

    inputEl.classList.remove("valid", "invalid");

    if (!tagname) {
        return; // Empty is OK, no validation needed
    }

    // If no unit selected, mark as invalid
    if (!unitName) {
        inputEl.classList.add("invalid");
        return;
    }

    // Check format: must contain exactly one dot
    if (!tagname.includes('.')) {
        inputEl.classList.add("invalid");
        return;
    }

    const parts = tagname.split('.');
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
        inputEl.classList.add("invalid");
        return;
    }

    const [tagKey, category] = parts;
    const categoryLower = category.toLowerCase();

    // Validate that format is correct (category should be measured, filtered, or calculated)
    if (!['measured', 'filtered', 'calculated'].includes(categoryLower)) {
        inputEl.classList.add("invalid");
        return;
    }

    const availableTagnames = await getUnitTagnames(unitName);

    if (availableTagnames.includes(tagname)) {
        inputEl.classList.add("valid");
    } else {
        inputEl.classList.add("invalid");
    }
}

// Add real-time validation listeners to all tagname inputs
// (deprecated - now using dropdown validation via validateAllRows)
function attachValidationListeners() {
    // document.querySelectorAll("input.tagname-input").forEach(input => {
    //     // Validate on blur
    //     input.addEventListener("blur", function () {
    //         validateTagnameInput(this);
    //     });
    //
    //     // Validate on input (with debouncing)
    //     let timeout;
    //     input.addEventListener("input", function () {
    //         clearTimeout(timeout);
    //         timeout = setTimeout(() => {
    //             validateTagnameInput(this);
    //         }, 300);
    //     });
    // });
}

// Validate all tagnames and get warnings
async function validateAllTagnames() {
    const { rows_section1A, rows_section1B, rows_section2 } = collect_all_nlog_rows();

    return new Promise((resolve) => {
        $.ajax({
            type: "POST",
            url: "/app/reportgenerator/validate_nlog_tagnames",
            contentType: "application/json",
            dataType: "json",
            data: JSON.stringify({
                rows_section1A,
                rows_section1B,
                rows_section2
            }),
            success: function (resp) {
                resolve({
                    warnings: resp.warnings || [],
                    warnings_by_section: resp.warnings_by_section || {}
                });
            },
            error: function () {
                resolve({
                    warnings: [],
                    warnings_by_section: {}
                });
            }
        });
    });
}

// Show validation warnings modal
function showValidationWarnings(warnings, warningsBySection, onContinue) {
    const container = document.getElementById("warningsContainer");
    container.innerHTML = "";

    if (warnings.length === 0) {
        onContinue();
        return;
    }

    // Parse warning string: "Parameter: X | Unit: Y | Tagname: Z — Status"
    // Or new format: "Parameter: X | Unit: EMPTY | Status: ..." or "Parameter: X | Unit: Y | Status: ..."
    function parseWarning(warningStr) {
        // Try old format first: "Parameter: X | Unit: Y | Tagname: Z — Status"
        let match = warningStr.match(/Parameter:\s*([^|]+)\s*\|\s*Unit:\s*([^|]+)\s*\|\s*Tagname:\s*([^—]+)\s*—\s*(.+)/);
        if (match) {
            return {
                parameter: match[1].trim(),
                unit: match[2].trim(),
                tagname: match[3].trim(),
                status: match[4].trim()
            };
        }

        // Try new format: "Parameter: X | Unit: Y | Status: ..."
        match = warningStr.match(/Parameter:\s*([^|]+)\s*\|\s*Unit:\s*([^|]+)\s*\|\s*Status:\s*(.+)/);
        if (match) {
            return {
                parameter: match[1].trim(),
                unit: match[2].trim(),
                tagname: "", // Empty for new format
                status: match[3].trim()
            };
        }

        return null;
    }

    // Create sections if warnings exist for that section
    const sections = [
        {
            key: "production_well",
            title: "Kenmerken van productieput / Production well characteristics",
            warnings: warningsBySection.production_well || [],
            columns: ["Parameter", "Unit name", "Tagname"]
        },
        {
            key: "injection_well",
            title: "Kenmerken van injectieput / Injection well characteristics",
            warnings: warningsBySection.injection_well || [],
            columns: ["Parameter", "Unit name", "Tagname"]
        },
        {
            key: "plant",
            title: "Kenmerken van de installatie / Characteristics of the plant",
            warnings: warningsBySection.plant || [],
            columns: ["Parameter", "Unit name", "Tagname"]
        }
    ];

    sections.forEach(section => {
        if (section.warnings.length > 0) {
            // Create section header
            const sectionHeader = document.createElement("h6");
            sectionHeader.className = "mt-4 mb-3 font-weight-bold";
            sectionHeader.setAttribute("style", "color: #333 !important;");
            sectionHeader.textContent = section.title;
            container.appendChild(sectionHeader);

            // Create table for this section
            const table = document.createElement("table");
            table.className = "table table-sm table-striped";
            table.setAttribute("style", "color: #333 !important");

            // Create table header
            const thead = document.createElement("thead");
            const headerRow = document.createElement("tr");
            section.columns.forEach(col => {
                const th = document.createElement("th");
                th.setAttribute("style", "background-color: #f5f5f5 !important; color: #333 !important; font-weight: 600 !important;");
                th.textContent = col;
                headerRow.appendChild(th);
            });
            const warningTh = document.createElement("th");
            warningTh.setAttribute("style", "background-color: #f5f5f5 !important; color: #333 !important; font-weight: 600 !important;");
            warningTh.textContent = "Warning";
            headerRow.appendChild(warningTh);
            thead.appendChild(headerRow);
            table.appendChild(thead);

            // Create table body with warnings
            const tbody = document.createElement("tbody");
            tbody.setAttribute("style", "color: #333 !important;");
            section.warnings.forEach(warning => {
                const parsed = parseWarning(warning);
                if (parsed) {
                    const row = document.createElement("tr");
                    row.setAttribute("style", "color: #333 !important;");
                    row.className = "align-middle";

                    const tdParam = document.createElement("td");
                    tdParam.textContent = parsed.parameter;
                    tdParam.setAttribute("style", "color: #333 !important;");
                    row.appendChild(tdParam);

                    const tdUnit = document.createElement("td");
                    tdUnit.textContent = parsed.unit;
                    tdUnit.setAttribute("style", "color: #333 !important;");
                    row.appendChild(tdUnit);

                    const tdTagname = document.createElement("td");
                    tdTagname.textContent = parsed.tagname;
                    tdTagname.setAttribute("style", "color: #dc3545 !important; font-weight: bold !important;");
                    row.appendChild(tdTagname);

                    const tdStatus = document.createElement("td");
                    tdStatus.textContent = parsed.status;
                    tdStatus.setAttribute("style", "color: #dc3545 !important;");
                    row.appendChild(tdStatus);

                    tbody.appendChild(row);
                }
            });
            table.appendChild(tbody);
            container.appendChild(table);
        }
    });

    // Set up continue button
    const confirmBtn = document.getElementById("confirmActionBtn");
    confirmBtn.onclick = function () {
        $("#validationWarningsModal").modal("hide");
        onContinue();
    };

    $("#validationWarningsModal").modal("show");
}

async function save_nlog_tagnames() {
    const result = await validateAllTagnames();
    const warnings = result.warnings;
    const warningsBySection = result.warnings_by_section;

    const performSave = () => {
        const { rows_section1A, rows_section1B, rows_section2 } = collect_all_nlog_rows();

        // Check that all rows have unit selected (safeguard)
        const allRows = rows_section1A.concat(rows_section1B, rows_section2);
        const missingUnit = allRows.find(row => row.enabled !== false && (!row.component_name || row.component_name.trim() === ""));
        if (missingUnit) {
            alert("All rows must have a Unit Name selected.");
            return;
        }

        const inputs = {
            ProjectName: document.getElementById("select_project").value,
            NlogPeriod: document.getElementById("nlog_period").value,
            LicenseHolder: document.getElementById("nlog_license_holder").value,
            rows_section1A: rows_section1A,
            rows_section1B: rows_section1B,
            rows_section2: rows_section2
        };

        $.ajax({
            type: "POST",
            url: "/app/reportgenerator/save_nlog_settings",
            contentType: "application/json",
            data: JSON.stringify(inputs),

            success: function (resp) {
                alert("NLOG settings saved successfully!");
            },

            error: function (xhr, status, error) {
                console.error("Error saving NLOG settings:", error);
                alert("Error saving NLOG settings.");
            }
        });
    };

    showValidationWarnings(warnings, warningsBySection, performSave);
}
function showResetNlogSettingsConfirmation() {
    const confirmBtn = document.getElementById("confirmResetNlogSettingsBtn");
    if (!confirmBtn) return;

    confirmBtn.onclick = reset_nlog_settings_to_defaults;
    $("#resetNlogSettingsModal").modal("show");
}

async function reset_nlog_settings_to_defaults() {
    const confirmBtn = document.getElementById("confirmResetNlogSettingsBtn");
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="fa fa-spinner fa-spin mr-1" aria-hidden="true"></i> Resetting...';
    }

    nlogTablesLoaded = false;
    nlogTablesLoading = true;
    setNlogAdvancedButtonState("loading");

    try {
        const resetInputs = {
            ProjectName: document.getElementById("select_project").value
        };
        const resp = await $.ajax({
            type: "POST",
            url: "/app/reportgenerator/reset_nlog_settings",
            contentType: "application/json",
            dataType: "json",
            data: JSON.stringify(resetInputs),
            timeout: 60000
        });

        advancedNLOGSection.style.display = 'none';

        await show_nlog_tagnames();

        nlogTablesLoaded = true;
        setNlogAdvancedButtonState("ready");
        alert("NLOG settings reset to default values.");
    } catch (error) {
        console.error("Error resetting NLOG settings:", error);
        nlogTablesLoaded = false;
        setNlogAdvancedButtonState("error");
        alert("Error resetting or reloading NLOG settings.");
    } finally {
        nlogTablesLoading = false;
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = "Continue Anyway";
        }
        $("#resetNlogSettingsModal").modal("hide");
    }
}
