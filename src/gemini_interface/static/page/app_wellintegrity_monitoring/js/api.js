load_plant()

function load_plant() {
    const fieldID = $('#select_project').val();
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_plant',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {
            get_well_list();
        },
        error: function (xhr) {
            console.error('Error loading plant for WIMS:', xhr);
            if (typeof showErrorMessage === 'function') {
                var msg = (xhr.responseJSON && xhr.responseJSON.error)
                    ? xhr.responseJSON.error
                    : 'Failed to load plant. Well list may be unavailable.';
                showErrorMessage(msg);
            }
        }
    });
}

function get_well_list() {
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_well_list',
        contentType: 'application/json',
        data: JSON.stringify(),
        success: function (data) {
            const select = document.getElementById('select_well');
            select.options.length = 1;
            
            data.forEach(well => {
                select.options[select.options.length] = new Option(well, well);
            });
        }
    });
}

window.processedLogsAvailable = [];
window.selectedProcessedLogs = [];
const PROCESSED_LOG_NON_PLOT_COLUMNS = [
    'Tally Joint No.',
    'Seq. No.',
    'Tally Seq. No.',
    'Top Depth [m]',
    'Bottom Depth [m]',
    'Length [m]',
    'Nominal IR [inch]',
    'Nominal OR [inch]',
    'Max. Penetration Depth [m]',
    'Min. Penetration Depth [m]',
    'Ovality [%]'
];

function getProcessedLogPenetrationDepthKind(selectedColumn) {
    const col = (selectedColumn || '').trim();
    if (/^Min\./i.test(col)) return 'min';
    if (/^Max\./i.test(col)) return 'max';
    return null;
}

function getProcessedLogPenetrationDepth(row, kind) {
    if (kind === 'min') {
        return row['Min. Penetration Depth [m]'];
    }
    if (kind === 'max') {
        return row['Max. Penetration Depth [m]'];
    }
    return null;
}

function buildProcessedLogHoverTemplate(selectedColumn, depthKind) {
    let template =
        'Tally Seq. No.: %{x}<br>' +
        'Tally Joint No.: %{customdata[0]}<br>' +
        'Seq. No.: %{customdata[8]}<br>' +
        selectedColumn + ': %{y}<br>';
    if (depthKind === 'min') {
        template += 'Min. Penetration Depth [m]: %{customdata[6]}<br>';
    } else if (depthKind === 'max') {
        template += 'Max. Penetration Depth [m]: %{customdata[6]}<br>';
    }
    template +=
        'Nominal IR [inch]: %{customdata[4]}<br>' +
        'Nominal OR [inch]: %{customdata[5]}<br>' +
        'Ovality [%]: %{customdata[7]}<br>' +
        'Top Depth [m]: %{customdata[1]}<br>' +
        'Bottom Depth [m]: %{customdata[2]}<br>' +
        'Length [m]: %{customdata[3]}<extra>%{fullData.name}</extra>';
    return template;
}
window.logDateByName = {};

$('#select_well').off('change').on('change', function () {
    const well_name = $('#select_well').val();
    resetAnnulusMonitorAlarms();
    window.lastProcessedLogsData = null; // clear so dropdown uses get_log_status for this well
    window.logDateByName = {};
    if (!well_name) {
        hideDataUI();
        $('#processed_logs_panel').hide();
        $('#view_processed_log_block').hide();
        hideProcessedLogSection();
        Plotly.purge('processed_log_chart');
        return;
    }
    // Show Well Logs when well is selected; show View processed log + panel only when there are processed logs
    showDataUI();
    loadEspGeometry();
    loadWellLogs();
    checkForSavedSchematics();
    resetDashboardForWell(well_name);
    setTimeout(syncProcessedLogPanelHeight, 150);
});

function getSelectedProcessedLogs() {
    return ($('#processed_log_dropdown_menu input.processed-log-checkbox:checked')
        .map(function() { return this.value; })
        .get());
}

function updateProcessedLogDropdownLabel() {
    const selected = getSelectedProcessedLogs();
    const text = selected.length === 0
        ? 'Select processed logs'
        : (selected.length === 1 ? selected[0] : `${selected.length} logs selected`);
    $('#processed_log_dropdown_toggle').text(text);
    window.selectedProcessedLogs = selected;
}

function renderProcessedLogCheckboxDropdown(processedLogs, preselectedLogs) {
    const $menu = $('#processed_log_dropdown_menu');
    const selectedSet = new Set(preselectedLogs || []);
    $menu.empty();

    processedLogs.forEach(function(logName) {
        const isChecked = selectedSet.has(logName) ? 'checked' : '';
        const html = `<label class="processed-log-option"><input type="checkbox" class="processed-log-checkbox" value="${logName}" ${isChecked}><span>${logName}</span></label>`;
        $menu.append(html);
    });
    updateProcessedLogDropdownLabel();
}

$('#processed_log_dropdown_toggle').off('click').on('click', function(e) {
    e.preventDefault();
    $('#processed_log_dropdown_menu').toggleClass('show');
});

$(document).off('mousedown.processedLogDropdown').on('mousedown.processedLogDropdown', function(e) {
    const $dropdown = $('#processed_log_dropdown');
    if ($dropdown.length && !$dropdown.is(e.target) && $dropdown.has(e.target).length === 0) {
        $('#processed_log_dropdown_menu').removeClass('show');
    }
});

$(document).off('change.processedLogCheckbox').on('change.processedLogCheckbox', '#processed_log_dropdown_menu input.processed-log-checkbox', function() {
    updateProcessedLogDropdownLabel();
    const selectedLogs = getSelectedProcessedLogs();
    if (selectedLogs.length === 0) {
        Plotly.purge('processed_log_chart');
        return;
    }
    const missing = selectedLogs.filter(l => !window.lastProcessedLogsData || !window.lastProcessedLogsData[l]);
    if (missing.length > 0) {
        loadProcessedLogs(missing);
    } else {
        renderProcessedLogChart();
    }
});

$('#processed_log_column_select').off('change').on('change', function() {
    renderProcessedLogChart();
});

$('#saved_schematics_select').off('change').on('change', function() {
    const well_name = $('#select_well').val();
    const schematic_filename = $(this).val();
    const schematic_name = $(this).find('option:selected').text();
    const $subcards = $('#wims_subcards_container');
    const $dashImg = $('#dashboard_schematic_image_output');
    wimsAnnulusMonitors = [];
    wimsCachedDrawnItems = [];
    wimsCachedSchematicData = null;
    resetAnnulusMonitorAlarms();
    displayWimsAnnulusMonitors();
    if (!schematic_filename) {
        $subcards.hide();
        $('#dashboard_well_name').text('Well');
        $dashImg.html('<span style="color:#888;">Select a schematic to view.</span>');
        resetDashboardManualState();
        renderDashboardManualSections();
        return;
    }
    if (!well_name) {
        $subcards.hide();
        $dashImg.html('<span class="text-danger">Select a well first.</span>');
        return;
    }
    $subcards.show();
    $dashImg.html('<span style="color:#888;">Loading schematic...</span>');
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_schematic',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, schematic_filename: schematic_filename }),
        success: function(schematicData) {
            wimsCachedSchematicData = schematicData;
            loadEspGeometry();
            // Load KPI dashboard manual fields for this well + schematic
            $('#dashboard_well_name').text(schematic_name);
            loadDashboard();
            // Load WIMS panel first (from file) so it works even when schematic server is down
            loadWimsPanel(function(panelData) {
                $dashImg.html('<span style="color:#888;">Generating schematic...</span>');
                var payload = Object.assign({}, schematicData);
                if (panelData && (panelData.primary_barrier_elements || panelData.secondary_barrier_elements)) {
                    payload.primary_barrier_elements = panelData.primary_barrier_elements || [];
                    payload.secondary_barrier_elements = panelData.secondary_barrier_elements || [];
                }
                $.ajax({
                    url: '/app/wellintegrity/generate_schematic_image_with_barriers',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify(payload),
                    success: function(response) {
                        if (response.image_base64) {
                            wimsCachedDrawnItems = response.drawn_items || [];
                            var schematicImgHtml = '<img src="data:image/png;base64,' + response.image_base64 + '" style="max-width:100%; height:auto; display:block;" />';
                            $dashImg.html(schematicImgHtml);
                        } else if (response.error) {
                            $dashImg.html('<span class="text-danger">' + response.error + '</span>');
                        } else {
                            $dashImg.html('<span class="text-danger">No schematic returned.</span>');
                        }
                    },
                    error: function(xhr) {
                        const msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error generating schematic.';
                        $dashImg.html('<span class="text-danger">' + msg + '</span>');
                    }
                });
            });
        },
        error: function(xhr) {
            const msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error loading schematic.';
            $dashImg.html('<span class="text-danger">' + msg + '</span>');
        }
    });
});

function checkForSavedSchematics() {
    const well_name = $('#select_well').val();
    
    if (!well_name) {
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_saved_schematics',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function (data) {
            const $select = $('#saved_schematics_select');
            $select.empty().append('<option value="">Select a saved schematic...</option>');
            
            if (data.length > 0) {
                data.forEach(schematic => {
                    $select.append(`<option value="${schematic.filename}">${schematic.name}</option>`);
                });
            } else {
                $select.append('<option value="">No saved schematics found</option>');
            }
        },
        error: function (xhr) {
            console.error('Error loading saved schematics:', xhr);
        }
    });
}


function showDataUI() {
    $('#wall_thickness_forecast_card').show();
    $('#erosion_card').show();
    $('#well_data_section').show();
    $('#dashboard_card').show();
    $('#forecasting_status_message').text('');
    $('#forecasting_optimize_result_section').hide();
    $('#forecasting_predict_result_section').hide();
    $('#forecasting_years_to_min_result_section').hide();
    // -- gate Run until we confirm optimized params exist ---------------
    setForecastRunEnabled(false);
    refreshOptimizationStatus();
}

function hideDataUI() {
    $('#wall_thickness_forecast_card').hide();
    $('#erosion_card').hide();
    $('#dashboard_card').hide();
}

/* ───── Erosion panel ───── */

var erosionWellType = 'productionwell';

var EROSION_COMPONENT_TYPES = [
    { value: 'intake', label: 'Intake' },
    { value: 'pump', label: 'Pump' },
    { value: 'seal', label: 'Seal' },
    { value: 'protector', label: 'Protector' },
    { value: 'motor', label: 'Motor' },
    { value: 'cable_protector', label: 'Cable protector' },
    { value: 'custom', label: 'Custom' }
];

function toggleErosionModelParams() {
    var model = $('#erosion_model_select').val();
    $('#erosion_params_dnv').toggle(model === 'DNVGL');
    $('#erosion_params_oka').toggle(model === 'OKA');
    $('#erosion_params_tulsa').toggle(model === 'E/CRC Tulsa');
}

function buildEspComponentTypeSelect(selected) {
    var html = '';
    EROSION_COMPONENT_TYPES.forEach(function(opt) {
        var sel = opt.value === selected ? ' selected' : '';
        html += '<option value="' + opt.value + '"' + sel + '>' + opt.label + '</option>';
    });
    return html;
}

function addEspComponentRow(comp) {
    comp = comp || {};
    var ctype = comp.component_type || 'custom';
    var name = comp.name || '';
    var length_m = comp.length_m != null ? comp.length_m : '';
    var od_inch = comp.od_inch != null ? comp.od_inch : '';
    var row = '<tr>' +
        '<td><select class="form-control form-control-sm erosion-esp-type">' +
        buildEspComponentTypeSelect(ctype) + '</select></td>' +
        '<td><input type="text" class="form-control form-control-sm erosion-esp-name" value="' + name + '"></td>' +
        '<td><input type="number" class="form-control form-control-sm erosion-esp-length" step="0.1" value="' + length_m + '"></td>' +
        '<td><input type="number" class="form-control form-control-sm erosion-esp-od" step="0.01" value="' + od_inch + '"></td>' +
        '<td><button type="button" class="btn btn-default btn-sm erosion-remove-row" title="Remove">&times;</button></td>' +
        '</tr>';
    $('#erosion_esp_components_tbody').append(row);
}

function renderEspGeometryTable(components) {
    $('#erosion_esp_components_tbody').empty();
    if (!components || !components.length) {
        EROSION_COMPONENT_TYPES.slice(0, 5).forEach(function(opt) {
            addEspComponentRow({
                component_type: opt.value,
                name: opt.label,
                length_m: 0,
                od_inch: 0
            });
        });
        return;
    }
    components.forEach(function(comp) {
        addEspComponentRow(comp);
    });
}

function collectEspGeometryFromTable() {
    var components = [];
    $('#erosion_esp_components_tbody tr').each(function() {
        var $row = $(this);
        var ctype = $row.find('.erosion-esp-type').val();
        var label = EROSION_COMPONENT_TYPES.find(function(o) { return o.value === ctype; });
        var name = $row.find('.erosion-esp-name').val() || (label ? label.label : ctype);
        components.push({
            component_type: ctype,
            name: name,
            length_m: parseFloat($row.find('.erosion-esp-length').val()) || 0,
            od_inch: parseFloat($row.find('.erosion-esp-od').val()) || 0,
            flow_path: 'esp_joint_annulus'
        });
    });
    return {
        setting_depth_m: null,
        production_tubing_id_inch: null,
        reference: 'intake_bottom',
        components: components
    };
}

function readProductionTubingIdInch() {
    var tubingId = parseFloat($('#erosion_tubing_id_inch').val());
    if (!isNaN(tubingId) && tubingId > 0) {
        return tubingId;
    }
    return null;
}

function loadEspGeometry() {
    var well_name = $('#select_well').val();
    if (!well_name) return;

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_esp_geometry',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(data) {
            erosionWellType = data.well_type || 'productionwell';
            if (erosionWellType === 'productionwell') {
                $('#erosion_esp_geometry_section').show();
                var depth = data.plant_esp_depth_m;
                $('#erosion_plant_esp_depth').text(
                    depth != null && !isNaN(depth) ? Number(depth).toFixed(1) : '—'
                );
                if (data.production_casing_id_inch != null && !isNaN(data.production_casing_id_inch)) {
                    $('#erosion_tally_casing_id').text(Number(data.production_casing_id_inch).toFixed(3));
                } else {
                    $('#erosion_tally_casing_id').text('—');
                }
                if (data.production_tubing_id_inch != null && !isNaN(data.production_tubing_id_inch)) {
                    $('#erosion_tubing_id_inch').val(Number(data.production_tubing_id_inch).toFixed(3));
                } else if (data.esp_geometry && data.esp_geometry.production_tubing_id_inch != null) {
                    $('#erosion_tubing_id_inch').val(
                        Number(data.esp_geometry.production_tubing_id_inch).toFixed(3)
                    );
                } else {
                    $('#erosion_tubing_id_inch').val('');
                }
                renderEspGeometryTable((data.esp_geometry && data.esp_geometry.components) || []);
            } else {
                $('#erosion_esp_geometry_section').hide();
            }
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Failed to load ESP geometry';
            $('#erosion_status_message').text(msg);
        }
    });
}

function saveEspGeometry() {
    var well_name = $('#select_well').val();
    if (!well_name) return;

    var geometry = collectEspGeometryFromTable();
    geometry.production_tubing_id_inch = readProductionTubingIdInch();
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_esp_geometry',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, esp_geometry: geometry }),
        success: function() {
            $('#erosion_status_message').text('ESP geometry saved.');
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Save failed';
            $('#erosion_status_message').text(msg);
        }
    });
}

function collectErosionParams() {
    var model = $('#erosion_model_select').val();
    var params = {
        rho_fluid_kgm3: parseFloat($('#erosion_rho_fluid').val()) || 1000,
        flow_stat: $('#erosion_flow_stat').val() || 'mean'
    };
    if (model === 'DNVGL') {
        params.alpha_deg = parseFloat($('#erosion_alpha_deg').val()) || 90;
        params.mater = $('#erosion_mater').val();
    } else if (model === 'OKA') {
        params.alpha_deg = parseFloat($('#erosion_oka_alpha').val()) || 90;
        params.Hv_gpa = parseFloat($('#erosion_hv_gpa').val()) || 1.0;
        params.mater_particle = $('#erosion_mater_particle').val();
        params.diameter_particle_mm = parseFloat($('#erosion_diameter_particle_mm').val()) || 0.1;
    } else if (model === 'E/CRC Tulsa') {
        params.alpha_deg = parseFloat($('#erosion_tulsa_alpha').val()) || 90;
        params.Hv_gpa = parseFloat($('#erosion_tulsa_hv').val()) || 1.0;
        params.fs = parseFloat($('#erosion_fs').val()) || 0.5;
        params.rho_pipe_kgm3 = parseFloat($('#erosion_rho_pipe').val()) || 7800;
    }
    return params;
}

function buildErosionResultTableHtml(rows, options) {
    var isApi = options.isApi;
    var wellType = options.wellType;
    var title = options.title;
    var idColumnHeader = options.idColumnHeader;
    var idField = options.idField || 'joint_id_inch';
    var showComponent = options.showComponent || false;

    var html = '<div class="mb-2 mt-3" style="color: #aaa; font-size: 0.85rem;">' + title + '</div>';
    html += '<table class="table erosion-table"><thead><tr>';
    if (showComponent) {
        html += '<th>Component</th>';
    }
    html += '<th>Joint</th><th>' + idColumnHeader + '</th>' +
        '<th>Top MD [m]</th><th>Bottom MD [m]</th>' +
        '<th>Flow area [mm²]</th><th>Flow [m³/h]</th>';
    if (isApi) {
        html += '<th>Flow velocity [m/s]</th><th>API limit [m/s]</th><th>Status</th>';
    } else {
        html += '<th>Rate [mm/yr]</th>';
    }
    html += '</tr></thead><tbody>';

    rows.forEach(function(row) {
        var rateCell = '—';
        var apiLimitCell = '—';
        var statusCell = '—';
        var flowVelocity = row.flow_velocity_ms != null ? row.flow_velocity_ms : row.erosion_velocity_ms;
        if (isApi) {
            if (flowVelocity != null) {
                rateCell = Number(flowVelocity).toFixed(4);
            }
            if (row.api_erosion_limit_velocity_ms != null) {
                apiLimitCell = Number(row.api_erosion_limit_velocity_ms).toFixed(4);
            }
            if (row.exceeds_api_limit === true) {
                statusCell = '<span style="color: #e57373;">Exceeds limit</span>';
            } else if (row.exceeds_api_limit === false) {
                statusCell = '<span style="color: #4caf82;">OK</span>';
            }
        } else if (row.erosion_rate_mm_yr != null) {
            rateCell = Number(row.erosion_rate_mm_yr).toFixed(4);
        }

        html += '<tr>';
        if (showComponent) {
            html += '<td>' + (row.name || row.component_type || '—') + '</td>';
        }
        html += '<td>' + (row.joint != null ? row.joint : '—') + '</td>' +
            '<td>' + (row[idField] != null ? Number(row[idField]).toFixed(3) : '—') + '</td>' +
            '<td>' + (row.top_md_m != null ? Number(row.top_md_m).toFixed(1) : '') + '</td>' +
            '<td>' + (row.bottom_md_m != null ? Number(row.bottom_md_m).toFixed(1) : '') + '</td>' +
            '<td>' + (row.flow_area_mm2 != null
                ? Number(row.flow_area_mm2).toFixed(1)
                : '') + '</td>' +
            '<td>' + (row.flow_m3h != null ? Number(row.flow_m3h).toFixed(2) : '') + '</td>';
        if (isApi) {
            html += '<td>' + rateCell + '</td>' +
                '<td>' + apiLimitCell + '</td>' +
                '<td>' + statusCell + '</td>';
        } else {
            html += '<td>' + rateCell + '</td>';
        }
        html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
}

function displayErosionResult(data) {
    var summary = data.summary || {};
    var model = $('#erosion_model_select').val();
    var isApi = model === 'API';
    var wellType = data.well_type || erosionWellType || 'productionwell';

    var jointRows = [];
    var espAnnulusRows = [];
    var tubingAboveEspRows = [];
    if (wellType === 'productionwell') {
        jointRows = summary.joints_below_esp_intake || [];
        espAnnulusRows = summary.esp_annulus_segments || [];
        tubingAboveEspRows = summary.tubing_above_esp_joints || [];
    } else {
        jointRows = summary.injection_joints || [];
    }

    var plotRows = wellType === 'productionwell'
        ? jointRows.concat(espAnnulusRows).concat(tubingAboveEspRows)
        : jointRows;

    var summaryText = 'Tubing below intake: ' + jointRows.length;
    if (wellType === 'productionwell') {
        summaryText += ' | ESP annulus: ' + espAnnulusRows.length;
        summaryText += ' | Tally above ESP: ' + tubingAboveEspRows.length;
    }
    if (isApi && summary.api_erosion_limit_velocity_ms != null) {
        summaryText += ' | API velocity limit: ' +
            Number(summary.api_erosion_limit_velocity_ms).toFixed(4) + ' m/s';
    }
    if (isApi && summary.joints_exceeding_api_limit_count != null) {
        summaryText += ' | Exceeds limit: ' + summary.joints_exceeding_api_limit_count +
            ' joint(s)';
    }
    if (wellType === 'productionwell') {
        if (summary.max_erosion_below_esp_intake_mm_yr != null && !isApi) {
            summaryText += ' | Max below ESP intake: ' +
                Number(summary.max_erosion_below_esp_intake_mm_yr).toFixed(4) + ' mm/yr';
        }
        if (isApi && summary.max_flow_velocity_below_esp_intake_ms != null) {
            summaryText += ' | Max flow velocity below ESP intake: ' +
                Number(summary.max_flow_velocity_below_esp_intake_ms).toFixed(4) + ' m/s';
        }
        if (isApi && summary.max_flow_velocity_esp_annulus_ms != null) {
            summaryText += ' | Max ESP annulus flow velocity: ' +
                Number(summary.max_flow_velocity_esp_annulus_ms).toFixed(4) + ' m/s';
        }
        if (!isApi && summary.max_erosion_esp_annulus_mm_yr != null) {
            summaryText += ' | Max ESP annulus erosion: ' +
                Number(summary.max_erosion_esp_annulus_mm_yr).toFixed(4) + ' mm/yr';
        }
        if (!isApi && summary.tubing_interior_average_mm_yr != null) {
            summaryText += ' | Avg tubing interior: ' +
                Number(summary.tubing_interior_average_mm_yr).toFixed(4) + ' mm/yr';
        } else if (isApi && summary.tubing_interior_average_flow_velocity_ms != null) {
            summaryText += ' | Avg tubing interior flow velocity: ' +
                Number(summary.tubing_interior_average_flow_velocity_ms).toFixed(4) + ' m/s';
        }
    } else if (isApi && summary.max_flow_velocity_ms != null) {
        summaryText += ' | Max flow velocity: ' +
            Number(summary.max_flow_velocity_ms).toFixed(4) + ' m/s';
    } else if (!isApi && summary.max_erosion_rate_mm_yr != null) {
        summaryText += ' | Max erosion rate: ' + Number(summary.max_erosion_rate_mm_yr).toFixed(4) + ' mm/yr';
    }
    if (data.esp_depth_m != null) {
        summaryText += ' | ESP intake: ' + Number(data.esp_depth_m).toFixed(1) + ' m';
    }
    $('#erosion_results_summary').text(summaryText);

    var html = '';
    if (wellType === 'productionwell') {
        html += buildErosionResultTableHtml(jointRows, {
            isApi: isApi,
            wellType: wellType,
            title: 'Joints below ESP intake (production tubing interior)',
            idColumnHeader: 'Tubing ID [inch]',
            idField: 'tubing_id_inch'
        });
        html += buildErosionResultTableHtml(espAnnulusRows, {
            isApi: isApi,
            wellType: wellType,
            title: 'ESP annulus (tally joint ID vs ESP component OD)',
            idColumnHeader: 'Joint ID [inch]',
            idField: 'joint_id_inch',
            showComponent: true
        });
        html += buildErosionResultTableHtml(tubingAboveEspRows, {
            isApi: isApi,
            wellType: wellType,
            title: 'Tally joints above ESP (tubing interior)',
            idColumnHeader: 'Joint ID [inch]',
            idField: 'joint_id_inch'
        });
    } else {
        html += buildErosionResultTableHtml(jointRows, {
            isApi: isApi,
            wellType: wellType,
            title: 'Per-joint erosion (tubular interior)',
            idColumnHeader: 'Joint ID [inch]',
            idField: 'joint_id_inch'
        });
    }

    if (wellType === 'productionwell') {
        var tubingSummary = '';
        if (!isApi && summary.tubing_interior_average_mm_yr != null) {
            tubingSummary = 'Average production tubing interior erosion: ' +
                Number(summary.tubing_interior_average_mm_yr).toFixed(4) + ' mm/yr' +
                ' (' + (summary.tubing_interior_segment_count || 0) + ' segments)';
        } else if (isApi && summary.tubing_interior_average_flow_velocity_ms != null) {
            var tubingAvg = Number(summary.tubing_interior_average_flow_velocity_ms);
            var tubingStatus = '';
            if (summary.api_erosion_limit_velocity_ms != null) {
                tubingStatus = tubingAvg > Number(summary.api_erosion_limit_velocity_ms)
                    ? ' (exceeds API limit)'
                    : ' (within API limit)';
            }
            tubingSummary = 'Average production tubing interior flow velocity: ' +
                tubingAvg.toFixed(4) + ' m/s' + tubingStatus +
                ' (' + (summary.tubing_interior_segment_count || 0) + ' segments)';
        }
        if (tubingSummary) {
            html += '<div class="mt-2" style="color: #ccc; font-size: 0.85rem;">' + tubingSummary + '</div>';
        }
    }

    $('#erosion_results_table').html(html);
    $('#erosion_results_section').show();

    if (typeof Plotly !== 'undefined' && plotRows.length) {
        var depths = [];
        var values = [];
        plotRows.forEach(function(row) {
            var mid = ((row.top_md_m || 0) + (row.bottom_md_m || 0)) / 2;
            depths.push(mid);
            var flowVelocity = row.flow_velocity_ms != null ? row.flow_velocity_ms : row.erosion_velocity_ms;
            if (isApi && flowVelocity != null) {
                values.push(flowVelocity);
            } else if (row.erosion_rate_mm_yr != null) {
                values.push(row.erosion_rate_mm_yr);
            } else {
                values.push(0);
            }
        });
        var yTitle = isApi ? 'Velocity [m/s]' : 'Erosion rate [mm/yr]';
        var plotTitle = isApi
            ? (wellType === 'productionwell'
                ? 'Flow velocity vs API limit (tubing + ESP annulus)'
                : 'Flow velocity vs API limit')
            : (wellType === 'productionwell'
                ? 'Erosion (tubing below intake + ESP annulus)'
                : 'Per-joint erosion');
        var plotTraces = [{
            name: 'Flow velocity',
            x: depths,
            y: values,
            type: 'scatter',
            mode: 'markers+lines',
            marker: { color: '#4caf82' },
            line: { color: '#4caf82' }
        }];
        if (isApi && summary.api_erosion_limit_velocity_ms != null && depths.length) {
            plotTraces.push({
                name: 'API velocity limit',
                x: depths,
                y: depths.map(function() { return summary.api_erosion_limit_velocity_ms; }),
                type: 'scatter',
                mode: 'lines',
                line: { color: '#e57373', dash: 'dash' }
            });
        }
        Plotly.react('erosion_plot', plotTraces, {
            margin: { t: 40, r: 20, b: 50, l: 60 },
            title: { text: plotTitle, font: { color: '#ccc', size: 13 } },
            paper_bgcolor: '#2a2d47',
            plot_bgcolor: '#1e1e2e',
            font: { color: '#ccc' },
            xaxis: { title: 'Depth MD [m]', gridcolor: '#444' },
            yaxis: { title: yTitle, gridcolor: '#444' },
            showlegend: isApi
        }, { responsive: true });
    }
}

function runErosionCalculation() {
    var well_name = $('#select_well').val();
    var start_time = $('#erosion_start_date').val();
    var end_time = $('#erosion_end_date').val();

    if (!well_name) {
        $('#erosion_status_message').text('Select a well first.');
        return;
    }
    if (!start_time || !end_time) {
        $('#erosion_status_message').text('Select start and end dates.');
        return;
    }

    $('#erosion_status_message').text('Running erosion calculation…');
    $('#erosion_run_btn').prop('disabled', true);

    var payload = {
        selected_well: well_name,
        start_time: start_time,
        end_time: end_time,
        erosion_model: $('#erosion_model_select').val(),
        erosion_params: collectErosionParams()
    };
    if (erosionWellType === 'productionwell') {
        payload.esp_geometry = collectEspGeometryFromTable();
        var tubingId = readProductionTubingIdInch();
        if (tubingId != null) {
            payload.esp_geometry.production_tubing_id_inch = tubingId;
            payload.tubing_id_inch = tubingId;
        }
    }

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/calculate_erosion',
        contentType: 'application/json',
        data: JSON.stringify(payload),
        success: function(data) {
            $('#erosion_status_message').text('Calculation complete.');
            displayErosionResult(data);
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Calculation failed';
            $('#erosion_status_message').text(msg);
        },
        complete: function() {
            $('#erosion_run_btn').prop('disabled', false);
        }
    });
}

/* ───── End erosion panel ───── */

// Tracks whether calibrated corrosion parameters exist for the selected well.
var wimsModelOptimized = false;

var WALL_THICKNESS_CHANGE_RATE_PREFIX = 'Wall thickness change rate [mm/year]';
var WALL_THICKNESS_CHANGE_PREFIX = 'Wall thickness change [mm]';
var PREDICTED_WALL_THICKNESS_CHANGE_RATE_PREFIX = 'Predicted wall thickness change rate [mm/year]';
var ANNUAL_WALL_THICKNESS_CHANGE_RATE_COL = 'Annual wall thickness change rate [mm/year]';

/** Rate columns present in a {col:[vals]} series (optimize / modelled tables). */
function isWallThicknessChangeRateColumn(name) {
    return name.indexOf(WALL_THICKNESS_CHANGE_RATE_PREFIX) === 0
        || name.indexOf('Corrosion rate [mm/year]') === 0;
}

/** Strip the rate prefix to get the interval label for selectors. */
function stripWallThicknessChangeRatePrefix(col) {
    if (!col) return '';
    return col.replace(WALL_THICKNESS_CHANGE_RATE_PREFIX + ' ', '')
        .replace('Corrosion rate [mm/year] ', '')
        .trim();
}

/** Enable/disable the Forecast "Run" button (prediction requires optimized params). */
function setForecastRunEnabled(enabled) {
    wimsModelOptimized = !!enabled;
    var $btn = $('#forecasting_run_method_btn');
    $btn.prop('disabled', !enabled);
    $btn.attr('title', enabled ? '' : 'Run Optimize first to calibrate the model.');
}

/**
 * Query the backend for the selected well's calibration status and update the
 * "last optimized" note plus the Run button. Prediction is only allowed once
 * optimized parameters are present.
 */
function refreshOptimizationStatus() {
    var well_name = $('#select_well').val();
    var $text = $('#forecasting_last_optimized_text');

    // -- no well selected: nothing to report --------------------------------
    if (!well_name) {
        $text.text('Select a well to check optimization status.');
        setForecastRunEnabled(false);
        return;
    }

    $text.text('Checking optimization status\u2026');

    // -- ask backend whether calibrated params exist (and when) -------------
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/optimization_status',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(data) {
            if (data && data.optimized) {
                var when = data.optimized_at ? (' on ' + data.optimized_at) : '';
                $text.html('Model last optimized' + when + '.');
                setForecastRunEnabled(true);
            } else {
                $text.text('Model not yet optimized \u2014 run Optimize to enable prediction.');
                setForecastRunEnabled(false);
            }
        },
        error: function() {
            $text.text('Could not check optimization status.');
            setForecastRunEnabled(false);
        }
    });
}

/** Request per-joint corrosion model calibration via Celery task. */
function optimizeCorrosionModel() {
    var well_name = $('#select_well').val();
    var $statusMsg = $('#forecasting_status_message');
    var $resultSection = $('#forecasting_optimize_result_section');
    var $btn = $('#forecasting_optimize_btn');

    if (!well_name) {
        if (typeof showErrorMessage === 'function') showErrorMessage('Select a well first.');
        return;
    }

    $btn.prop('disabled', true);
    $statusMsg.text('Submitting corrosion optimization task...');
    $resultSection.hide();

    // -- reset live progress UI (bar, plot, summary, tables) ------------
    $('#forecasting_optimize_summary').empty();
    $('#forecasting_optimize_tables').empty();
    $('#forecasting_optimize_progress_bar').css('width', '0%');
    $('#forecasting_optimize_progress_wrap').hide();
    $('#forecasting_optimize_rate_controls').hide();
    if (typeof Plotly !== 'undefined') {
        var plotEl = document.getElementById('forecasting_optimize_plot');
        var ratePlotEl = document.getElementById('forecasting_optimize_rate_plot');
        if (plotEl) Plotly.purge(plotEl);
        if (ratePlotEl) Plotly.purge(ratePlotEl);
    }

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/optimize_corrosion',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(data) {
            if (data.task_id) {
                $statusMsg.text('Optimization task submitted. Waiting for result...');
                pollOptimizeTask(data.task_id);
            } else {
                displayOptimizeResult(data);
                $btn.prop('disabled', false);
            }
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error requesting corrosion optimization.';
            $statusMsg.text('');
            $btn.prop('disabled', false);
            if (typeof showErrorMessage === 'function') showErrorMessage(msg);
        }
    });
}

/** Poll the corrosion optimization Celery task until complete. */
function pollOptimizeTask(taskId) {
    var $statusMsg = $('#forecasting_status_message');
    var $btn = $('#forecasting_optimize_btn');

    $.ajax({
        type: 'GET',
        url: '/app/wellintegrity/corrosion_task_status/' + taskId,
        success: function(data) {
            if (data.state === 'SUCCESS') {
                $statusMsg.text('');
                $btn.prop('disabled', false);
                displayOptimizeResult(data.result);
            } else if (data.state === 'FAILURE') {
                $statusMsg.text('');
                $btn.prop('disabled', false);
                if (typeof showErrorMessage === 'function') showErrorMessage(data.error || 'Optimization task failed.');
            } else {
                if (data.state === 'PROGRESS' && data.progress) {
                    renderOptimizeProgress(data.progress);
                } else {
                    $statusMsg.text('Optimization state: ' + data.state + '... waiting...');
                }
                setTimeout(function() { pollOptimizeTask(taskId); }, 2000);
            }
        },
        error: function() {
            $statusMsg.text('');
            $btn.prop('disabled', false);
            if (typeof showErrorMessage === 'function') showErrorMessage('Error polling optimization task status.');
        }
    });
}

/** Render live optimization progress: bar + summary text + growing plot. */
function renderOptimizeProgress(progress) {
    var $section = $('#forecasting_optimize_result_section');
    var $summary = $('#forecasting_optimize_summary');
    var $statusMsg = $('#forecasting_status_message');

    var completed = progress.completed || 0;
    var total = progress.total || 0;
    var perJoint = Array.isArray(progress.per_joint) ? progress.per_joint : [];
    var pct = total > 0 ? Math.round((completed / total) * 100) : 0;

    $section.show();
    $('#forecasting_optimize_progress_wrap').show();
    $('#forecasting_optimize_progress_bar').css('width', pct + '%');
    $statusMsg.text('Optimizing... ' + completed + ' / ' + total + ' calibrations (' + pct + '%)');
    $summary.html('<strong>Optimization in progress\u2026</strong> ' + completed + ' / ' + total + ' (joint, interval) calibrations done.');
    renderOptimizePlot(perJoint, 'Per-joint error (updating live)');
}

/** Draw grouped before/after SSE bars into the optimize plot div.
 *
 * Each record is one (joint, interval) calibration.  When the supplied list
 * spans more than one interval (e.g. live progress), the interval is appended
 * to the x-axis label so bars do not collide; for a single interval the label
 * is just the joint number. */
function renderOptimizePlot(perJoint, titleText) {
    var el = document.getElementById('forecasting_optimize_plot');
    if (!el || typeof Plotly === 'undefined' || !Array.isArray(perJoint) || perJoint.length === 0) {
        return;
    }

    var intervals = {};
    perJoint.forEach(function(j) { if (j.interval) intervals[j.interval] = true; });
    var multiInterval = Object.keys(intervals).length > 1;

    var labels = perJoint.map(function(j) {
        var jl = (j.joint_label !== null && j.joint_label !== undefined) ? j.joint_label : j.joint;
        return (multiInterval && j.interval) ? (jl + ' ' + j.interval) : String(jl);
    });
    var before = perJoint.map(function(j) { return j.sse_before; });
    var after = perJoint.map(function(j) { return j.sse_after; });

    var traces = [
        { x: labels, y: before, name: 'Error before', type: 'bar', marker: { color: '#e07b53' } },
        { x: labels, y: after, name: 'Error after', type: 'bar', marker: { color: '#4caf82' } }
    ];
    var layout = {
        paper_bgcolor: '#2a2d47',
        plot_bgcolor: '#23243a',
        font: { color: '#ccc', size: 10 },
        barmode: 'group',
        title: { text: titleText || '', font: { size: 12, color: '#ccc' } },
        xaxis: {
            title: { text: 'Joint No.', font: { size: 11 }, standoff: 6 },
            type: 'category', gridcolor: '#444', automargin: true, tickfont: { size: 9 }
        },
        yaxis: {
            title: { text: 'Sum of squared error [(mm/yr)\u00b2]', font: { size: 11 }, standoff: 6 },
            gridcolor: '#444', automargin: true, tickfont: { size: 9 }, rangemode: 'tozero'
        },
        margin: { t: 30, r: 8, b: 40, l: 60 },
        legend: { orientation: 'h', x: 0, y: 1.14, font: { size: 10 }, bgcolor: 'rgba(35,36,58,0.65)' },
        autosize: true,
        height: 300,
        hovermode: 'closest'
    };
    Plotly.react(el, traces, layout, { responsive: true });
}

/** Rate columns ("Wall thickness change rate [mm/year] (...)") present in a {col:[vals]} series. */
function getRateColumns(series) {
    if (!series || typeof series !== 'object') return [];
    return Object.keys(series).filter(isWallThicknessChangeRateColumn);
}

/**
 * Ordered list of interval rate columns to offer in the interval selector.
 * Prefers the calibrated (joint, interval) pairs from per_joint, falling back to
 * the intervals shared by the measured and modelled tables.
 */
function getOptimizeIntervalCols(data) {
    var cols = [];
    var seen = {};
    if (data && Array.isArray(data.per_joint)) {
        data.per_joint.forEach(function(r) {
            if (r.rate_col && !seen[r.rate_col]) { seen[r.rate_col] = true; cols.push(r.rate_col); }
        });
    }
    if (cols.length === 0 && data) {
        var measuredCols = getRateColumns(data.measured);
        var modelledCols = getRateColumns(data.modelled_calibrated);
        if (modelledCols.length === 0) modelledCols = getRateColumns(data.modelled_uncalibrated);
        cols = measuredCols.filter(function(c) { return modelledCols.indexOf(c) !== -1; });
        if (cols.length === 0) cols = measuredCols.length ? measuredCols : modelledCols;
    }
    return cols;
}

/** Draw the three rate traces for one interval column into the rate plot div. */
function drawCorrosionRateTraces(el, data, col) {
    if (!el || typeof Plotly === 'undefined' || !col) return;
    var measured = data.measured || {};
    var uncal = data.modelled_uncalibrated || {};
    var cal = data.modelled_calibrated || {};

    // -- x-axis = tally sequence number (1..N), aligned by row index ---
    var labels = measured['Joint No.'] || cal['Joint No.'] || uncal['Joint No.'] || [];
    var n = Math.max(
        labels.length,
        (measured[col] || []).length,
        (uncal[col] || []).length,
        (cal[col] || []).length
    );
    var x = [];
    var hover = [];
    for (var i = 0; i < n; i++) {
        x.push(i + 1);
        hover.push(labels[i] !== undefined ? String(labels[i]) : '');
    }

    var common = {
        x: x, type: 'scatter', mode: 'lines+markers', marker: { size: 4 },
        customdata: hover,
        hovertemplate: 'Seq %{x} (joint %{customdata})<br>%{y:.4f} mm/yr<extra>%{fullData.name}</extra>'
    };
    var traces = [];
    if (measured[col]) traces.push(Object.assign({}, common, { y: measured[col], name: 'Measured', line: { color: '#f1c40f' } }));
    if (uncal[col]) traces.push(Object.assign({}, common, { y: uncal[col], name: 'Modelled (un-calibrated)', line: { color: '#e07b53', dash: 'dot' } }));
    if (cal[col]) traces.push(Object.assign({}, common, { y: cal[col], name: 'Modelled (calibrated)', line: { color: '#4caf82' } }));

    var layout = {
        paper_bgcolor: '#2a2d47',
        plot_bgcolor: '#23243a',
        font: { color: '#ccc', size: 10 },
        title: { text: 'Wall thickness change rate by joint: measured vs modelled', font: { size: 12, color: '#ccc' } },
        xaxis: {
            title: { text: 'Tally seq. no.', font: { size: 11 }, standoff: 6 },
            gridcolor: '#444', automargin: true, tickfont: { size: 9 }
        },
        yaxis: {
            title: { text: WALL_THICKNESS_CHANGE_RATE_PREFIX, font: { size: 11 }, standoff: 6 },
            gridcolor: '#444', automargin: true, tickfont: { size: 9 }, rangemode: 'tozero'
        },
        margin: { t: 30, r: 8, b: 40, l: 60 },
        legend: { orientation: 'h', x: 0, y: 1.14, font: { size: 10 }, bgcolor: 'rgba(35,36,58,0.65)' },
        autosize: true,
        height: 320,
        hovermode: 'closest'
    };
    Plotly.react(el, traces, layout, { responsive: true });
}

/** Render a {col: [vals]} object as a labelled table into a container. */
function renderForecastTable($container, title, colsObj) {
    if (!colsObj || typeof colsObj !== 'object') return;
    var cols = Object.keys(colsObj);
    if (cols.length === 0) return;
    var nRows = Array.isArray(colsObj[cols[0]]) ? colsObj[cols[0]].length : 0;

    var $wrap = $('<div class="forecasting-table-wrap" style="max-height: 300px; overflow: auto; margin-bottom: 14px;"></div>');
    if (title) {
        $wrap.append($('<div style="color: #aaa; font-size: 0.8rem; margin-bottom: 4px;"></div>').text(title));
    }
    var $table = $('<table class="table table-sm forecasting-corrosion-table"></table>');
    var $thead = $('<thead></thead>');
    var $headRow = $('<tr></tr>');
    cols.forEach(function(col) { $headRow.append($('<th></th>').text(col)); });
    $thead.append($headRow);

    var $tbody = $('<tbody></tbody>');
    for (var r = 0; r < nRows; r++) {
        var $tr = $('<tr></tr>');
        cols.forEach(function(col) {
            var val = colsObj[col][r];
            if (val === null || val === undefined || (typeof val === 'number' && isNaN(val))) {
                val = '\u2014';
            } else if (typeof val === 'number') {
                val = Number(val).toFixed(5);
            }
            $tr.append($('<td></td>').text(val));
        });
        $tbody.append($tr);
    }
    $table.append($thead).append($tbody);
    $wrap.append($table);
    $container.append($wrap);
}

/** Adaptive number format: exponential for tiny magnitudes, fixed otherwise. */
function formatOptimizeNumber(value, digits) {
    if (typeof value !== 'number' || !isFinite(value)) return '\u2014';
    if (value !== 0 && Math.abs(value) < 0.001) return value.toExponential(2);
    return Number(value).toFixed(digits != null ? digits : 4);
}

/** Render per-joint calibrated coefficients (A,B,C,D,E), iterations, convergence.
 *
 * ``perJoint`` should already be filtered to a single interval; ``intervalLabel``
 * is shown in the table caption. */
function renderOptimizeParamsTable($container, perJoint, intervalLabel) {
    if (!Array.isArray(perJoint) || perJoint.length === 0) return;

    var caption = 'Calibrated coefficients & convergence per joint';
    if (intervalLabel) caption += ' \u2014 interval ' + intervalLabel;

    var headers = ['Joint No.', 'A', 'B', 'C', 'D', 'E (sign)', 'Iterations', 'Func. evals', 'Converged', 'SSE before', 'SSE after'];
    var $wrap = $('<div class="forecasting-table-wrap" style="max-height: 340px; overflow: auto; margin-bottom: 14px;"></div>');
    $wrap.append($('<div style="color: #aaa; font-size: 0.8rem; margin-bottom: 4px;"></div>').text(caption));

    var $table = $('<table class="table table-sm forecasting-corrosion-table"></table>');
    var $thead = $('<thead></thead>');
    var $headRow = $('<tr></tr>');
    headers.forEach(function(h) { $headRow.append($('<th></th>').text(h)); });
    $thead.append($headRow);

    var $tbody = $('<tbody></tbody>');
    perJoint.forEach(function(j) {
        var p = j.params || {};
        var $tr = $('<tr></tr>');
        $tr.append($('<td></td>').text((j.joint_label !== null && j.joint_label !== undefined) ? j.joint_label : j.joint));
        $tr.append($('<td></td>').text(formatOptimizeNumber(p.A)));
        $tr.append($('<td></td>').text(formatOptimizeNumber(p.B)));
        $tr.append($('<td></td>').text(formatOptimizeNumber(p.C)));
        $tr.append($('<td></td>').text(formatOptimizeNumber(p.D)));
        $tr.append($('<td></td>').text((p.E !== null && p.E !== undefined) ? (p.E < 0 ? '-1' : '+1') : '\u2014'));
        $tr.append($('<td></td>').text((j.iterations !== null && j.iterations !== undefined) ? j.iterations : '\u2014'));
        $tr.append($('<td></td>').text((j.n_func_evals !== null && j.n_func_evals !== undefined) ? j.n_func_evals : '\u2014'));
        $tr.append($('<td style="color:' + (j.converged ? '#4caf82' : '#e07b53') + ';"></td>').text(j.converged ? 'yes' : 'no'));
        $tr.append($('<td></td>').text(formatOptimizeNumber(j.sse_before)));
        $tr.append($('<td></td>').text(formatOptimizeNumber(j.sse_after)));
        $tbody.append($tr);
    });
    $table.append($thead).append($tbody);
    $wrap.append($table);
    $container.append($wrap);
}

/** Display the corrosion optimization result (summary + comparison tables). */
function displayOptimizeResult(data) {
    var $section = $('#forecasting_optimize_result_section');
    var $summary = $('#forecasting_optimize_summary');
    var $tables = $('#forecasting_optimize_tables');
    var $statusMsg = $('#forecasting_status_message');

    $summary.empty();
    $tables.empty();

    if (!data || typeof data !== 'object') {
        $section.hide();
        $statusMsg.text('No optimization result returned.');
        return;
    }

    var summary = data.summary || {};
    if (summary.status === 'skipped' || (data.message && summary.status !== 'ok')) {
        $section.hide();
        $('#forecasting_optimize_progress_wrap').hide();
        $statusMsg.text(summary.message || data.message || 'Optimization skipped: no overlapping measured/modelled intervals.');
        return;
    }

    var nJoints = (summary.n_joints !== null && summary.n_joints !== undefined) ? summary.n_joints : '?';
    var nIntervals = (summary.n_intervals !== null && summary.n_intervals !== undefined) ? summary.n_intervals : 1;
    var sseBefore = (typeof summary.sse_before === 'number') ? summary.sse_before.toExponential(3) : '?';
    var sseAfter = (typeof summary.sse_after === 'number') ? summary.sse_after.toExponential(3) : '?';
    $summary.html(
        '<strong>Calibration complete.</strong> Joints calibrated: ' + nJoints +
        ' &nbsp;|&nbsp; intervals: ' + nIntervals +
        ' &nbsp;|&nbsp; total SSE ' + sseBefore + ' \u2192 ' + sseAfter
    );
    if (data.log_file) {
        $summary.append(
            $('<div style="color: #888; font-size: 0.78rem; margin-top: 4px;"></div>')
                .text('Debug log saved: ' + data.log_file)
        );
    }

    // -- complete the progress bar --------------------------------------
    $('#forecasting_optimize_progress_bar').css('width', '100%');
    $('#forecasting_optimize_progress_wrap').hide();

    // -- calibration succeeded: refresh "last optimized" + enable Run ---
    refreshOptimizationStatus();

    // -- separate hosts: params table re-renders per interval; data tables once
    var $paramsHost = $('<div></div>');
    var $dataHost = $('<div></div>');
    $tables.append($paramsHost).append($dataHost);
    renderForecastTable($dataHost, 'Measured (from logs)', data.measured);
    renderForecastTable($dataHost, 'Modelled (un-calibrated)', data.modelled_uncalibrated);
    renderForecastTable($dataHost, 'Modelled (calibrated)', data.modelled_calibrated);

    var perJoint = Array.isArray(data.per_joint) ? data.per_joint : [];
    var intervalCols = getOptimizeIntervalCols(data);
    var rateEl = document.getElementById('forecasting_optimize_rate_plot');

    // -- render all interval-specific views for one selected interval ---
    function renderInterval(col) {
        var label = stripWallThicknessChangeRatePrefix(col);
        var filtered = perJoint.filter(function(r) { return r.rate_col === col; });
        if (filtered.length === 0) filtered = perJoint;  // single-interval payloads
        renderOptimizePlot(filtered, 'Per-joint error: before vs after calibration' + (label ? ' (' + label + ')' : ''));
        $paramsHost.empty();
        renderOptimizeParamsTable($paramsHost, filtered, label);
        if (rateEl) drawCorrosionRateTraces(rateEl, data, col);
    }

    // -- one interval selector drives SSE plot + params table + rate plot
    var $controls = $('#forecasting_optimize_rate_controls');
    var $select = $('#forecasting_optimize_rate_interval');
    if (intervalCols.length > 1) {
        $select.empty();
        intervalCols.forEach(function(c) {
            var label = stripWallThicknessChangeRatePrefix(c);
            $select.append($('<option></option>').attr('value', c).text(label || c));
        });
        $controls.show();
        $select.off('change.optInterval').on('change.optInterval', function() {
            renderInterval($(this).val());
        });
    } else {
        $controls.hide();
    }
    renderInterval(intervalCols.length ? intervalCols[0] : null);

    $statusMsg.text('');
    $section.show();
    // Plotly needs a resize once its containers become visible.
    if (typeof Plotly !== 'undefined') {
        setTimeout(function() {
            var sseEl = document.getElementById('forecasting_optimize_plot');
            if (sseEl) Plotly.Plots.resize(sseEl);
            if (rateEl) Plotly.Plots.resize(rateEl);
        }, 0);
    }
    if (typeof showSuccessMessage === 'function') showSuccessMessage('Corrosion model optimization complete.');
}

/** Request a remaining-wall-thickness prediction via Celery task. */
function predictCorrosion() {
    var well_name = $('#select_well').val();
    var $statusMsg = $('#forecasting_status_message');
    var $resultSection = $('#forecasting_predict_result_section');
    var $btn = $('#forecasting_run_method_btn');

    if (!well_name) {
        if (typeof showErrorMessage === 'function') showErrorMessage('Select a well first.');
        return;
    }

    $btn.prop('disabled', true);
    $statusMsg.text('Submitting prediction task...');
    $resultSection.hide();

    // -- reset prediction UI (summary, plot, tables) --------------------
    $('#forecasting_predict_summary').empty();
    $('#forecasting_predict_tables').empty();
    if (typeof Plotly !== 'undefined') {
        var plotEl = document.getElementById('forecasting_predict_plot');
        if (plotEl) Plotly.purge(plotEl);
    }

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/predict_corrosion',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(data) {
            if (data.task_id) {
                $statusMsg.text('Prediction task submitted. Waiting for result...');
                pollPredictTask(data.task_id);
            } else {
                displayPredictResult(data);
                $btn.prop('disabled', false);
            }
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error requesting corrosion prediction.';
            $statusMsg.text('');
            $btn.prop('disabled', false);
            if (typeof showErrorMessage === 'function') showErrorMessage(msg);
        }
    });
}

/** Poll the corrosion prediction Celery task until complete. */
function pollPredictTask(taskId) {
    var $statusMsg = $('#forecasting_status_message');
    var $btn = $('#forecasting_run_method_btn');

    $.ajax({
        type: 'GET',
        url: '/app/wellintegrity/corrosion_task_status/' + taskId,
        success: function(data) {
            if (data.state === 'SUCCESS') {
                $statusMsg.text('');
                $btn.prop('disabled', false);
                displayPredictResult(data.result);
            } else if (data.state === 'FAILURE') {
                $statusMsg.text('');
                $btn.prop('disabled', false);
                if (typeof showErrorMessage === 'function') showErrorMessage(data.error || 'Prediction task failed.');
            } else {
                $statusMsg.text('Prediction state: ' + data.state + '... waiting...');
                setTimeout(function() { pollPredictTask(taskId); }, 2000);
            }
        },
        error: function() {
            $statusMsg.text('');
            $btn.prop('disabled', false);
            if (typeof showErrorMessage === 'function') showErrorMessage('Error polling prediction task status.');
        }
    });
}

/** Display the predicted remaining wall thickness (summary + plot + table). */
function displayPredictResult(data) {
    var $section = $('#forecasting_predict_result_section');
    var $summary = $('#forecasting_predict_summary');
    var $tables = $('#forecasting_predict_tables');
    var $statusMsg = $('#forecasting_status_message');

    $summary.empty();
    $tables.empty();

    if (!data || typeof data !== 'object' || data.status !== 'ok') {
        $section.hide();
        var msg = (data && data.message) ? data.message : 'No prediction returned.';
        $statusMsg.text(msg);
        if (typeof showErrorMessage === 'function') showErrorMessage(msg);
        return;
    }

    var nJoints = (data.n_joints !== null && data.n_joints !== undefined) ? data.n_joints : '?';
    $summary.html(
        '<strong>Prediction complete.</strong> Joints: ' + nJoints +
        ' &nbsp;|&nbsp; window ' + (data.latest_log_date || '?') + ' \u2192 ' + (data.end_date || 'now') +
        '<div style="color:#888;font-size:0.78rem;margin-top:4px;">Uses the latest interval\u2019s calibrated parameters and production data since the latest log.</div>'
    );

    renderRemainingWallPlot(data);
    renderForecastTable($tables, 'Predicted remaining wall thickness per joint', data.prediction);

    $statusMsg.text('');
    $section.show();
    if (typeof Plotly !== 'undefined') {
        setTimeout(function() {
            var el = document.getElementById('forecasting_predict_plot');
            if (el) Plotly.Plots.resize(el);
        }, 0);
    }
    if (typeof showSuccessMessage === 'function') showSuccessMessage('Corrosion prediction complete.');
}

/** Plot predicted remaining wall thickness (and rate) vs tally seq. no. */
function renderRemainingWallPlot(data) {
    var el = document.getElementById('forecasting_predict_plot');
    if (!el || typeof Plotly === 'undefined') return;
    var pred = data ? data.prediction : null;
    if (!pred || typeof pred !== 'object') { Plotly.purge(el); return; }

    var cols = Object.keys(pred);
    var jointCol = cols.filter(function(c) { return c.indexOf('Joint No.') === 0; })[0] || cols[0];
    var wallCol = cols.filter(function(c) { return c.indexOf('Remaining wall thickness [mm]') === 0; })[0];
    var rateCol = cols.filter(function(c) {
        return c.indexOf(PREDICTED_WALL_THICKNESS_CHANGE_RATE_PREFIX) === 0
            || c.indexOf('Predicted corrosion rate') === 0;
    })[0];
    if (!wallCol) { Plotly.purge(el); return; }

    var joints = pred[jointCol] || [];
    var x = joints.map(function(_, i) { return i + 1; });
    var hover = joints.map(function(j) { return 'Joint ' + j; });

    var traces = [{
        x: x, y: pred[wallCol], mode: 'lines+markers', type: 'scatter',
        name: 'Remaining wall [mm]', line: { color: '#4caf82' }, marker: { size: 5 },
        text: hover, hovertemplate: '%{text}<br>Wall: %{y:.3f} mm<extra></extra>'
    }];
    if (rateCol) {
        traces.push({
            x: x, y: pred[rateCol], mode: 'lines+markers', type: 'scatter',
            name: 'Predicted wall thickness change rate [mm/yr]', yaxis: 'y2',
            line: { color: '#e07b53', dash: 'dot' }, marker: { size: 4 },
            text: hover, hovertemplate: '%{text}<br>Change rate: %{y:.4f} mm/yr<extra></extra>'
        });
    }

    var layout = {
        paper_bgcolor: '#2a2d47',
        plot_bgcolor: '#23243a',
        font: { color: '#ccc', size: 10 },
        title: { text: 'Predicted remaining wall thickness per joint', font: { size: 12, color: '#ccc' } },
        xaxis: {
            title: { text: 'Tally seq. no.', font: { size: 11 }, standoff: 6 },
            gridcolor: '#444', automargin: true, tickfont: { size: 9 }
        },
        yaxis: {
            title: { text: 'Remaining wall [mm]', font: { size: 11 }, standoff: 6 },
            gridcolor: '#444', automargin: true, tickfont: { size: 9 }, rangemode: 'tozero'
        },
        yaxis2: {
            title: { text: 'Predicted wall thickness change rate [mm/yr]', font: { size: 11 } },
            overlaying: 'y', side: 'right', gridcolor: 'rgba(224,123,83,0.15)',
            automargin: true, tickfont: { size: 9 }
        },
        margin: { t: 30, r: 60, b: 40, l: 60 },
        legend: { orientation: 'h', x: 0, y: 1.14, font: { size: 10 }, bgcolor: 'rgba(35,36,58,0.65)' },
        autosize: true, height: 320, hovermode: 'closest'
    };
    Plotly.react(el, traces, layout, { responsive: true });
}

// ---------------------------------------------------------------------------
// Forecast method: years to minimum thickness
// ---------------------------------------------------------------------------

/**
 * Dispatch the prediction method selected in the Forecast card.
 *
 * The picker is extensible; "years_to_min" is the only option for now.
 */
function runForecastMethod() {
    if (!wimsModelOptimized) {
        if (typeof showErrorMessage === 'function') {
            showErrorMessage('Run Optimize first \u2014 prediction needs calibrated model parameters.');
        }
        return;
    }
    var method = $('#forecasting_method_select').val();
    if (method === 'current_wall_thickness') {
        predictCorrosion();
    } else if (method === 'years_to_min') {
        forecastYearsToMin();
    } else if (typeof showErrorMessage === 'function') {
        showErrorMessage('Unknown prediction method: ' + method);
    }
}

/**
 * Forecast years-to-minimum-thickness per casing size.
 *
 * Reads Minimum wall thickness operational limits, runs the calibrated model
 * over the last 12 months of production (Celery), and shows results in the
 * Forecast card only.
 */
function forecastYearsToMin() {
    var well_name = $('#select_well').val();
    var $statusMsg = $('#forecasting_status_message');
    var $resultSection = $('#forecasting_years_to_min_result_section');
    var $btn = $('#forecasting_run_method_btn');

    if (!well_name) {
        if (typeof showErrorMessage === 'function') showErrorMessage('Select a well first.');
        return;
    }

    // -- gather minimum thickness from operational limits -------------
    var casings = [];
    getMinimumWallThicknessLimits().forEach(function(item) {
        var label = item.casing != null ? String(item.casing) : '';
        var minMm = item.min;
        if (!label || minMm == null || String(minMm).trim() === '' || !isFinite(parseFloat(minMm))) {
            return;
        }
        var size = (dashboardCasingSizes || []).filter(function(s) {
            return String(s.label) === label;
        })[0];
        if (size) {
            casings.push({ od_inch: size.od_inch, min_thickness_mm: parseFloat(minMm) });
        }
    });

    if (!casings.length) {
        if (typeof showErrorMessage === 'function') {
            showErrorMessage('Add at least one Minimum wall thickness operational limit with a casing and thickness first.');
        }
        return;
    }

    $btn.prop('disabled', true);
    $statusMsg.text('Submitting years-to-minimum-thickness forecast...');
    $resultSection.hide();
    $('#forecasting_years_to_min_summary').empty();
    $('#forecasting_years_to_min_tables').empty();

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/forecast_years_to_min',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, casings: casings }),
        success: function(data) {
            if (data.task_id) {
                $statusMsg.text('Forecast task submitted. Waiting for result...');
                pollYearsToMinTask(data.task_id);
            } else {
                displayYearsToMinResult(data);
                $btn.prop('disabled', false);
            }
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error requesting years-to-minimum-thickness forecast.';
            $statusMsg.text('');
            $btn.prop('disabled', false);
            if (typeof showErrorMessage === 'function') showErrorMessage(msg);
        }
    });
}

/** Poll the years-to-min Celery task until complete. */
function pollYearsToMinTask(taskId) {
    var $statusMsg = $('#forecasting_status_message');
    var $btn = $('#forecasting_run_method_btn');

    $.ajax({
        type: 'GET',
        url: '/app/wellintegrity/corrosion_task_status/' + taskId,
        success: function(data) {
            if (data.state === 'SUCCESS') {
                $statusMsg.text('');
                $btn.prop('disabled', false);
                displayYearsToMinResult(data.result);
            } else if (data.state === 'FAILURE') {
                $statusMsg.text('');
                $btn.prop('disabled', false);
                if (typeof showErrorMessage === 'function') showErrorMessage(data.error || 'Forecast task failed.');
            } else {
                $statusMsg.text('Forecast state: ' + data.state + '... waiting...');
                setTimeout(function() { pollYearsToMinTask(taskId); }, 2000);
            }
        },
        error: function() {
            $statusMsg.text('');
            $btn.prop('disabled', false);
            if (typeof showErrorMessage === 'function') showErrorMessage('Error polling forecast task status.');
        }
    });
}

/** Display the years-to-min result in the Forecast card. */
function displayYearsToMinResult(data) {
    var $section = $('#forecasting_years_to_min_result_section');
    var $summary = $('#forecasting_years_to_min_summary');
    var $tables = $('#forecasting_years_to_min_tables');
    var $statusMsg = $('#forecasting_status_message');

    $summary.empty();
    $tables.empty();

    if (!data || typeof data !== 'object' || data.status !== 'ok') {
        $section.hide();
        var msg = (data && data.message) ? data.message : 'No forecast returned.';
        $statusMsg.text(msg);
        if (typeof showErrorMessage === 'function') showErrorMessage(msg);
        return;
    }

    var perCasing = Array.isArray(data.per_casing) ? data.per_casing : [];

    // -- summary + per-casing confirmation table -----------------------
    var rateWindow = Array.isArray(data.rate_window) ? data.rate_window.join(' \u2192 ') : '';
    $summary.html(
        '<strong>Forecast complete.</strong> Casing sizes: ' + perCasing.length +
        (rateWindow ? (' &nbsp;|&nbsp; rate window ' + rateWindow) : '') +
        '<div style="color:#888;font-size:0.78rem;margin-top:4px;">Top 5 worst (soonest) joints per casing; calibrated model over the last 12 months.</div>'
    );

    renderYearsToMinTable($tables, perCasing);

    $statusMsg.text('');
    $section.show();
    if (typeof showSuccessMessage === 'function') showSuccessMessage('Years-to-minimum-thickness forecast complete.');
}

/** Map a casing OD [inch] to its dashboard label, when known. */
function casingLabelForOd(odInch) {
    var match = (dashboardCasingSizes || []).filter(function(s) {
        return Math.abs(parseFloat(s.od_inch) - parseFloat(odInch)) < 1e-4;
    })[0];
    return match ? String(match.label) : null;
}

/** Top ranked joints for one casing entry (legacy fallback when top_joints absent). */
function yearsToMinRowsForCasing(c) {
    var rows = Array.isArray(c.top_joints) ? c.top_joints.slice() : [];
    if (!rows.length && c.limiting_joint != null) {
        rows = [{
            rank: 1,
            joint: c.limiting_joint,
            remaining_now_mm: c.remaining_now_mm,
            rate_mm_yr: c.rate_mm_yr,
            years_to_min_yr: c.years_to_min_yr
        }];
    }
    return rows;
}

/** Render a compact per-casing years-to-min table in the Forecast card. */
function renderYearsToMinTable($container, perCasing) {
    if (!Array.isArray(perCasing) || perCasing.length === 0) {
        $container.append($('<div class="text-muted" style="font-size:0.8rem;"></div>').text('No casing sizes with a minimum thickness were evaluated.'));
        return;
    }
    var $wrap = $('<div class="forecasting-table-wrap" style="max-height: 420px; overflow: auto; margin-bottom: 14px;"></div>');
    var $table = $('<table class="table table-sm forecasting-corrosion-table"></table>');
    var headers = ['Casing', 'Min. thickness [mm]', 'Rank', 'Joint', 'Remaining now [mm]', 'Wall thickness change rate [mm/yr]', 'Years to min.'];
    var $thead = $('<thead></thead>');
    var $headRow = $('<tr></tr>');
    headers.forEach(function(h) { $headRow.append($('<th></th>').text(h)); });
    $thead.append($headRow);

    var $tbody = $('<tbody></tbody>');
    perCasing.forEach(function(c) {
        var label = casingLabelForOd(c.od_inch) || (c.od_inch != null ? String(c.od_inch) : '\u2014');
        var minStr = c.min_thickness_mm != null ? Number(c.min_thickness_mm).toFixed(2) : '\u2014';
        var joints = yearsToMinRowsForCasing(c);
        joints.forEach(function(j, idx) {
            var years = (j.years_to_min_yr === null || j.years_to_min_yr === undefined) ? 'N/A' : Number(j.years_to_min_yr).toFixed(2);
            var $tr = $('<tr></tr>');
            if (idx === 0) {
                $tr.append($('<td></td>').attr('rowspan', joints.length).text(label));
                $tr.append($('<td></td>').attr('rowspan', joints.length).text(minStr));
            }
            $tr.append($('<td></td>').text(j.rank != null ? String(j.rank) : String(idx + 1)));
            $tr.append($('<td></td>').text(j.joint != null ? j.joint : '\u2014'));
            $tr.append($('<td></td>').text(j.remaining_now_mm != null ? Number(j.remaining_now_mm).toFixed(3) : '\u2014'));
            $tr.append($('<td></td>').text(j.rate_mm_yr != null ? Number(j.rate_mm_yr).toFixed(4) : '\u2014'));
            $tr.append($('<td></td>').text(years));
            $tbody.append($tr);
        });
    });
    $table.append($thead).append($tbody);
    $wrap.append($table);
    $container.append($wrap);
}

/** Match Processed Logs panel height to Well Logs card. */
function syncProcessedLogPanelHeight() {
    var $wellLogsCard = $('#well_data_section');
    var $panel = $('#processed_logs_panel');
    if (!$panel.length || !$panel.is(':visible')) {
        $panel.css({ 'min-height': '', 'max-height': '' });
        return;
    }
    if ($wellLogsCard.length && $wellLogsCard.is(':visible')) {
        var cardH = $wellLogsCard.outerHeight();
        if (cardH > 0) {
            $panel.css({ 'min-height': cardH + 'px', 'max-height': cardH + 'px' });
            const chartEl = document.getElementById('processed_log_chart');
            if (chartEl) {
                setTimeout(function() {
                    Plotly.Plots.resize(chartEl);
                }, 0);
            }
        }
    }
}

function showProcessedLogSection() {
    $('#processed_log_section').show();
}

function hideProcessedLogSection() {
    $('#processed_log_section').hide();
}


function updateProcessedLogsDropdown(processedLogs) {
    window.processedLogsAvailable = Array.isArray(processedLogs) ? processedLogs.slice() : [];
    const selected = window.processedLogsAvailable.slice();
    renderProcessedLogCheckboxDropdown(window.processedLogsAvailable, selected);

    var hasDetected = (window.detectedLogsList || []).length > 0;
    var $hint = $('#view_processed_log_block .text-muted');

    if (window.processedLogsAvailable.length > 0) {
        $('#view_processed_log_block').show();
        $('#processed_logs_panel').show();
        $('#processed_log_section').show();
        $hint.text('Select one or more processed logs to chart');
        showProcessedLogSection();
    } else if (hasDetected) {
        $('#view_processed_log_block').show();
        $('#processed_logs_panel').hide();
        $('#processed_log_section').hide();
        $hint.text('No processed logs yet. Use "Detect Joints" → QA/QC → "Process Logs" workflow.');
        hideProcessedLogSection();
        Plotly.purge('processed_log_chart');
    } else {
        $('#view_processed_log_block').hide();
        $('#processed_logs_panel').hide();
        hideProcessedLogSection();
        Plotly.purge('processed_log_chart');
    }
}

// Global variable to track unprocessed logs
let unprocessedLogsList = [];
let inputsRequiredLogsList = [];
const MAX_WELL_LOGS = 5;

function loadWellLogs() {
    const well_name = $('#select_well').val();
    if (!well_name) {
        return;
    }
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_log_status',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function (data) {
            const tbody = $('#logs_table_body');
            tbody.empty();

            const logs = Array.isArray(data) ? data.slice(0, MAX_WELL_LOGS) : [];

            if (logs.length > 0) {
                let unprocessedLogs = [];
                let detectedLogs = [];
                let processedLogs = [];
                let inputsRequiredLogs = [];

                logs.forEach(log => {
                    var statusBadge;
                    if (log.status === 'processed') {
                        statusBadge = '<span class="badge badge-success">Processed</span>';
                        processedLogs.push(log.name);
                    } else if (log.status === 'detected') {
                        statusBadge = '<span class="badge badge-primary">Joints detected</span>';
                        detectedLogs.push(log.name);
                    } else if (log.status === 'unprocessed') {
                        statusBadge = '<span class="badge badge-info">Un-processed</span>';
                        unprocessedLogs.push(log.name);
                    } else {
                        statusBadge = '<span class="badge badge-warning">Inputs required</span>';
                        inputsRequiredLogs.push(log.name);
                    }
                    
                    const row = $('<tr class="log-row-clickable"></tr>')
                        .attr('data-log-name', log.name)
                        .append($('<td class="log-name-cell"></td>').attr('title', log.name).text(log.name))
                        .append($('<td></td>').html(statusBadge));
                    tbody.append(row);
                    window.logDateByName[log.name] = log.date || '';
                });

                for (let i = logs.length; i < MAX_WELL_LOGS; i += 1) {
                    tbody.append(
                        '<tr class="log-row-placeholder">' +
                        '<td class="log-name-cell text-muted">—</td>' +
                        '<td class="text-center text-muted">—</td>' +
                        '</tr>'
                    );
                }
                
                unprocessedLogsList = unprocessedLogs;
                inputsRequiredLogsList = inputsRequiredLogs;
                window.detectedLogsList = detectedLogs;
                updateProcessButtonState();
                updateProcessedLogsDropdown(processedLogs);
                if (processedLogs.length > 0) {
                    loadProcessedLogs(processedLogs, { silent: true });
                } else {
                    Plotly.purge('processed_log_chart');
                }

                var logsWithDetection = detectedLogs.concat(processedLogs);
                if (logsWithDetection.length > 0) {
                    loadSavedDetectedJoints(logsWithDetection);
                } else {
                    $('#open_qaqc_modal_btn').hide();
                }
            } else {
                for (let i = 0; i < MAX_WELL_LOGS; i += 1) {
                    tbody.append(
                        '<tr class="log-row-placeholder">' +
                        '<td class="log-name-cell text-muted">—</td>' +
                        '<td class="text-center text-muted">—</td>' +
                        '</tr>'
                    );
                }
                unprocessedLogsList = [];
                inputsRequiredLogsList = [];
                updateProcessButtonState();
                updateProcessedLogsDropdown([]);
                Plotly.purge('processed_log_chart');
            }
            setTimeout(syncProcessedLogPanelHeight, 50);
        },
        error: function (xhr) {
            console.error('Error loading logs:', xhr);
            $('#logs_table_body').empty().append('<tr><td colspan="2" class="text-danger text-center py-3">Error loading logs</td></tr>');
        }
    });
}

function updateProcessButtonState() {
    var processBtn = $('#process_logs_btn');
    var detectBtn = $('#detect_joints_btn');
    var detected = window.detectedLogsList || [];

    if (unprocessedLogsList.length > 0) {
        detectBtn.prop('disabled', false).text('Detect Joints (' + unprocessedLogsList.length + ')');
        processBtn.prop('disabled', true).text('Process Logs (detect joints first)');
    } else if (inputsRequiredLogsList.length > 0 && detected.length === 0) {
        detectBtn.prop('disabled', true).text('Detect Joints (define all log inputs)');
        processBtn.prop('disabled', true).text('Process Logs (detect joints first)');
    } else if (detected.length > 0) {
        detectBtn.prop('disabled', true).text('Detect Joints');
        processBtn.prop('disabled', false).text('Process Logs (' + detected.length + ' detected)');
    } else {
        processBtn.prop('disabled', true).text('Process Logs');
        detectBtn.prop('disabled', true).text('Detect Joints');
    }
}

// ---------------------------------------------------------------------------
// Joint Detection QA/QC
// ---------------------------------------------------------------------------

window.detectedJointsData = {};

function _initLogApprovalState(logData) {
    if (!logData) return;
    var allCandidates = logData.candidates || [];
    logData._allCandidates = allCandidates;

    if (logData.approved_candidates && logData.approved_candidates.length > 0) {
        var approved = logData.approved_candidates;
        var approvedDepths = {};
        for (var j = 0; j < approved.length; j++) {
            var key = approved[j].depth + '|' + approved[j].idx + '|' + approved[j].kind;
            approvedDepths[key] = true;
        }
        var approvedIdxs = [];
        for (var i = 0; i < allCandidates.length; i++) {
            var ck = allCandidates[i].depth + '|' + allCandidates[i].idx + '|' + allCandidates[i].kind;
            if (approvedDepths[ck]) {
                approvedIdxs.push(i);
            }
        }
        logData._approvedIndices = approvedIdxs;
    }
}

function loadSavedDetectedJoints(logNames) {
    var wellName = $('#select_well').val();
    if (!wellName || logNames.length === 0) return;

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_detected_joints',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: wellName,
            selected_logs: logNames
        }),
        success: function (data) {
            if (data.detected_joints) {
                for (var ln in data.detected_joints) {
                    window.detectedJointsData[ln] = data.detected_joints[ln];
                    _initLogApprovalState(window.detectedJointsData[ln]);
                }
                window._qaqcLogNames = logNames;
                $('#open_qaqc_modal_btn').show();
            }
        },
        error: function (xhr) {
            console.warn('[DetectJoints] Failed to load saved detected joints:', xhr);
        }
    });
}

function detectJointsForLogs(logNames) {
    const well_name = $('#select_well').val();
    const selectedLogs = (logNames || []).filter(Boolean);

    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }

    if (selectedLogs.length === 0) {
        showErrorMessage('No logs selected for joint detection');
        return;
    }

    showInfoMessage('Detecting joints for ' + selectedLogs.length + ' log(s)... Please wait.');

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/detect_joints',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            selected_logs: selectedLogs
        }),
        success: function (data) {
            if (data.task_id) {
                showInfoMessage('Joint detection started. Please wait...');
                pollDetectJointsResults(data.task_id, selectedLogs);
            } else {
                showErrorMessage('Failed to start joint detection: No task ID returned');
            }
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Error starting joint detection';
            showErrorMessage(errorMsg);
        }
    });
}

function detectJoints() {
    if (unprocessedLogsList.length === 0) {
        showErrorMessage('No unprocessed logs to detect joints for');
        return;
    }
    detectJointsForLogs(unprocessedLogsList);
}

function pollDetectJointsResults(taskId, selectedLogs) {
    var pollInterval = 2000;
    var panelShown = false;
    var prevReadyCount = 0;
    var wellName = $('#select_well').val();

    function checkResults() {
        $.ajax({
            type: 'POST',
            url: '/app/wellintegrity/get_detect_joints_results',
            contentType: 'application/json',
            data: JSON.stringify({
                task_id: taskId,
                selected_well: wellName,
                selected_logs: selectedLogs
            }),
            success: function (data) {
                console.log('[DetectJoints] Poll:', data.task_status,
                    data.completed_logs + '/' + data.total_logs, 'logs ready');

                var readyLogs = data.ready_logs || {};
                var readyCount = data.completed_logs || 0;

                if (readyCount > prevReadyCount) {
                    for (var logName in readyLogs) {
                        if (!window.detectedJointsData[logName] ||
                            (readyLogs[logName].chart_depths &&
                             !window.detectedJointsData[logName].chart_depths)) {
                            window.detectedJointsData[logName] = readyLogs[logName];
                            _initLogApprovalState(window.detectedJointsData[logName]);
                        }
                    }
                    prevReadyCount = readyCount;

                    if (!panelShown) {
                        panelShown = true;
                        showJointQaqcPanel(selectedLogs);
                    } else {
                        refreshQaqcPanelLogList(selectedLogs);
                        var currentLog = $('#joint_qaqc_log_select').val();
                        if (currentLog && window.detectedJointsData[currentLog] &&
                            window.detectedJointsData[currentLog].chart_depths) {
                            renderJointQaqcChart(currentLog);
                        }
                    }

                    showInfoMessage('Detected joints for ' + readyCount + '/' +
                        data.total_logs + ' log(s)...');
                }

                if (data.task_status === 'SUCCESS') {
                    if (data.task_result && data.task_result.detected_joints) {
                        var finalData = data.task_result.detected_joints;
                        for (var ln in finalData) {
                            window.detectedJointsData[ln] = finalData[ln];
                        }
                    }
                    showSuccessMessage('Joint detection completed! (' +
                        data.total_logs + ' logs)');

                    if (!panelShown) {
                        panelShown = true;
                        showJointQaqcPanel(selectedLogs);
                    }

                    var currentLog = $('#joint_qaqc_log_select').val();
                    if (currentLog && window.detectedJointsData[currentLog]) {
                        renderJointQaqcChart(currentLog);
                    }

                    loadWellLogs();

                } else if (data.task_status === 'FAILURE') {
                    var errMsg = 'Unknown error';
                    if (data.task_result && typeof data.task_result === 'string') {
                        errMsg = data.task_result;
                    } else if (data.task_result && data.task_result.error) {
                        errMsg = data.task_result.error;
                    }
                    showErrorMessage('Joint detection failed: ' + errMsg);
                } else {
                    setTimeout(checkResults, pollInterval);
                }
            },
            error: function (xhr) {
                var errorMsg = (xhr.responseJSON && xhr.responseJSON.error) ||
                    'Error checking detection results';
                showErrorMessage(errorMsg);
            }
        });
    }

    setTimeout(checkResults, pollInterval);
}

function refreshQaqcPanelLogList(logNames) {
    var $select = $('#joint_qaqc_log_select');
    var current = $select.val();
    $select.empty().append('<option value="">Select log...</option>');
    logNames.forEach(function (name) {
        var ready = window.detectedJointsData[name] ? ' \u2713' : '';
        $select.append('<option value="' + name + '">' + name + ready + '</option>');
    });
    if (current) $select.val(current);
}

function showJointQaqcPanel(logNames) {
    var $modal = $('#joint_qaqc_modal');
    var $select = $('#joint_qaqc_log_select');

    window._qaqcLogNames = logNames;

    $select.empty().append('<option value="">Select log...</option>');
    logNames.forEach(function (name) {
        var ready = window.detectedJointsData[name] ? ' \u2713' : '';
        $select.append('<option value="' + name + '">' + name + ready + '</option>');
    });

    $modal.addClass('show');
    $('#open_qaqc_modal_btn').show();

    if (logNames.length >= 1) {
        $select.val(logNames[0]);
        renderJointCandidatesTable(logNames[0]);
        setTimeout(function () {
            renderJointQaqcChartSmart(logNames[0]);
        }, 50);
    }
}

function renderJointCandidatesTable(logName) {
    var $tbody = $('#joint_qaqc_table_body');
    $tbody.empty();

    var logData = window.detectedJointsData[logName];
    if (!logData) {
        $tbody.append('<tr><td colspan="5" class="text-muted text-center py-3">No candidates detected for this log.</td></tr>');
        return;
    }

    if (!logData._allCandidates) {
        logData._allCandidates = logData.candidates || [];
    }
    var allCandidates = logData._allCandidates;

    if (allCandidates.length === 0) {
        $tbody.append('<tr><td colspan="5" class="text-muted text-center py-3">No candidates detected for this log.</td></tr>');
        return;
    }

    var approvedSet = logData._approvedIndices;
    var allApproved = !approvedSet;

    var allChecked = true;
    allCandidates.forEach(function (cand, idx) {
        var depth = typeof cand.depth === 'number' ? cand.depth.toFixed(2) : cand.depth;
        var score = typeof cand.score === 'number' ? cand.score.toFixed(1) : cand.score;
        var isChecked = allApproved || (approvedSet && approvedSet.indexOf(idx) >= 0);
        if (!isChecked) allChecked = false;
        var excludedClass = isChecked ? '' : ' class="joint-excluded"';

        $tbody.append(
            '<tr data-cand-idx="' + idx + '"' + excludedClass + '>' +
            '<td><input type="checkbox" class="joint-checkbox" data-cand-idx="' + idx + '"' +
            (isChecked ? ' checked' : '') + '></td>' +
            '<td>' + (cand.idx !== undefined ? cand.idx : idx) + '</td>' +
            '<td><input type="number" class="joint-depth-input" data-cand-idx="' + idx + '" value="' + depth + '" step="0.01"></td>' +
            '<td>' + ((cand.kind || '').indexOf('spike') >= 0 ? 'Connection' : ((cand.kind || '').indexOf('gradient') >= 0 ? 'Size-change' : (cand.kind || '-'))) + '</td>' +
            '<td>' + score + '</td>' +
            '</tr>'
        );
    });

    $('#joint_qaqc_select_all').prop('checked', allChecked);
}

/* ───── uPlot QA/QC Chart ───── */
window._uplotInstance = null;
window._uplotLogName = null;

function destroyUplot() {
    if (window._uplotInstance) {
        window._uplotInstance.destroy();
        window._uplotInstance = null;
    }
    var el = document.getElementById('joint_qaqc_uplot');
    if (el) el.innerHTML = '';
    var tip = document.getElementById('joint_qaqc_tooltip');
    if (tip) tip.style.display = 'none';
}

function getApprovedIndicesForChart(logName) {
    var logData = window.detectedJointsData[logName];
    if (!logData) return null;
    var $rows = $('#joint_qaqc_table_body tr');
    if ($rows.length > 0 && $rows.find('.joint-checkbox').length > 0) {
        var indices = [];
        $rows.each(function (i) {
            var $cb = $(this).find('.joint-checkbox');
            if ($cb.length && $cb.is(':checked')) indices.push(i);
        });
        return indices;
    }
    if (logData._approvedIndices) return logData._approvedIndices;
    var allCands = logData._allCandidates || logData.candidates || [];
    var indices = [];
    for (var i = 0; i < allCands.length; i++) indices.push(i);
    return indices;
}

function computeBoundariesFromApproved(logName) {
    var logData = window.detectedJointsData[logName];
    if (!logData) return [];
    var approvedSet = {};
    var indices = getApprovedIndicesForChart(logName);
    if (indices) {
        for (var i = 0; i < indices.length; i++) approvedSet[indices[i]] = true;
    }
    var allCands = logData._allCandidates || logData.candidates || [];
    var approved = [];
    for (var j = 0; j < allCands.length; j++) {
        if (approvedSet[j]) approved.push(allCands[j]);
    }
    approved.sort(function (a, b) { return a.depth - b.depth; });

    var boundaries = [];
    for (var k = 0; k < approved.length - 1; k++) {
        boundaries.push([approved[k].depth, approved[k + 1].depth]);
    }
    return boundaries;
}

function renderJointQaqcChart(logName, restoreScales) {
    var $placeholder = $('#joint_qaqc_chart_placeholder');
    var logData = window.detectedJointsData[logName];

    if (!logData || !logData.chart_depths || logData.chart_depths.length === 0) {
        destroyUplot();
        $placeholder.text('No chart data available').show();
        return;
    }

    $placeholder.hide();
    destroyUplot();
    window._uplotLogName = logName;

    var depths = logData.chart_depths;
    var values = logData.chart_values;
    var allCands = logData._allCandidates || logData.candidates || [];
    var approvedIndices = getApprovedIndicesForChart(logName);
    var approvedSet = {};
    if (approvedIndices) {
        for (var i = 0; i < approvedIndices.length; i++) approvedSet[approvedIndices[i]] = true;
    }
    var boundaries = computeBoundariesFromApproved(logName);

    var wrapEl = document.getElementById('joint_qaqc_chart_wrap');
    var targetEl = document.getElementById('joint_qaqc_uplot');
    var chartWidth = wrapEl.clientWidth - 2;
    var chartHeight = wrapEl.clientHeight - 2;

    if (chartWidth < 10 || chartHeight < 10) {
        setTimeout(function () { renderJointQaqcChart(logName); }, 100);
        return;
    }

    var tooltipEl = document.getElementById('joint_qaqc_tooltip');
    if (!tooltipEl) {
        tooltipEl = document.createElement('div');
        tooltipEl.id = 'joint_qaqc_tooltip';
        tooltipEl.style.cssText = 'position:absolute;pointer-events:none;background:rgba(30,30,46,0.92);border:1px solid #666;border-radius:4px;padding:4px 8px;color:#eee;font-size:11px;white-space:nowrap;z-index:9999;display:none;';
        wrapEl.style.position = 'relative';
        wrapEl.appendChild(tooltipEl);
    }

    var opts = {
        width: chartWidth,
        height: chartHeight,
        cursor: {
            drag: { x: true, y: false, uni: 50 },
            y: true
        },
        select: {
            show: true
        },
        legend: { show: false },
        axes: [
            {
                stroke: '#aaa',
                grid: { stroke: 'rgba(255,255,255,0.08)', width: 1 },
                ticks: { stroke: 'rgba(255,255,255,0.15)', width: 1 },
                label: 'Depth [m]',
                labelGap: 4,
                font: '11px system-ui',
                labelFont: '12px system-ui',
                side: 3
            },
            {
                stroke: '#aaa',
                grid: { stroke: 'rgba(255,255,255,0.08)', width: 1 },
                ticks: { stroke: 'rgba(255,255,255,0.15)', width: 1 },
                label: 'Average Caliper Measurement',
                labelGap: 4,
                font: '11px system-ui',
                labelFont: '12px system-ui',
                side: 0
            }
        ],
        scales: {
            x: { time: false, auto: true, ori: 1, dir: -1 },
            y: { auto: true, ori: 0, dir: 1 }
        },
        series: [
            {},
            {
                stroke: '#cccccc',
                width: 1,
                label: 'Caliper'
            }
        ],
        hooks: {
            draw: [
                function (u) {
                    var ctx = u.ctx;
                    var xMin = u.scales.x.min;
                    var xMax = u.scales.x.max;

                    var left = u.bbox.left;
                    var top = u.bbox.top;
                    var w = u.bbox.width;
                    var h = u.bbox.height;

                    ctx.save();

                    var visibleRange = xMax - xMin;
                    var pixelsPerUnit = h / visibleRange;
                    var showLabels = pixelsPerUnit > 2;

                    ctx.font = '11px system-ui';
                    ctx.textBaseline = 'bottom';

                    var activePositions = [];

                    for (var ci = 0; ci < allCands.length; ci++) {
                        var cand = allCands[ci];
                        var depth = cand.depth;
                        if (depth < xMin || depth > xMax) continue;

                        var yPos = u.valToPos(depth, 'x', true);
                        var isActive = !!approvedSet[ci];
                        var isSpike = (cand.kind || '').indexOf('spike') >= 0;
                        var color;

                        if (isActive) {
                            color = isSpike ? 'rgba(255,80,80,0.6)' : 'rgba(77,171,247,0.6)';
                            ctx.strokeStyle = color;
                            ctx.lineWidth = 1;
                            activePositions.push({ depth: depth, yPos: yPos });
                        } else {
                            color = 'rgba(128,128,128,0.25)';
                            ctx.strokeStyle = color;
                            ctx.lineWidth = 0.5;
                            ctx.setLineDash([3, 3]);
                        }

                        ctx.beginPath();
                        ctx.moveTo(left, yPos);
                        ctx.lineTo(left + w, yPos);
                        ctx.stroke();

                        if (!isActive) ctx.setLineDash([]);

                        if (isActive && showLabels) {
                            var idx = cand.idx !== undefined ? cand.idx : ci;
                            var rawKind = (cand.kind || '?');
                            var kindStr = rawKind.indexOf('spike') >= 0 ? 'Connection' : (rawKind.indexOf('gradient') >= 0 ? 'Size-change' : rawKind);
                            var lbl = 'idx=' + idx + '  ' + kindStr + '  depth=' + depth.toFixed(1) + 'm  score=' + (cand.score || 0).toFixed(0);
                            ctx.fillStyle = color;
                            ctx.textAlign = 'right';
                            ctx.fillText(lbl, left + w - 3, yPos - 2);
                        }
                    }

                    if (showLabels && activePositions.length > 1) {
                        activePositions.sort(function (a, b) { return a.depth - b.depth; });
                        ctx.font = '10px system-ui';
                        ctx.fillStyle = 'rgba(255,220,100,0.8)';
                        ctx.textAlign = 'left';
                        ctx.textBaseline = 'middle';
                        for (var di = 1; di < activePositions.length; di++) {
                            var dist = Math.abs(activePositions[di].depth - activePositions[di - 1].depth);
                            var midY = (activePositions[di].yPos + activePositions[di - 1].yPos) / 2;
                            var pixGap = Math.abs(activePositions[di].yPos - activePositions[di - 1].yPos);
                            if (pixGap > 14) {
                                ctx.fillText('\u2195 ' + dist.toFixed(2) + ' m', left + 6, midY);
                            }
                        }
                    }

                    ctx.restore();
                }
            ],
            setCursor: [
                function (u) {
                    var idx = u.cursor.idx;
                    if (idx == null || idx < 0 || idx >= depths.length) {
                        tooltipEl.style.display = 'none';
                        return;
                    }
                    var depthVal = depths[idx];
                    var calVal = values[idx];
                    var yPos = u.valToPos(depthVal, 'x', true);
                    var xPos = u.valToPos(calVal, 'y', true);
                    tooltipEl.innerHTML = '<b>Depth:</b> ' + depthVal.toFixed(2) + ' m<br><b>Caliper:</b> ' + calVal.toFixed(3);
                    tooltipEl.style.display = 'block';
                    var tipX = xPos + 12;
                    var tipY = yPos - 10;
                    if (tipX + tooltipEl.offsetWidth > wrapEl.clientWidth) tipX = xPos - tooltipEl.offsetWidth - 8;
                    if (tipY < 0) tipY = yPos + 12;
                    tooltipEl.style.left = tipX + 'px';
                    tooltipEl.style.top = tipY + 'px';
                }
            ]
        }
    };

    var data = [depths, values];

    window._uplotInstance = new uPlot(opts, data, targetEl);

    if (restoreScales) {
        if (restoreScales.x) window._uplotInstance.setScale('x', restoreScales.x);
        if (restoreScales.y) window._uplotInstance.setScale('y', restoreScales.y);
    }
}

function renderJointQaqcChartSmart(logName) {
    renderJointQaqcChart(logName);
}

function updateJointQaqcChart() {
    var logName = $('#joint_qaqc_log_select').val();
    if (!logName) return;
    var savedScales = null;
    if (window._uplotInstance) {
        savedScales = {
            x: { min: window._uplotInstance.scales.x.min, max: window._uplotInstance.scales.x.max },
            y: { min: window._uplotInstance.scales.y.min, max: window._uplotInstance.scales.y.max }
        };
    }
    renderJointQaqcChart(logName, savedScales);
}

/* ───── End uPlot QA/QC Chart ───── */

/* ───── Finger Detail Modal ───── */
window._fingerDetailUplot = null;

function destroyFingerDetailUplot() {
    if (window._fingerDetailUplot) {
        window._fingerDetailUplot.destroy();
        window._fingerDetailUplot = null;
    }
    var el = document.getElementById('finger_detail_uplot');
    if (el) el.innerHTML = '';
}

function openFingerDetailModal(preselectedJointIdx) {
    var $modal = $('#finger_detail_modal');
    var $logSelect = $('#finger_detail_log_select');
    var $jointSelect = $('#finger_detail_joint_select');

    if (!window.lastProcessedLogsData) {
        showInfoMessage('No processed logs available.');
        return;
    }

    var logKeys = Object.keys(window.lastProcessedLogsData);
    if (logKeys.length === 0) {
        showInfoMessage('No processed logs available.');
        return;
    }

    $logSelect.empty().append('<option value="">Select log...</option>');
    logKeys.forEach(function (name) {
        var dateLabel = (window.logDateByName && window.logDateByName[name]) ? ' (' + window.logDateByName[name] + ')' : '';
        $logSelect.append('<option value="' + name + '">' + name + dateLabel + '</option>');
    });

    $logSelect.val(logKeys[0]);
    populateFingerDetailJoints(logKeys[0]);

    $modal.addClass('show');

    if (preselectedJointIdx !== undefined && preselectedJointIdx !== null) {
        setTimeout(function () {
            var $opts = $jointSelect.find('option');
            if (preselectedJointIdx + 1 < $opts.length) {
                $jointSelect.val($opts.eq(preselectedJointIdx + 1).val());
                $jointSelect.trigger('change');
            }
        }, 50);
    }
}

function populateFingerDetailJoints(logName) {
    var $jointSelect = $('#finger_detail_joint_select');
    $jointSelect.empty().append('<option value="">Select joint...</option>');

    if (!logName || !window.lastProcessedLogsData || !window.lastProcessedLogsData[logName]) return;

    var logData = window.lastProcessedLogsData[logName];
    if (!Array.isArray(logData)) return;

    logData.forEach(function (row, idx) {
        var label = 'Joint ' + (row['Tally Joint No.'] || row['Joint No.'] || (idx + 1)) +
            ' (' + (row['Top Depth [m]'] || '?') + ' – ' + (row['Bottom Depth [m]'] || '?') + ' m)';
        var val = JSON.stringify({
            top: row['Top Depth [m]'],
            bottom: row['Bottom Depth [m]'],
            idx: idx
        });
        $jointSelect.append('<option value=\'' + val + '\'>' + label + '</option>');
    });
}

function loadFingerDetailData(logName, topDepth, bottomDepth, jointIdx) {
    var well_name = $('#select_well').val();
    if (!well_name) return;

    $('#finger_detail_placeholder').text('Loading...').show();
    destroyFingerDetailUplot();

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_joint_finger_data',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            log_name: logName,
            top_depth: topDepth,
            bottom_depth: bottomDepth,
            joint_idx: jointIdx
        }),
        success: function (data) {
            $('#finger_detail_placeholder').hide();
            renderFingerDetailChart(data);
        },
        error: function (xhr) {
            var msg = xhr.responseJSON ? xhr.responseJSON.error : 'Error loading finger data';
            $('#finger_detail_placeholder').text(msg).show();
        }
    });
}

function renderFingerDetailChart(data) {
    var wrapEl = document.getElementById('finger_detail_uplot_wrap');
    var targetEl = document.getElementById('finger_detail_uplot');

    var chartWidth = wrapEl.clientWidth - 2;
    var chartHeight = wrapEl.clientHeight - 2;

    if (chartWidth < 10 || chartHeight < 10) {
        setTimeout(function () { renderFingerDetailChart(data); }, 100);
        return;
    }

    var depths = data.depths;
    var fingerCols = data.finger_cols;
    var maxVals = data.max;
    var minVals = data.min;
    var meanVals = data.mean;
    var maxFinger = data.max_finger || [];
    var minFinger = data.min_finger || [];

    var seriesData = [depths];
    var seriesDefs = [{}];

    fingerCols.forEach(function (col) {
        seriesData.push(data.fingers[col]);
        seriesDefs.push({
            stroke: 'rgba(150,150,150,0.35)',
            width: 1,
            label: col
        });
    });

    seriesData.push(maxVals);
    seriesDefs.push({ stroke: '#ff5555', width: 2, label: 'Max' });

    seriesData.push(minVals);
    seriesDefs.push({ stroke: '#5599ff', width: 2, label: 'Min' });

    seriesData.push(meanVals);
    seriesDefs.push({ stroke: '#ffffff', width: 2, label: 'Mean' });


    var tooltipEl = document.getElementById('finger_detail_tooltip');
    if (!tooltipEl) {
        tooltipEl = document.createElement('div');
        tooltipEl.id = 'finger_detail_tooltip';
        tooltipEl.style.cssText = 'position:absolute;pointer-events:none;background:rgba(30,30,46,0.92);border:1px solid #666;border-radius:4px;padding:4px 8px;color:#eee;font-size:11px;white-space:nowrap;z-index:9999;display:none;';
        wrapEl.style.position = 'relative';
        wrapEl.appendChild(tooltipEl);
    }

    var opts = {
        width: chartWidth,
        height: chartHeight,
        cursor: {
            drag: { x: true, y: false, uni: 50 },
            y: true
        },
        select: { show: true },
        legend: { show: true },
        axes: [
            {
                stroke: '#aaa',
                grid: { stroke: 'rgba(255,255,255,0.08)', width: 1 },
                ticks: { stroke: 'rgba(255,255,255,0.15)', width: 1 },
                label: 'Depth [m]',
                labelGap: 4,
                font: '11px system-ui',
                labelFont: '12px system-ui',
                side: 3
            },
            {
                stroke: '#aaa',
                grid: { stroke: 'rgba(255,255,255,0.08)', width: 1 },
                ticks: { stroke: 'rgba(255,255,255,0.15)', width: 1 },
                label: 'Radius [inch]',
                labelGap: 4,
                font: '11px system-ui',
                labelFont: '12px system-ui',
                side: 0
            }
        ],
        scales: {
            x: { time: false, auto: true, ori: 1, dir: -1 },
            y: { auto: true, ori: 0, dir: 1 }
        },
        series: seriesDefs,
        hooks: {
            setCursor: [
                function (u) {
                    var idx = u.cursor.idx;
                    if (idx == null || idx < 0 || idx >= depths.length) {
                        tooltipEl.style.display = 'none';
                        return;
                    }
                    var depthVal = depths[idx];
                    var html = '<b>Depth:</b> ' + depthVal.toFixed(2) + ' m<br>' +
                        '<b>Max:</b> ' + maxVals[idx].toFixed(4) + ' (' + (maxFinger[idx] || '?') + ')<br>' +
                        '<b>Min:</b> ' + minVals[idx].toFixed(4) + ' (' + (minFinger[idx] || '?') + ')<br>' +
                        '<b>Mean:</b> ' + meanVals[idx].toFixed(4);
                    tooltipEl.innerHTML = html;
                    tooltipEl.style.display = 'block';
                    var yPos = u.valToPos(depthVal, 'x', true);
                    var xPos = u.valToPos(meanVals[idx], 'y', true);
                    var tipX = xPos + 12;
                    var tipY = yPos - 10;
                    if (tipX + tooltipEl.offsetWidth > wrapEl.clientWidth) tipX = xPos - tooltipEl.offsetWidth - 8;
                    if (tipY < 0) tipY = yPos + 12;
                    tooltipEl.style.left = tipX + 'px';
                    tooltipEl.style.top = tipY + 'px';
                }
            ]
        }
    };

    window._fingerDetailUplot = new uPlot(opts, seriesData, targetEl);
}

/* ───── End Finger Detail Modal ───── */

function approveJoints() {
    var well_name = $('#select_well').val();
    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }

    var logName = $('#joint_qaqc_log_select').val();
    if (!logName) {
        showErrorMessage('Please select a log first');
        return;
    }

    var logData = window.detectedJointsData[logName] || {};
    if (!logData._allCandidates) {
        logData._allCandidates = logData.candidates || [];
    }
    var allCandidates = logData._allCandidates;

    var checkedIdxs = [];
    $('#joint_qaqc_table_body .joint-checkbox:checked').each(function () {
        checkedIdxs.push(parseInt($(this).attr('data-cand-idx')));
    });
    var approvedCandidates = allCandidates.filter(function (_, i) {
        return checkedIdxs.indexOf(i) >= 0;
    });

    var approvedJoints = {};
    approvedJoints[logName] = approvedCandidates;

    showInfoMessage('Saving approved joints...');

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_approved_joints',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            approved_joints: approvedJoints
        }),
        success: function () {
            logData._approvedIndices = checkedIdxs;
            updateJointQaqcChart();
            showSuccessMessage('Approved joints saved for ' + logName +
                ' (' + approvedCandidates.length + '/' + allCandidates.length + ' candidates)');
        },
        error: function (xhr) {
            var errorMsg = (xhr.responseJSON && xhr.responseJSON.error) ||
                'Error saving approved joints';
            showErrorMessage(errorMsg);
        }
    });
}

function loadProcessedLogs(logNames, options = {}) {
    const well_name = $('#select_well').val();
    const silent = !!options.silent;
    
    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }
    
    if (!silent) {
        showInfoMessage('Loading processed log data...');
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_processed_logs',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            selected_logs: logNames
        }),
        success: function (data) {
            if (!silent) {
                showSuccessMessage('Processed logs loaded successfully!');
            }
            
            if (data.results && data.results.processedLogs) {
                if (!window.lastProcessedLogsData) window.lastProcessedLogsData = {};
                Object.assign(window.lastProcessedLogsData, data.results.processedLogs);
                populateColumnSelector();
                renderProcessedLogChart();
            }
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Error loading processed logs';
            if (!silent) {
                showErrorMessage(errorMsg);
            } else {
                console.error(errorMsg);
            }
        }
    });
}

function uploadLog() {
    const well_name = $('#select_well').val();
    const fileInput = $('#log_upload')[0];
    
    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }
    
    if (!fileInput.files || fileInput.files.length === 0) {
        showErrorMessage('Please select a file to upload');
        return;
    }
    
    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.las')) {
        showErrorMessage('Please select a .las file');
        return;
    }
    
    const formData = new FormData();
    formData.append('las_file', file);
    formData.append('selected_well', well_name);
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/upload_log',
        data: formData,
        processData: false,
        contentType: false,
        success: function (data) {
            showSuccessMessage('Log uploaded successfully');
            fileInput.value = ''; // Clear the file input
            loadWellLogs(); // Reload the logs list
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Error uploading log';
            showErrorMessage(errorMsg);
        }
    });
}

function processCaliperLogs() {
    const well_name = $('#select_well').val();
    
    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }

    var logsToProcess = (window.detectedLogsList || []).slice();
    if (logsToProcess.length === 0) {
        showErrorMessage('No detected logs to process. Run "Detect Joints" first.');
        return;
    }
    
    showInfoMessage(`Starting processing of ${logsToProcess.length} caliper logs... This may take a moment.`);
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/process_caliper_logs',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            selected_logs: logsToProcess,
            use_approved_joints: true
        }),
        success: function (data) {
            if (data.task_id) {
                showInfoMessage('Processing started. Please wait...');
                pollProcessingResults(data.task_id, logsToProcess);
            } else {
                showErrorMessage('Failed to start processing: No task ID returned');
            }
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Error starting caliper logs processing';
            showErrorMessage(errorMsg);
        }
    });
}

function pollProcessingResults(taskId, selectedLogs) {
    const pollInterval = 2000; // Poll every 2 seconds
    
    function checkResults() {
        $.ajax({
            type: 'POST',
            url: '/app/wellintegrity/get_processing_results',
            contentType: 'application/json',
            data: JSON.stringify({
                task_id: taskId
            }),
            success: function (data) {
                if (data.task_status === 'SUCCESS') {
                    showSuccessMessage('Caliper logs processed successfully!');
                    console.log('Processing results:', data.task_result);
                    
                    // Refresh the logs list to show updated processing status
                    loadWellLogs();
                    
                    // Display the results using the new structure
                    if (data.task_result && data.task_result.results) {
                        displayProcessingResults(data.task_result.results);
                        // Corrosion rate is only calculated when user clicks Calculate
                    } else {
                        console.warn('No processed logs data in response:', data);
                    }
                } else if (data.task_status === 'FAILURE') {
                    showErrorMessage('Processing failed: ' + (data.task_result?.error || 'Unknown error'));
                } else if (data.task_status === 'PENDING') {
                    // Still processing, continue polling
                    setTimeout(checkResults, pollInterval);
                } else {
                    // Other statuses like RETRY
                    showInfoMessage('Processing status: ' + data.task_status);
                    setTimeout(checkResults, pollInterval);
                }
            },
            error: function (xhr) {
                const errorMsg = xhr.responseJSON?.error || 'Error checking processing results';
                showErrorMessage(errorMsg);
            }
        });
    }
    
    // Start polling
    setTimeout(checkResults, pollInterval);
}

function populateColumnSelector() {
    const $colSelect = $('#processed_log_column_select');
    const currentVal = $colSelect.val();
    $colSelect.empty();

    if (!window.lastProcessedLogsData) return;
    const allLogKeys = Object.keys(window.lastProcessedLogsData);
    if (allLogKeys.length === 0) return;

    const firstLogData = window.lastProcessedLogsData[allLogKeys[0]];
    if (!firstLogData || !Array.isArray(firstLogData) || firstLogData.length === 0) return;

    const columns = Object.keys(firstLogData[0]).filter(
        c => PROCESSED_LOG_NON_PLOT_COLUMNS.indexOf(c) === -1
    );
    columns.forEach(col => {
        $colSelect.append(`<option value="${col}">${col}</option>`);
    });

    if (currentVal && columns.includes(currentVal)) {
        $colSelect.val(currentVal);
    } else {
        $colSelect.val(columns[0] || '');
    }

    $('#open_finger_detail_btn').show();
}

function renderProcessedLogChart() {
    const selectedLogs = getSelectedProcessedLogs();
    const selectedColumn = $('#processed_log_column_select').val();
    const chartDiv = 'processed_log_chart';
    const chartElement = document.getElementById(chartDiv);

    if (selectedLogs.length === 0 || !selectedColumn || !window.lastProcessedLogsData) {
        Plotly.purge(chartDiv);
        return;
    }

    const depthKind = getProcessedLogPenetrationDepthKind(selectedColumn);
    const hoverTemplate = buildProcessedLogHoverTemplate(selectedColumn, depthKind);

    const traces = [];
    const seriesForLegend = [];
    selectedLogs.forEach(logName => {
        const logData = window.lastProcessedLogsData[logName];
        if (!logData || !Array.isArray(logData) || logData.length === 0) return;

        const x = logData.map(r => r['Tally Seq. No.'] || r['Tally Seq.']);
        const y = logData.map(r => {
            const v = r[selectedColumn];
            return (v === null || v === undefined || v === 'None') ? null : Number(v);
        });

        traces.push({
            x: x,
            y: y,
            customdata: logData.map(r => {
                const rowData = [
                    r['Tally Joint No.'] || r['Joint No.'],
                    r['Top Depth [m]'],
                    r['Bottom Depth [m]'],
                    r['Length [m]'],
                    r['Nominal IR [inch]'],
                    r['Nominal OR [inch]'],
                    null,
                    r['Ovality [%]'],
                    r['Seq. No.']
                ];
                if (depthKind) {
                    rowData[6] = getProcessedLogPenetrationDepth(r, depthKind);
                }
                return rowData;
            }),
            hovertemplate: hoverTemplate,
            name: (window.logDateByName && window.logDateByName[logName]) ? window.logDateByName[logName] : 'No date',
            mode: 'lines+markers',
            marker: { size: 4 }
        });
        seriesForLegend.push(y);
    });

    function getAdaptiveLegend(seriesList) {
        // Prefer the corner with less data density.
        // Score corners using first/last data segment and low/high y occupancy.
        const scores = {
            topRight: 0,
            bottomRight: 0,
            topLeft: 0,
            bottomLeft: 0
        };

        seriesList.forEach(arr => {
            const vals = (arr || []).filter(v => Number.isFinite(v));
            if (vals.length < 3) return;
            const minY = Math.min(...vals);
            const maxY = Math.max(...vals);
            const span = Math.max(maxY - minY, 1e-9);
            const leftY = vals[Math.max(0, Math.floor(vals.length * 0.1))];
            const rightY = vals[Math.min(vals.length - 1, Math.floor(vals.length * 0.9))];
            const leftNorm = (leftY - minY) / span;
            const rightNorm = (rightY - minY) / span;

            scores.topLeft += leftNorm > 0.55 ? 1 : 0;
            scores.bottomLeft += leftNorm < 0.45 ? 1 : 0;
            scores.topRight += rightNorm > 0.55 ? 1 : 0;
            scores.bottomRight += rightNorm < 0.45 ? 1 : 0;
        });

        const entries = Object.entries(scores).sort((a, b) => a[1] - b[1]);
        const best = entries[0] ? entries[0][0] : 'topRight';
        if (best === 'topLeft') {
            return { x: 0.01, y: 0.99, xanchor: 'left', yanchor: 'top' };
        }
        if (best === 'bottomLeft') {
            return { x: 0.01, y: 0.01, xanchor: 'left', yanchor: 'bottom' };
        }
        if (best === 'bottomRight') {
            return { x: 0.99, y: 0.01, xanchor: 'right', yanchor: 'bottom' };
        }
        return { x: 0.99, y: 0.99, xanchor: 'right', yanchor: 'top' };
    }

    const legendPos = getAdaptiveLegend(seriesForLegend);

    let plotHeight = 260;
    const panelBody = document.querySelector('#processed_logs_panel .panel-body-wrap');
    if (panelBody && panelBody.clientHeight > 0) {
        plotHeight = Math.max(panelBody.clientHeight - 6, 180);
    } else if (chartElement && chartElement.clientHeight > 0) {
        plotHeight = Math.max(chartElement.clientHeight - 6, 180);
    }
    const layout = {
        paper_bgcolor: '#2a2d47',
        plot_bgcolor: '#23243a',
        font: { color: '#ccc', size: 10 },
        xaxis: {
            title: { text: 'Tally Seq. No.', font: { size: 11 }, standoff: 6 },
            gridcolor: '#444',
            automargin: true,
            tickfont: { size: 10 }
        },
        yaxis: {
            title: { text: selectedColumn, font: { size: 11 }, standoff: 6 },
            gridcolor: '#444',
            automargin: true,
            tickfont: { size: 10 }
        },
        margin: { t: 8, r: 8, b: 26, l: 42 },
        legend: {
            orientation: 'v',
            x: legendPos.x,
            xanchor: legendPos.xanchor,
            y: legendPos.y,
            yanchor: legendPos.yanchor,
            font: { size: 9 },
            bgcolor: 'rgba(35,36,58,0.65)',
            bordercolor: '#444',
            borderwidth: 1
        },
        autosize: true,
        height: plotHeight,
        hovermode: 'closest'
    };

    Plotly.newPlot(chartDiv, traces, layout, { responsive: true }).then(function() {
        if (chartElement) {
            Plotly.Plots.resize(chartElement);
        }
        chartElement.removeAllListeners && chartElement.removeAllListeners('plotly_click');
        chartElement.on('plotly_click', function (eventData) {
            if (!eventData || !eventData.points || eventData.points.length === 0) return;
            var pt = eventData.points[0];
            var pointIdx = pt.pointIndex;
            var traceIdx = pt.curveNumber;
            if (traceIdx < selectedLogs.length) {
                openFingerDetailModal(pointIdx);
                var logName = selectedLogs[traceIdx];
                setTimeout(function () {
                    $('#finger_detail_log_select').val(logName).trigger('change');
                    setTimeout(function () {
                        var $opts = $('#finger_detail_joint_select option');
                        if (pointIdx + 1 < $opts.length) {
                            $('#finger_detail_joint_select').val($opts.eq(pointIdx + 1).val()).trigger('change');
                        }
                    }, 100);
                }, 50);
            }
        });
    });
}

function displayProcessingResults(results) {
    if (!results.processedLogs || typeof results.processedLogs !== 'object') return;

    window.lastProcessedLogsData = window.lastProcessedLogsData || {};
    Object.assign(window.lastProcessedLogsData, results.processedLogs);

    const logNames = Object.keys(results.processedLogs);
    if (logNames.length === 0) return;

    const availableSet = new Set(window.processedLogsAvailable || []);
    logNames.forEach(name => {
        availableSet.add(name);
    });
    const selectedSet = new Set(getSelectedProcessedLogs());
    logNames.forEach(name => selectedSet.add(name));
    window.processedLogsAvailable = Array.from(availableSet);
    renderProcessedLogCheckboxDropdown(window.processedLogsAvailable, Array.from(selectedSet));

    populateColumnSelector();
    renderProcessedLogChart();
}


// WIMS card: annulus monitors (annulus pressure tags plotted with configurable lookback)
let wimsAnnulusMonitors = [];
/** Per-monitor alarm state: ok | alarm | acknowledged (while still out of limit). */
let wimsAnnulusAlarmState = {};
/** Pending limit-breach alarms waiting for acknowledge. */
let wimsAnnulusAlarmQueue = [];
// Cached drawn items from schematic (element_name, element_type, patch_type) for "From schematic" element picker
let wimsCachedDrawnItems = [];
// Cached schematic JSON used for WIMS panel (so we can re-call generate with item_colors for recoloring)
let wimsCachedSchematicData = null;

var WBE_ELEMENT_KEY_SEP = '\u001f';

function buildWbeElementKey(elementName, elementType) {
    return (elementName || '').trim() + WBE_ELEMENT_KEY_SEP + (elementType || '').trim();
}

function parseWbeElementKey(key) {
    if (!key) return { element_name: '', element_type: '' };
    var idx = key.indexOf(WBE_ELEMENT_KEY_SEP);
    if (idx === -1) return { element_name: key.trim(), element_type: '' };
    return {
        element_name: key.slice(0, idx).trim(),
        element_type: key.slice(idx + 1).trim()
    };
}

function parseBarrierElementCell(text) {
    var cell = (text || '').trim();
    if (cell.indexOf(' | ') === -1) return { element_name: cell, element_type: '' };
    var parts = cell.split(' | ');
    return {
        element_name: parts[0].trim(),
        element_type: parts.slice(1).join(' | ').trim()
    };
}

function formatBarrierElementLabel(elementName, elementType) {
    if (!elementType) return elementName || '';
    return (elementName || '') + ' | ' + elementType;
}

function getUniqueDrawnElementCombos(drawnItems) {
    var list = drawnItems || [];
    var seen = {};
    var unique = [];
    list.forEach(function(item) {
        var name = (item.element_name || item.name || item.id || '').trim();
        var typeVal = (item.element_type || '').trim();
        if (!name) return;
        var key = buildWbeElementKey(name, typeVal);
        if (seen[key]) return;
        seen[key] = true;
        unique.push({ element_name: name, element_type: typeVal, key: key });
    });
    unique.sort(function(a, b) {
        var la = formatBarrierElementLabel(a.element_name, a.element_type);
        var lb = formatBarrierElementLabel(b.element_name, b.element_type);
        return la.localeCompare(lb);
    });
    return unique;
}

function getPatchesForDrawnElement(elementName, elementType) {
    var patches = [];
    var seen = {};
    (wimsCachedDrawnItems || []).forEach(function(item) {
        var name = (item.element_name || item.name || item.id || '').trim();
        var typeVal = (item.element_type || '').trim();
        var pt = (item.patch_type || '').trim();
        if (name !== elementName || typeVal !== elementType || !pt || seen[pt]) return;
        seen[pt] = true;
        patches.push(pt);
    });
    patches.sort();
    return patches;
}

/** Derive display group key for a patch; pairs *_left / *_right under one label. */
function getWbePatchGroupKey(patch) {
    var leftMatch = patch.match(/^(.*)_left(_.*)?$/);
    if (leftMatch) return leftMatch[1] + (leftMatch[2] || '');
    var rightMatch = patch.match(/^(.*)_right(_.*)?$/);
    if (rightMatch) return rightMatch[1] + (rightMatch[2] || '');
    return patch;
}

/** Group patch_type values into checklist rows (left+right combined when both exist). */
function groupWbePatchesForDisplay(patchList) {
    var groupsByKey = {};
    var order = [];
    (patchList || []).forEach(function(pt) {
        var groupKey = getWbePatchGroupKey(pt);
        if (!groupsByKey[groupKey]) {
            groupsByKey[groupKey] = { label: groupKey, patches: [] };
            order.push(groupKey);
        }
        if (groupsByKey[groupKey].patches.indexOf(pt) === -1) {
            groupsByKey[groupKey].patches.push(pt);
        }
    });
    order.sort(function(a, b) { return a.localeCompare(b); });
    return order.map(function(key) {
        var group = groupsByKey[key];
        group.patches.sort();
        return group;
    });
}

function formatWbePatchGroupLabel(group) {
    if (group.patches.length > 1) {
        return group.label + ' (left & right)';
    }
    return group.label;
}

function isWbePatchGroupFullySelected(group, selectedSet) {
    return group.patches.every(function(pt) { return selectedSet.has(pt); });
}

function populateWbeElementSelect($select, selectedKey) {
    var combos = getUniqueDrawnElementCombos(wimsCachedDrawnItems);
    $select.empty().append('<option value="">— Select from schematic —</option>');
    combos.forEach(function(item) {
        var label = formatBarrierElementLabel(item.element_name, item.element_type);
        $select.append(
            $('<option></option>').attr('value', item.key).text(label)
        );
    });
    if (selectedKey) $select.val(selectedKey);
}

function renderWbePatchChecklist(prefix, elementName, elementType, selectedPatches) {
    var $wrap = $('#' + prefix + '_element_patches_wrap');
    var $list = $('#' + prefix + '_element_patches_list');
    if (!elementName) {
        $wrap.hide();
        $list.empty();
        return;
    }
    var patches = getPatchesForDrawnElement(elementName, elementType);
    var groups = groupWbePatchesForDisplay(patches);
    var selectedSet = new Set(Array.isArray(selectedPatches) ? selectedPatches : patches);
    $list.empty();
    if (groups.length === 0) {
        $list.append('<p class="text-muted small mb-0">No patches found for this element.</p>');
        $wrap.show();
        return;
    }
    groups.forEach(function(group) {
        var checked = isWbePatchGroupFullySelected(group, selectedSet) ? 'checked' : '';
        var esc = function(t) { var d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; };
        var html = '<label><input type="checkbox" class="wims-patch-checkbox" value="' +
            escapeHtmlAttr(group.label) + '" data-patch-types="' +
            escapeHtmlAttr(JSON.stringify(group.patches)) + '" ' + checked + '><span>' +
            esc(formatWbePatchGroupLabel(group)) + '</span></label>';
        $list.append(html);
    });
    $wrap.show();
}

function readWbePatchSelection(prefix) {
    var result = [];
    $('#' + prefix + '_element_patches_list input.wims-patch-checkbox:checked').each(function() {
        var raw = this.getAttribute('data-patch-types');
        if (raw) {
            try {
                JSON.parse(raw).forEach(function(pt) {
                    if (result.indexOf(pt) === -1) result.push(pt);
                });
            } catch (e) {
                result.push(this.value);
            }
        } else {
            result.push(this.value);
        }
    });
    return result;
}

function escapeHtmlAttr(text) {
    return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function applyBarrierRowDataAttrs($tr, elementName, elementType, patchTypes) {
    $tr.attr('data-element-name', elementName || '');
    $tr.attr('data-element-type', elementType || '');
    if (Array.isArray(patchTypes) && patchTypes.length > 0) {
        $tr.attr('data-patch-types', JSON.stringify(patchTypes));
    } else {
        $tr.removeAttr('data-patch-types');
    }
}

function readBarrierRowPatchTypes($tr) {
    var raw = $tr.attr('data-patch-types');
    if (!raw) return null;
    try {
        var parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : null;
    } catch (e) {
        return null;
    }
}

function openWbeAddElementModal() {
    var combos = getUniqueDrawnElementCombos(wimsCachedDrawnItems);
    populateWbeElementSelect($('#wims_add_element_from_schematic'), '');
    $('#wims_add_element_patches_wrap').hide();
    $('#wims_add_element_patches_list').empty();
    updateWbeDisplayNameField('wims_add', null);
    $('#wims_add_element_no_schematic').toggle(combos.length === 0);
    resetWimsAddPartialRecolorFields();
    $('#wims_add_element_modal').addClass('show');
}

function openWbeEditElementModal($tr) {
    var parsed = parseBarrierElementCell($tr.find('td').eq(0).text().trim());
    var elementName = $tr.attr('data-element-name') || parsed.element_name;
    var elementType = $tr.attr('data-element-type') || parsed.element_type;
    var selectedKey = buildWbeElementKey(elementName, elementType);
    var patchTypes = readBarrierRowPatchTypes($tr);
    var combos = getUniqueDrawnElementCombos(wimsCachedDrawnItems);
    populateWbeElementSelect($('#wims_edit_element_from_schematic'), selectedKey);
    $('#wims_edit_element_no_schematic').toggle(combos.length === 0);
    if (elementName && elementType) {
        renderWbePatchChecklist('wims_edit', elementName, elementType, patchTypes);
        updateWbeDisplayNameField('wims_edit', { element_name: elementName, element_type: elementType }, $tr.find('td').eq(0).text().trim());
    } else {
        $('#wims_edit_element_patches_wrap').hide();
        $('#wims_edit_element_patches_list').empty();
        updateWbeDisplayNameField('wims_edit', null);
    }
}

function readWbeElementFromSelect(prefix) {
    var key = ($('#' + prefix + '_element_from_schematic').val() || '').trim();
    if (!key) return null;
    var parsed = parseWbeElementKey(key);
    if (!parsed.element_name) return null;
    return parsed;
}

function getDefaultWbeDisplayName(elementName, elementType) {
    return formatBarrierElementLabel(elementName, elementType);
}

function updateWbeDisplayNameField(prefix, parsed, displayName) {
    var $wrap = $('#' + prefix + '_element_display_name_wrap');
    var $input = $('#' + prefix + '_element_display_name');
    if (!parsed) {
        $wrap.hide();
        $input.val('');
        return;
    }
    $wrap.show();
    $input.val(displayName != null ? displayName : getDefaultWbeDisplayName(parsed.element_name, parsed.element_type));
}

function readWbeDisplayName(prefix, parsed) {
    var custom = ($('#' + prefix + '_element_display_name').val() || '').trim();
    if (custom) return custom;
    if (parsed) return getDefaultWbeDisplayName(parsed.element_name, parsed.element_type);
    return '';
}


function getAnnulusLetterFromTag(tagName) {
    var m = /_annulus_([a-z])(?:_|$)/i.exec(tagName || '');
    return m ? m[1].toUpperCase() : '';
}

function parseLimitNumber(v) {
    if (v == null) return null;
    var n = parseFloat(String(v).trim());
    return isNaN(n) ? null : n;
}

/** Find the dashboard operational-limit row matching an annulus letter (A/B/C). */
function findOpLimitForAnnulus(letter) {
    if (!letter) return null;
    var target = letter.toLowerCase();
    var found = null;
    (dashboardOpLimits || []).forEach(function(item) {
        if (found) return;
        var desc = (item && item.description ? String(item.description) : '').toLowerCase();
        if (desc.indexOf('annulus') === -1) return;
        var first = desc.replace(/^[^a-z0-9]+/, '').charAt(0);
        if (first === target) found = item;
    });
    return found;
}

var WIMS_LOOKBACK_OPTIONS = [
    { days: 7, label: '1 week' },
    { days: 30, label: '1 month' },
    { days: 183, label: '6 months' },
    { days: 365, label: '1 year' }
];

function getLookbackLabel(days) {
    var d = parseInt(days, 10) || 30;
    for (var i = 0; i < WIMS_LOOKBACK_OPTIONS.length; i++) {
        if (WIMS_LOOKBACK_OPTIONS[i].days === d) return WIMS_LOOKBACK_OPTIONS[i].label;
    }
    return d + ' days';
}

/** Resolve the operational limit to draw for a monitor (explicit, legacy auto-match, or none). */
function getOpLimitForMonitor(m) {
    if (m.opLimitDescription === null || m.opLimitDescription === '') return null;
    if (m.opLimitDescription === undefined) {
        return findOpLimitForAnnulus(m.annulusLetter || getAnnulusLetterFromTag(m.tagName));
    }
    return findOpLimitByStoredDescription(m.opLimitDescription);
}

function getAnnulusMonitorTagKey(m, index) {
    return m.tagName || ('idx_' + index);
}

/** Return limit breach for the latest reading, or null when within limits. */
function getLatestAnnulusLimitBreach(m) {
    var opLimit = getOpLimitForMonitor(m);
    if (!opLimit) return null;
    var series = m.series;
    if (!series || !series.values || series.values.length === 0) return null;

    var lastIdx = series.values.length - 1;
    var latestVal = parseFloat(series.values[lastIdx]);
    if (isNaN(latestVal)) return null;

    var latestTimestamp = (series.timestamps && series.timestamps[lastIdx]) ? series.timestamps[lastIdx] : null;
    var maxV = parseLimitNumber(opLimit.max);
    var minV = parseLimitNumber(opLimit.min);
    var unit = opLimit.unit || m.tagUnit || '';

    if (maxV != null && latestVal > maxV) {
        return { kind: 'above_max', limit: maxV, value: latestVal, unit: unit, timestamp: latestTimestamp, opLimit: opLimit };
    }
    if (minV != null && latestVal < minV) {
        return { kind: 'below_min', limit: minV, value: latestVal, unit: unit, timestamp: latestTimestamp, opLimit: opLimit };
    }
    return null;
}

function formatAnnulusReadingTimestamp(timestamp) {
    if (!timestamp) return 'unknown time';
    var d = new Date(timestamp);
    if (isNaN(d.getTime())) return String(timestamp);
    return d.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function resetAnnulusMonitorAlarms() {
    wimsAnnulusAlarmState = {};
    wimsAnnulusAlarmQueue = [];
    $('#annulus_alarm_modal').removeClass('show').removeData('tagKey');
}

/** Clear acknowledged/alarm state so limit breaches can raise popups again. */
function reArmAnnulusMonitorAlarms() {
    Object.keys(wimsAnnulusAlarmState).forEach(function(key) {
        if (wimsAnnulusAlarmState[key] === 'acknowledged' || wimsAnnulusAlarmState[key] === 'alarm') {
            wimsAnnulusAlarmState[key] = 'ok';
        }
    });
    wimsAnnulusAlarmQueue = [];
    $('#annulus_alarm_modal').removeClass('show').removeData('tagKey');
}

function enqueueAnnulusAlarm(alarm) {
    var exists = wimsAnnulusAlarmQueue.some(function(a) { return a.tagKey === alarm.tagKey; });
    if (!exists) wimsAnnulusAlarmQueue.push(alarm);
    showNextAnnulusAlarmIfNeeded();
}

function showNextAnnulusAlarmIfNeeded() {
    if ($('#annulus_alarm_modal').hasClass('show')) return;
    if (wimsAnnulusAlarmQueue.length === 0) return;
    presentAnnulusAlarmModal(wimsAnnulusAlarmQueue[0]);
}

function presentAnnulusAlarmModal(alarm) {
    var m = alarm.monitor;
    var b = alarm.breach;
    var letter = m.annulusLetter || getAnnulusLetterFromTag(m.tagName);
    var title = letter ? (letter + '-Annulus') : (m.tagText || m.tagName || 'Monitor');
    var limitLabel = b.kind === 'above_max' ? 'maximum' : 'minimum';
    var direction = b.kind === 'above_max' ? 'above' : 'below';
    var readingTime = formatAnnulusReadingTimestamp(b.timestamp);
    var msg = 'Latest reading at ' + readingTime + ' is ' + b.value.toFixed(2) + ' ' + b.unit +
        ', which is ' + direction + ' the operational ' + limitLabel +
        ' limit of ' + b.limit + ' ' + b.unit + '.';

    $('#annulus_alarm_modal_title').text('Annulus monitor alarm');
    $('#annulus_alarm_monitor_name').text(title);
    $('#annulus_alarm_tag_name').text(m.tagText || m.tagName || '');
    $('#annulus_alarm_message').text(msg);
    $('#annulus_alarm_modal').data('tagKey', alarm.tagKey).addClass('show');
}

function acknowledgeAnnulusMonitorAlarm() {
    var tagKey = $('#annulus_alarm_modal').data('tagKey');
    if (tagKey) wimsAnnulusAlarmState[tagKey] = 'acknowledged';
    $('#annulus_alarm_modal').removeClass('show').removeData('tagKey');
    wimsAnnulusAlarmQueue = wimsAnnulusAlarmQueue.filter(function(a) { return a.tagKey !== tagKey; });
    setTimeout(showNextAnnulusAlarmIfNeeded, 100);
}

/** Raise an acknowledge-required alarm when the latest reading breaches limits. */
function checkAnnulusMonitorAlarm(index) {
    var m = wimsAnnulusMonitors[index];
    if (!m) return;

    var tagKey = getAnnulusMonitorTagKey(m, index);
    var breach = getLatestAnnulusLimitBreach(m);
    var state = wimsAnnulusAlarmState[tagKey] || 'ok';

    if (!breach) {
        wimsAnnulusAlarmState[tagKey] = 'ok';
        return;
    }
    if (state === 'acknowledged' || state === 'alarm') return;

    wimsAnnulusAlarmState[tagKey] = 'alarm';
    enqueueAnnulusAlarm({ monitor: m, index: index, breach: breach, tagKey: tagKey });
}

/** Rebuild the operational-limit dropdown from dashboardOpLimits. */
function populateWimsMonitorOpLimitSelect(selectedDescription) {
    var $sel = $('#wims_add_monitor_op_limit').empty().append('<option value="">None</option>');
    (dashboardOpLimits || []).forEach(function(item, index) {
        if (isMinimumWallThicknessLimit(item)) return;
        var parts = [getOpLimitDisplayDescription(item)];
        if (item.min) parts.push('min ' + item.min);
        if (item.max) parts.push('max ' + item.max);
        if (item.unit) parts.push(item.unit);
        $sel.append($('<option></option>').attr('value', String(index)).text(parts.join(', ')));
    });
    if (selectedDescription) {
        var idx = (dashboardOpLimits || []).findIndex(function(x) {
            return getOpLimitDisplayDescription(x) === selectedDescription || x.description === selectedDescription;
        });
        $sel.val(idx >= 0 ? String(idx) : '');
    } else {
        $sel.val('');
    }
}


function displayWimsAnnulusMonitors() {
    var container = $('#wims_annulus_monitors_list');
    var esc = function(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; };
    if (wimsAnnulusMonitors.length === 0) {
        container.html('<p class="text-muted mb-0 small">No annulus monitors. Click Add monitor to plot an annulus pressure tag.</p>');
        return;
    }

    // -- build a card per monitor (chart filled in afterwards) ----
    var html = '';
    wimsAnnulusMonitors.forEach(function(m, index) {
        var letter = m.annulusLetter || getAnnulusLetterFromTag(m.tagName);
        var title = letter ? (letter + '-Annulus') : (m.tagText || m.tagName || 'Monitor');
        html += '<div class="wims-monitor-item" data-index="' + index + '">';
        html += '<div class="wims-monitor-head">';
        html += '<span class="wims-monitor-title">' + esc(title) + '</span>';
        html += '<button type="button" class="wims-monitor-remove" data-index="' + index + '" title="Remove">&times;</button>';
        html += '</div>';
        html += '<div class="wims-monitor-chart" id="wims_annulus_chart_' + index + '"></div>';
        html += '<div class="wims-monitor-tag">' + esc(m.tagText || m.tagName || '') + '</div>';
        html += '</div>';
    });
    container.html(html);

    // -- wire remove (x) and click-to-edit ----
    container.find('.wims-monitor-remove').on('click', function(e) {
        e.stopPropagation();
        removeWimsAnnulusMonitor(parseInt($(this).data('index'), 10));
    });
    container.find('.wims-monitor-item').on('click', function() {
        openWimsMonitorModal(parseInt($(this).data('index'), 10));
    });

    // -- draw each chart, fetching the series if not cached ----
    wimsAnnulusMonitors.forEach(function(m, index) {
        if (m.series && Array.isArray(m.series.values)) {
            renderWimsAnnulusChart(index);
        } else {
            renderWimsAnnulusChartMessage(index, 'Loading...');
            fetchWimsAnnulusSeries(index);
        }
    });

    // -- keep the charts fresh: refresh configured lookback window every 5 minutes ----
    startWimsAnnulusAutoRefresh();
}

function renderWimsAnnulusChartMessage(index, message) {
    var el = document.getElementById('wims_annulus_chart_' + index);
    if (el) el.innerHTML = '<div class="wims-monitor-msg">' + message + '</div>';
}

/** Render a compact line chart with operational-limit lines. */
function renderWimsAnnulusChart(index) {
    var el = document.getElementById('wims_annulus_chart_' + index);
    if (!el) return;
    if (typeof Plotly === 'undefined') {
        renderWimsAnnulusChartMessage(index, 'Charts unavailable.');
        return;
    }
    var m = wimsAnnulusMonitors[index];
    if (!m) return;
    var series = m.series || { timestamps: [], values: [] };
    if (!series.values || series.values.length === 0) {
        renderWimsAnnulusChartMessage(index, 'No data in last ' + getLookbackLabel(m.lookbackDays || 30) + '.');
        return;
    }
    var unit = m.tagUnit || '';

    // -- horizontal threshold lines from operational limits ----
    var shapes = [];
    var annotations = [];
    var opLimit = getOpLimitForMonitor(m);
    if (opLimit) {
        var maxV = parseLimitNumber(opLimit.max);
        var minV = parseLimitNumber(opLimit.min);
        if (maxV != null) {
            shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: maxV, y1: maxV,
                line: { color: '#dc3545', width: 1, dash: 'dash' } });
            annotations.push({ xref: 'paper', x: 0, y: maxV, xanchor: 'left', yanchor: 'bottom',
                text: 'max ' + maxV, showarrow: false, font: { size: 9, color: '#dc3545' } });
        }
        if (minV != null) {
            shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: minV, y1: minV,
                line: { color: '#28a745', width: 1, dash: 'dash' } });
            annotations.push({ xref: 'paper', x: 0, y: minV, xanchor: 'left', yanchor: 'top',
                text: 'min ' + minV, showarrow: false, font: { size: 9, color: '#28a745' } });
        }
    }

    // -- assemble trace + compact dark layout ----
    var trace = {
        x: series.timestamps,
        y: series.values,
        type: 'scatter',
        mode: 'lines',
        line: { color: '#4da3ff', width: 1.6 },
        hovertemplate: '%{x|%d %b}<br>%{y:.2f} ' + unit + '<extra></extra>'
    };
    var layout = {
        height: 150,
        margin: { l: 40, r: 8, t: 6, b: 22 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#bbb', size: 10 },
        xaxis: { type: 'date', showgrid: false, tickfont: { size: 9 } },
        yaxis: { title: { text: unit, font: { size: 9 } }, gridcolor: '#3a3c55', zeroline: false, tickfont: { size: 9 } },
        shapes: shapes,
        annotations: annotations,
        showlegend: false
    };
    // -- drop the "Loading..." placeholder so it doesn't linger under the plot
    if (el.querySelector('.wims-monitor-msg')) {
        el.innerHTML = '';
    }
    Plotly.react(el, [trace], layout, { displayModeBar: false, responsive: true });
    checkAnnulusMonitorAlarm(index);
}

function fetchWimsAnnulusSeries(index, options) {
    options = options || {};
    var silent = !!options.silentError;  // background refresh: keep chart on error
    var m = wimsAnnulusMonitors[index];

    // -- resolve required inputs (clear the spinner if missing) ----
    if (!m || !m.tagName) {
        if (!silent) renderWimsAnnulusChartMessage(index, 'No tag configured.');
        return;
    }
    var well_name = $('#select_well').val();
    if (!well_name) {
        if (!silent) renderWimsAnnulusChartMessage(index, 'Select a well to load data.');
        return;
    }

    // -- fetch configured lookback window; every outcome must clear "Loading..." ----
    var lookbackDays = m.lookbackDays || 30;
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_tag_series',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, tag_name: m.tagName, days: lookbackDays }),
        timeout: 30000,
        success: function(data) {
            m.series = { timestamps: data.timestamps || [], values: data.values || [] };
            if (data.unit && !m.tagUnit) m.tagUnit = data.unit;
            renderWimsAnnulusChart(index);
        },
        error: function(xhr, textStatus) {
            // background refresh: don't clobber a working chart on a transient error
            if (silent) return;
            var msg = (textStatus === 'timeout')
                ? 'Timed out loading data.'
                : 'Error loading data.';
            renderWimsAnnulusChartMessage(index, msg);
        }
    });
}

// Single page-lifetime timer that refreshes every annulus monitor's configured
// lookback window; null until started by displayWimsAnnulusMonitors().
var wimsAnnulusRefreshTimer = null;
var WIMS_ANNULUS_REFRESH_MS = 5 * 60 * 1000;  // 5 minutes

/** Re-fetch the configured lookback window for every monitor (silent on error). */
function refreshAllWimsAnnulusMonitors() {
    if (!Array.isArray(wimsAnnulusMonitors) || wimsAnnulusMonitors.length === 0) return;
    if (!$('#select_well').val()) return;
    wimsAnnulusMonitors.forEach(function(m, index) {
        if (m && m.tagName) fetchWimsAnnulusSeries(index, { silentError: true });
    });
}

/** Start the 5-minute auto-refresh once (idempotent). */
function startWimsAnnulusAutoRefresh() {
    if (wimsAnnulusRefreshTimer) return;
    wimsAnnulusRefreshTimer = setInterval(refreshAllWimsAnnulusMonitors, WIMS_ANNULUS_REFRESH_MS);
}

function removeWimsAnnulusMonitor(index) {
    var m = wimsAnnulusMonitors[index];
    if (m) {
        var tagKey = getAnnulusMonitorTagKey(m, index);
        delete wimsAnnulusAlarmState[tagKey];
        wimsAnnulusAlarmQueue = wimsAnnulusAlarmQueue.filter(function(a) { return a.tagKey !== tagKey; });
        if ($('#annulus_alarm_modal').data('tagKey') === tagKey) {
            $('#annulus_alarm_modal').removeClass('show').removeData('tagKey');
            setTimeout(showNextAnnulusAlarmIfNeeded, 100);
        }
    }
    wimsAnnulusMonitors.splice(index, 1);
    displayWimsAnnulusMonitors();
}

var wimsMonitorEditIndex = -1;

/** Open the add/edit modal; index = -1 to add, >=0 to edit. Tag list is annulus-only. */
function openWimsMonitorModal(index) {
    wimsMonitorEditIndex = index;
    var isEdit = typeof index === 'number' && index >= 0 && index < wimsAnnulusMonitors.length;
    var m = isEdit ? wimsAnnulusMonitors[index] : {};
    $('#wims_add_monitor_modal_title').text(isEdit ? 'Edit annulus monitor' : 'Add annulus monitor');
    $('#wims_add_monitor_submit_btn').text(isEdit ? 'Save' : 'Add');
    $('#wims_add_monitor_delete_btn').toggle(isEdit);
    $('#wims_add_monitor_error').hide();
    $('#wims_add_monitor_annulus').val(isEdit && m.annulusLetter ? m.annulusLetter : '');

    // -- operational limit and lookback defaults ----
    var opLimitDesc = null;
    if (isEdit) {
        if (Object.prototype.hasOwnProperty.call(m, 'opLimitDescription')) {
            opLimitDesc = m.opLimitDescription;
        } else {
            var autoLimit = findOpLimitForAnnulus(m.annulusLetter || getAnnulusLetterFromTag(m.tagName));
            opLimitDesc = autoLimit ? getOpLimitDisplayDescription(autoLimit) : null;
        }
    }
    populateWimsMonitorOpLimitSelect(opLimitDesc);
    $('#wims_add_monitor_lookback').val(String(m.lookbackDays || 30));

    var well_name = $('#select_well').val();
    var $sel = $('#wims_add_monitor_tag').empty().append('<option value="">Select tag...</option>');
    if (!well_name) {
        $sel.append('<option value="">Select a well first</option>');
        $('#wims_add_monitor_modal').addClass('show');
        return;
    }

    // -- load all measured tags for this well ----
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_measured_tags',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(data) {
            $sel.empty().append('<option value="">Select tag...</option>');
            if (data.measured_tags && data.measured_tags.length > 0) {
                data.measured_tags.forEach(function(tag) {
                    var label = tag.description || tag.tag_name;
                    var unitText = tag.unit ? ' (' + tag.unit + ')' : '';
                    $sel.append($('<option></option>').attr('value', tag.tag_name).attr('data-unit', tag.unit || '').text(label + unitText));
                });
            } else {
                $sel.append('<option value="">No tags found</option>');
            }
            if (isEdit && m.tagName) $sel.val(m.tagName);
        },
        error: function() {
            $sel.append('<option value="">Error loading tags</option>');
        }
    });
    $('#wims_add_monitor_modal').addClass('show');
}

function saveWimsMonitor() {
    var annulusLetter = $('#wims_add_monitor_annulus').val();
    var tagVal = $('#wims_add_monitor_tag').val();
    var tagOpt = $('#wims_add_monitor_tag option:selected');
    if (!annulusLetter) {
        $('#wims_add_monitor_error').text('Select an annulus.').show();
        return;
    }
    if (!tagVal) {
        $('#wims_add_monitor_error').text('Select a tag.').show();
        return;
    }

    // -- read operational limit and lookback ----
    var opIdx = $('#wims_add_monitor_op_limit').val();
    var opLimitDescription = null;
    if (opIdx !== '') {
        var opItem = dashboardOpLimits[parseInt(opIdx, 10)];
        opLimitDescription = opItem ? getOpLimitDisplayDescription(opItem) : null;
    }
    var lookbackDays = parseInt($('#wims_add_monitor_lookback').val(), 10) || 30;

    var monitor = {
        tagName: tagVal,
        tagText: tagOpt.text(),
        tagUnit: tagOpt.data('unit') || '',
        annulusLetter: annulusLetter,
        opLimitDescription: opLimitDescription,
        lookbackDays: lookbackDays,
        series: null
    };
    if (wimsMonitorEditIndex >= 0 && wimsMonitorEditIndex < wimsAnnulusMonitors.length) {
        wimsAnnulusMonitors[wimsMonitorEditIndex] = monitor;
    } else {
        wimsAnnulusMonitors.push(monitor);
        reArmAnnulusMonitorAlarms();
        delete wimsAnnulusAlarmState[tagVal];
    }
    $('#wims_add_monitor_modal').removeClass('show');
    displayWimsAnnulusMonitors();
}


function showToast(message, type = 'success', duration = 4000) {
    const icons = {
        success: '✓',
        error: '✗',
        info: 'ℹ'
    };
    
    const toastDiv = $(`
        <div class="toast-notification ${type}">
            <span class="toast-icon">${icons[type] || icons.success}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="closeToast(this)">×</button>
        </div>
    `);
    
    $('#toast-container').append(toastDiv);
    
    // Trigger animation
    setTimeout(() => {
        toastDiv.addClass('show');
    }, 100);
    
    // Auto-remove after duration
    setTimeout(() => {
        removeToast(toastDiv);
    }, duration);
}

// Global function for closing toasts
window.closeToast = function(button) {
    const toast = $(button).closest('.toast-notification');
    removeToast(toast);
};

function removeToast(toast) {
    toast.addClass('fade-out');
    setTimeout(() => {
        toast.remove();
    }, 300);
}

function showSuccessMessage(message) {
    showToast(message, 'success');
}

function showErrorMessage(message) {
    showToast(message, 'error');
}

function showInfoMessage(message) {
    showToast(message, 'info');
}


// --- Log Information modal ---

function applyBaselineDepthCorrectionRule() {
    var $depth = $('#log_info_depth_correction');
    $depth.prop('disabled', false);
}

function updateLogInfoRedetectOption(logName) {
    var detected = (window.detectedLogsList || []).indexOf(logName) >= 0;
    var processed = (window.processedLogsAvailable || []).indexOf(logName) >= 0;
    var show = detected || processed;
    $('#log_info_redetect_wrap').toggle(show);
    $('#log_info_redetect_joints').prop('checked', false);
}

function setSelectOrCustom(selectId, customInputId, value, presets) {
    var select = $(selectId);
    var custom = $(customInputId);
    var normalized = (value || '').trim();
    var isPreset = normalized && presets.indexOf(normalized) !== -1;
    var hasOption = normalized && select.find('option').filter(function() {
        return $(this).val() === normalized;
    }).length > 0;

    if (normalized && isPreset && hasOption) {
        select.val(normalized);
        custom.val('').hide();
    } else if (normalized) {
        select.val('__custom__');
        custom.val(normalized).show();
    } else {
        select.val('');
        custom.val('').hide();
    }
}

function getSelectOrCustom(selectId, customInputId) {
    if ($(selectId).val() === '__custom__') {
        return ($(customInputId).val() || '').trim();
    }
    return ($(selectId).val() || '').trim();
}

function openLogInfoModal(logName) {
    var well_name = $('#select_well').val();
    if (!well_name || !logName) return;
    $('#log_info_log_name').val(logName);
    $('#log_info_date').val('');
    $('#log_info_baseline').prop('checked', false);
    $('#log_info_finger_units').val('');
    $('#log_info_depth_correction').val('');
    $('#log_info_min_marker_score').val(100);
    $('#log_info_min_gradient_score').val(10);
    $('#log_info_score_params').hide();
    $('#log_info_finger_name_select').val('');
    $('#log_info_finger_name_custom').val('').hide();
    $('#log_info_max_column_name_select').val('');
    $('#log_info_max_column_name_custom').val('').hide();
    $('#log_info_min_column_name_select').val('');
    $('#log_info_min_column_name_custom').val('').hide();
    $('#log_info_average_column_name_select').val('');
    $('#log_info_average_column_name_custom').val('').hide();
    $('#log_info_error').hide();
    applyBaselineDepthCorrectionRule();
    updateLogInfoRedetectOption(logName);
    $('#log_info_modal').addClass('show');

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_log_info',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, log_name: logName }),
        success: function(data) {
            var info = (data && data.info) || {};
            $('#log_info_date').val(info.date || '');
            $('#log_info_baseline').prop('checked', !!info.is_baseline);
            $('#log_info_finger_units').val(info.finger_units || '');
            $('#log_info_depth_correction').val(info.joint_identification_marker || '');
            var markerVal = (info.joint_identification_marker || '').toLowerCase();
            if (markerVal === 'log_markers') {
                $('#log_info_score_params').show();
            }
            if (info.min_marker_score != null) {
                $('#log_info_min_marker_score').val(info.min_marker_score);
            }
            if (info.min_gradient_score != null) {
                $('#log_info_min_gradient_score').val(info.min_gradient_score);
            }
            setSelectOrCustom(
                '#log_info_finger_name_select',
                '#log_info_finger_name_custom',
                info.finger_name || '',
                ['R', 'RAD', 'RADI', 'D', 'DIAM', 'FING', 'F']
            );
            setSelectOrCustom(
                '#log_info_max_column_name_select',
                '#log_info_max_column_name_custom',
                info.max_column_name || '',
                ['MAX', 'MAXI', 'MXRD']
            );
            setSelectOrCustom(
                '#log_info_min_column_name_select',
                '#log_info_min_column_name_custom',
                info.min_column_name || '',
                ['MIN', 'MINI','MNRD']
            );
            var averageColumnName = info.average_column_name || '';
            if (averageColumnName === 'MENA') {
                averageColumnName = 'MEAN';
            }
            setSelectOrCustom(
                '#log_info_average_column_name_select',
                '#log_info_average_column_name_custom',
                averageColumnName,
                ['MEAN', 'AVGMNRD', 'AVRD']
            );
            applyBaselineDepthCorrectionRule();
        }
    });
}

function saveLogInfo() {
    var well_name = $('#select_well').val();
    var logName = $('#log_info_log_name').val();
    if (!well_name || !logName) return;

    var fingerName = getSelectOrCustom('#log_info_finger_name_select', '#log_info_finger_name_custom');
    var maxColumnName = getSelectOrCustom('#log_info_max_column_name_select', '#log_info_max_column_name_custom');
    var minColumnName = getSelectOrCustom('#log_info_min_column_name_select', '#log_info_min_column_name_custom');
    var averageColumnName = getSelectOrCustom(
        '#log_info_average_column_name_select',
        '#log_info_average_column_name_custom'
    );

    var jidMarker = $('#log_info_depth_correction').val();
    var info = {
        date: $('#log_info_date').val(),
        is_baseline: $('#log_info_baseline').is(':checked'),
        finger_units: $('#log_info_finger_units').val(),
        joint_identification_marker: jidMarker,
        finger_name: fingerName,
        max_column_name: maxColumnName,
        min_column_name: minColumnName,
        average_column_name: averageColumnName
    };
    if (jidMarker === 'log_markers') {
        var ms = parseFloat($('#log_info_min_marker_score').val());
        var gs = parseFloat($('#log_info_min_gradient_score').val());
        info.min_marker_score = isNaN(ms) ? 100.0 : ms;
        info.min_gradient_score = isNaN(gs) ? 10.0 : gs;
    }

    var redetectJoints = $('#log_info_redetect_joints').is(':checked');

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_log_info',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, log_name: logName, info: info }),
        success: function() {
            $('#log_info_modal').removeClass('show');
            if (redetectJoints) {
                delete window.detectedJointsData[logName];
                if (typeof showSuccessMessage === 'function') {
                    showSuccessMessage('Log information saved. Re-detecting joints...');
                }
                loadWellLogs();
                detectJointsForLogs([logName]);
            } else {
                if (typeof showSuccessMessage === 'function') showSuccessMessage('Log information saved.');
                loadWellLogs();
            }
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) || 'Error saving log info';
            $('#log_info_error').text(msg).show();
        }
    });
}

function removeLog() {
    var well_name = $('#select_well').val();
    var logName = $('#log_info_log_name').val();
    if (!well_name || !logName) return;

    var ok = window.confirm('Remove log "' + logName + '"? This will delete uploaded and processed files for this log.');
    if (!ok) return;

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/delete_log',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, log_name: logName }),
        success: function() {
            $('#log_info_modal').removeClass('show');
            if (window.lastProcessedLogsData && window.lastProcessedLogsData[logName]) {
                delete window.lastProcessedLogsData[logName];
            }
            if (typeof showSuccessMessage === 'function') showSuccessMessage('Log removed.');
            loadWellLogs();
            renderProcessedLogChart();
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) || 'Error removing log';
            $('#log_info_error').text(msg).show();
        }
    });
}

// Event handlers
$(document).ready(function() {
    $('#upload_log_btn').on('click', function() {
        $('#log_upload').trigger('click');
    });
    $('#log_upload').on('change', function() {
        if (this.files && this.files.length > 0) {
            uploadLog();
        }
    });
    $('#process_logs_btn').on('click', function () {
        processCaliperLogs();
    });
    $('#detect_joints_btn').on('click', detectJoints);
    $('#approve_joints_btn').on('click', approveJoints);
    $('#joint_qaqc_close_btn').on('click', function () {
        destroyUplot();
        $('#joint_qaqc_modal').removeClass('show');
    });
    $('#open_qaqc_modal_btn').on('click', function () {
        var logNames = window._qaqcLogNames || [];
        if (logNames.length === 0) {
            logNames = (window.detectedLogsList || []).concat(window.processedLogsAvailable || []);
        }
        if (logNames.length === 0 && Object.keys(window.detectedJointsData).length > 0) {
            logNames = Object.keys(window.detectedJointsData);
        }
        if (logNames.length > 0) {
            showJointQaqcPanel(logNames);
        } else {
            showInfoMessage('No detected joints available. Run "Detect Joints" first.');
        }
    });

    $('#joint_qaqc_log_select').on('change', function () {
        var logName = $(this).val();
        if (logName) {
            destroyUplot();
            renderJointCandidatesTable(logName);
            renderJointQaqcChartSmart(logName);
        }
    });

    $('#joint_qaqc_select_all').on('change', function () {
        var checked = $(this).is(':checked');
        $('#joint_qaqc_table_body .joint-checkbox').prop('checked', checked);
        $('#joint_qaqc_table_body tr').toggleClass('joint-excluded', !checked);
        updateJointQaqcChart();
    });

    $(document).on('change', '#joint_qaqc_table_body .joint-checkbox', function () {
        $(this).closest('tr').toggleClass('joint-excluded', !$(this).is(':checked'));
        updateJointQaqcChart();
    });

    $(document).on('change', '#joint_qaqc_table_body .joint-depth-input', function () {
        var candIdx = parseInt($(this).attr('data-cand-idx'), 10);
        var newDepth = parseFloat($(this).val());
        if (isNaN(newDepth)) return;
        var logName = $('#joint_qaqc_log_select').val();
        if (!logName) return;
        var logData = window.detectedJointsData[logName];
        if (!logData) return;
        var allCands = logData._allCandidates || logData.candidates || [];
        if (allCands[candIdx]) {
            allCands[candIdx].depth = newDepth;
            updateJointQaqcChart();
        }
    });

    // Finger Detail modal handlers
    $('#open_finger_detail_btn').on('click', function () {
        openFingerDetailModal();
    });
    $('#finger_detail_close_btn').on('click', function () {
        destroyFingerDetailUplot();
        $('#finger_detail_modal').removeClass('show');
    });
    $('#finger_detail_log_select').on('change', function () {
        var logName = $(this).val();
        if (logName) {
            populateFingerDetailJoints(logName);
            destroyFingerDetailUplot();
            $('#finger_detail_placeholder').text('Select a joint to view finger measurements').show();
        }
    });
    $('#finger_detail_joint_select').on('change', function () {
        var val = $(this).val();
        if (!val) return;
        var logName = $('#finger_detail_log_select').val();
        if (!logName) return;
        try {
            var joint = JSON.parse(val);
            loadFingerDetailData(logName, joint.top, joint.bottom, joint.idx);
        } catch (e) { /* ignore parse errors */ }
    });

    // Log info modal handlers
    $(document).on('click', '#logs_table_body tr.log-row-clickable', function() {
        var logName = $(this).attr('data-log-name');
        if (logName) openLogInfoModal(logName);
    });
    $('#log_info_cancel_btn').on('click', function() {
        $('#log_info_modal').removeClass('show');
    });
    $('#log_info_save_btn').on('click', saveLogInfo);
    $('#log_info_remove_btn').on('click', removeLog);
    $('#log_info_baseline').on('change', function() {
        applyBaselineDepthCorrectionRule();
    });
    $('#log_info_depth_correction').on('change', function() {
        if ($(this).val() === 'log_markers') {
            $('#log_info_score_params').show();
        } else {
            $('#log_info_score_params').hide();
        }
    });
    $('#log_info_finger_name_select').on('change', function() {
        if ($(this).val() === '__custom__') {
            $('#log_info_finger_name_custom').show().focus();
        } else {
            $('#log_info_finger_name_custom').val('').hide();
        }
    });
    $('#log_info_max_column_name_select').on('change', function() {
        if ($(this).val() === '__custom__') {
            $('#log_info_max_column_name_custom').show().focus();
        } else {
            $('#log_info_max_column_name_custom').val('').hide();
        }
    });
    $('#log_info_min_column_name_select').on('change', function() {
        if ($(this).val() === '__custom__') {
            $('#log_info_min_column_name_custom').show().focus();
        } else {
            $('#log_info_min_column_name_custom').val('').hide();
        }
    });
    $('#log_info_average_column_name_select').on('change', function() {
        if ($(this).val() === '__custom__') {
            $('#log_info_average_column_name_custom').show().focus();
        } else {
            $('#log_info_average_column_name_custom').val('').hide();
        }
    });

    // When Well Logs card grows (e.g. more logs), match Processed Logs panel height
    $(window).on('resize', function() {
        syncProcessedLogPanelHeight();
        if (window.lastProcessedLogsData) {
            renderProcessedLogChart();
        }
    });

    // Add barrier element: open modal – populate drawn items only (no redraw here)
    $('#wims_add_element_btn').off('click').on('click', function() {
        openWbeAddElementModal();
    });

    $('#wims_add_element_from_schematic').off('change').on('change', function() {
        var parsed = readWbeElementFromSelect('wims_add');
        if (!parsed) {
            $('#wims_add_element_patches_wrap').hide();
            $('#wims_add_element_patches_list').empty();
            updateWbeDisplayNameField('wims_add', null);
            return;
        }
        renderWbePatchChecklist('wims_add', parsed.element_name, parsed.element_type, null);
        updateWbeDisplayNameField('wims_add', parsed);
    });

    $('#wims_edit_element_from_schematic').off('change').on('change', function() {
        var parsed = readWbeElementFromSelect('wims_edit');
        if (!parsed) {
            $('#wims_edit_element_patches_wrap').hide();
            $('#wims_edit_element_patches_list').empty();
            updateWbeDisplayNameField('wims_edit', null);
            return;
        }
        renderWbePatchChecklist('wims_edit', parsed.element_name, parsed.element_type, null);
        updateWbeDisplayNameField('wims_edit', parsed);
    });

    // Partial recoloring: toggle depth band fields ----
    $('#wims_add_partial_recolor').off('change').on('change', function() {
        $('#wims_add_partial_recolor_wrap').toggle($(this).is(':checked'));
        if (!$(this).is(':checked')) {
            $('#wims_add_top_depth_m, #wims_add_bottom_depth_m').val('');
        }
    });
    $('#wims_edit_partial_recolor').off('change').on('change', function() {
        $('#wims_edit_partial_recolor_wrap').toggle($(this).is(':checked'));
        if (!$(this).is(':checked')) {
            $('#wims_edit_top_depth_m, #wims_edit_bottom_depth_m').val('');
        }
    });

    // Partial recoloring: toggle depth band fields ----
    $('#wims_add_element_cancel_btn').off('click').on('click', function() {
        $('#wims_add_element_modal').removeClass('show');
    });
    $('#wims_add_element_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
    });

    // -- WBE Risk: L × E -> risk factor ---------------------------------
    function computeWbeRiskFactor(lStr, eStr) {
        var l = parseFloat(lStr);
        var e = parseFloat(eStr);
        if (!isFinite(l) || !isFinite(e)) return '';
        var product = l * e;
        return Number.isInteger(product) ? String(product) : String(Math.round(product * 1000) / 1000);
    }

    function updateWbeRiskFactorField(prefix) {
        var l = $('#' + prefix + '_risk_l').val().trim();
        var e = $('#' + prefix + '_risk_e').val().trim();
        $('#' + prefix + '_risk_rf').val(computeWbeRiskFactor(l, e));
    }

    $('#wims_risk_l, #wims_risk_e').off('input.wbeRisk').on('input.wbeRisk', function() {
        updateWbeRiskFactorField('wims');
    });
    $('#wims_edit_risk_l, #wims_edit_risk_e').off('input.wbeRisk').on('input.wbeRisk', function() {
        updateWbeRiskFactorField('wims_edit');
    });

    // Add WBE Risk: open modal
    $('#wims_add_risk_btn').off('click').on('click', function() {
        $('#wims_risk_failure_mode').val('');
        $('#wims_risk_effect').val('');
        $('#wims_risk_l').val('');
        $('#wims_risk_e').val('');
        $('#wims_risk_rf').val('');
        $('#wims_risk_action_plan').val('');
        $('#wims_risk_months').val('');
        $('#wims_risk_operate_during_failure').val('');
        $('#wims_add_risk_modal').addClass('show');
    });
    $('#wims_add_risk_cancel_btn').off('click').on('click', function() {
        $('#wims_add_risk_modal').removeClass('show');
    });
    $('#wims_add_risk_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
    });
    // Add WBE Risk: submit – add row to #wims_wbe_risk_tbody
    $('#wims_add_risk_submit_btn').off('click').on('click', function() {
        var failureMode = $('#wims_risk_failure_mode').val().trim();
        var effect = $('#wims_risk_effect').val().trim();
        var l = $('#wims_risk_l').val().trim();
        var e = $('#wims_risk_e').val().trim();
        updateWbeRiskFactorField('wims');
        var rf = $('#wims_risk_rf').val().trim();
        var actionPlan = $('#wims_risk_action_plan').val().trim();
        var months = $('#wims_risk_months').val().trim();
        var operateDuringFailure = $('#wims_risk_operate_during_failure').val().trim();

        var $tbody = $('#wims_wbe_risk_tbody');
        var $placeholder = $tbody.find('tr.wims-wbe-risk-placeholder');
        if ($placeholder.length) {
            $placeholder.remove();
        }

        var row = '<tr class="wims-wbe-risk-data-row">' +
            '<td>' + escapeHtml(failureMode) + '</td>' +
            '<td>' + escapeHtml(effect) + '</td>' +
            '<td>' + escapeHtml(l) + '</td>' +
            '<td>' + escapeHtml(e) + '</td>' +
            '<td>' + escapeHtml(rf) + '</td>' +
            '<td>' + escapeHtml(actionPlan) + '</td>' +
            '<td>' + escapeHtml(months) + '</td>' +
            '<td>' + escapeHtml(operateDuringFailure) + '</td>' +
            '</tr>';
        $tbody.append(row);

        $('#wims_risk_failure_mode').val('');
        $('#wims_risk_effect').val('');
        $('#wims_risk_l').val('');
        $('#wims_risk_e').val('');
        $('#wims_risk_rf').val('');
        $('#wims_risk_action_plan').val('');
        $('#wims_risk_months').val('');
        $('#wims_risk_operate_during_failure').val('');
        $('#wims_add_risk_modal').removeClass('show');
    });

    // Edit WBE Risk: open on row click
    $(document).off('click', '#wims_wbe_risk_tbody tr.wims-wbe-risk-data-row').on('click', '#wims_wbe_risk_tbody tr.wims-wbe-risk-data-row', function() {
        var $tr = $(this);
        var $tds = $tr.find('td');
        if ($tds.length < 8) return;
        window.wimsEditRisk$tr = $tr;
        $('#wims_edit_risk_failure_mode').val($tds.eq(0).text().trim());
        $('#wims_edit_risk_effect').val($tds.eq(1).text().trim());
        $('#wims_edit_risk_l').val($tds.eq(2).text().trim());
        $('#wims_edit_risk_e').val($tds.eq(3).text().trim());
        updateWbeRiskFactorField('wims_edit');
        $('#wims_edit_risk_action_plan').val($tds.eq(5).text().trim());
        $('#wims_edit_risk_months').val($tds.eq(6).text().trim());
        $('#wims_edit_risk_operate_during_failure').val($tds.eq(7).text().trim());
        $('#wims_edit_risk_modal').addClass('show');
    });
    $('#wims_edit_risk_cancel_btn').off('click').on('click', function() {
        $('#wims_edit_risk_modal').removeClass('show');
    });
    $('#wims_edit_risk_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
    });
    $('#wims_edit_risk_save_btn').off('click').on('click', function() {
        var $tr = window.wimsEditRisk$tr;
        if (!$tr || !$tr.length) {
            $('#wims_edit_risk_modal').removeClass('show');
            return;
        }
        var failureMode = $('#wims_edit_risk_failure_mode').val().trim();
        var effect = $('#wims_edit_risk_effect').val().trim();
        var l = $('#wims_edit_risk_l').val().trim();
        var e = $('#wims_edit_risk_e').val().trim();
        updateWbeRiskFactorField('wims_edit');
        var rf = $('#wims_edit_risk_rf').val().trim();
        var actionPlan = $('#wims_edit_risk_action_plan').val().trim();
        var months = $('#wims_edit_risk_months').val().trim();
        var operateDuringFailure = $('#wims_edit_risk_operate_during_failure').val().trim();
        $tr.find('td').eq(0).text(failureMode);
        $tr.find('td').eq(1).text(effect);
        $tr.find('td').eq(2).text(l);
        $tr.find('td').eq(3).text(e);
        $tr.find('td').eq(4).text(rf);
        $tr.find('td').eq(5).text(actionPlan);
        $tr.find('td').eq(6).text(months);
        $tr.find('td').eq(7).text(operateDuringFailure);
        $('#wims_edit_risk_modal').removeClass('show');
    });
    $('#wims_edit_risk_delete_btn').off('click').on('click', function() {
        var $tr = window.wimsEditRisk$tr;
        if (!$tr || !$tr.length) {
            $('#wims_edit_risk_modal').removeClass('show');
            return;
        }
        var $tbody = $('#wims_wbe_risk_tbody');
        $tr.remove();
        if ($tbody.find('tr.wims-wbe-risk-data-row').length === 0) {
            $tbody.append('<tr class="wims-wbe-risk-placeholder"><td colspan="8" class="text-muted text-center py-3">No WBE risk rows loaded.</td></tr>');
        }
        $('#wims_edit_risk_modal').removeClass('show');
    });

    // Edit barrier element: open on row click
    $(document).off('click', '#wims_primary_barrier_tbody tr.wims-barrier-data-row, #wims_secondary_barrier_tbody tr.wims-barrier-data-row').on('click', '#wims_primary_barrier_tbody tr.wims-barrier-data-row, #wims_secondary_barrier_tbody tr.wims-barrier-data-row', function() {
        var $tr = $(this);
        var tbodyId = $tr.closest('tbody').attr('id');
        var tableType = tbodyId === 'wims_primary_barrier_tbody' ? 'primary' : 'secondary';
        var $tds = $tr.find('td');
        if ($tds.length < 5) return;
        var element = $tds.eq(0).text().trim();
        var qualification = $tds.eq(1).text().trim();
        var monitoring = $tds.eq(2).text().trim();
        var $statusSpan = $tds.eq(3).find('.wims-integrity-dot');
        var status = 'verified';
        if ($statusSpan.hasClass('failed')) status = 'failed';
        else if ($statusSpan.hasClass('not-verified')) status = 'not-verified';
        var remarksCell = $tds.eq(4)[0];
        var hasRemarkDot = $(remarksCell).find('.wims-barrier-remark-dot').length > 0;
        var remarks = hasRemarkDot ? '' : $(remarksCell).text().trim();

        window.wimsEditBarrierTableType = tableType;
        window.wimsEditBarrier$tr = $tr;

        $('#wims_edit_qualification').val(qualification);
        $('#wims_edit_monitoring').val(monitoring);
        $('#wims_edit_status').val(status);
        $('#wims_edit_remarks').val(remarks);
        setWimsEditPartialRecolorFields($tr);
        openWbeEditElementModal($tr);
        $('#wims_edit_element_modal').addClass('show');
    });

    // Edit barrier element: cancel and overlay close
    $('#wims_edit_element_cancel_btn').off('click').on('click', function() {
        $('#wims_edit_element_modal').removeClass('show');
    });
    $('#wims_edit_element_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
    });

    // Edit barrier element: save
    $('#wims_edit_element_save_btn').off('click').on('click', function() {
        var $tr = window.wimsEditBarrier$tr;
        if (!$tr || !$tr.length) {
            $('#wims_edit_element_modal').removeClass('show');
            return;
        }
        var parsed = readWbeElementFromSelect('wims_edit');
        if (!parsed) {
            showErrorMessage('Select an element from the schematic.');
            return;
        }
        var patchTypes = readWbePatchSelection('wims_edit');
        if (patchTypes.length === 0) {
            showErrorMessage('Select at least one patch for this barrier element.');
            return;
        }
        var element = readWbeDisplayName('wims_edit', parsed);
        if (!element) {
            showErrorMessage('Enter a name for the barrier table.');
            return;
        }
        var qualification = $('#wims_edit_qualification').val().trim();
        var monitoring = $('#wims_edit_monitoring').val().trim();
        var status = $('#wims_edit_status').val();
        var remarks = $('#wims_edit_remarks').val().trim();
        if (!element) {
            $('#wims_edit_element_modal').removeClass('show');
            return;
        }
        var editDepths = readWimsPartialRecolorDepths('wims_edit');
        if (editDepths && editDepths.error) {
            showErrorMessage(editDepths.error);
            return;
        }
        var statusDotClass = (status === 'failed' || status === 'not-verified' || status === 'verified') ? status : 'verified';
        var statusDot = '<span class="wims-integrity-dot ' + statusDotClass + '" title="' + escapeHtml($('#wims_edit_status option:selected').text()) + '"></span>';
        var remarkCell = remarks ? escapeHtml(remarks) : '';
        $tr.find('td').eq(0).text(element);
        $tr.find('td').eq(1).text(qualification);
        $tr.find('td').eq(2).text(monitoring);
        $tr.find('td').eq(3).html(statusDot);
        $tr.find('td').eq(4).html(remarkCell);
        applyBarrierRowDataAttrs($tr, parsed.element_name, parsed.element_type, patchTypes);
        $tr.removeAttr('data-top-depth-m').removeAttr('data-bottom-depth-m');
        if (editDepths && editDepths.top_depth_m != null) {
            $tr.attr('data-top-depth-m', editDepths.top_depth_m);
            $tr.attr('data-bottom-depth-m', editDepths.bottom_depth_m);
        }
        updateWimsOverallStatusFromBarriers();
        refreshWimsSchematicFromBarriers();
        $('#wims_edit_element_modal').removeClass('show');
    });

    // Edit barrier element: delete
    $('#wims_edit_element_delete_btn').off('click').on('click', function() {
        var $tr = window.wimsEditBarrier$tr;
        if (!$tr || !$tr.length) {
            $('#wims_edit_element_modal').removeClass('show');
            return;
        }
        var $tbody = $tr.closest('tbody');
        $tr.remove();
        if ($tbody.find('tr.wims-barrier-data-row').length === 0) {
            var placeholder = $tbody.attr('id') === 'wims_primary_barrier_tbody'
                ? '<tr><td colspan="5" class="text-muted text-center py-3">No primary Well Barrier Envelope (WBE) loaded.</td></tr>'
                : '<tr><td colspan="5" class="text-muted text-center py-3">No secondary Well Barrier Envelope (WBE) loaded.</td></tr>';
            $tbody.append(placeholder);
        }
        updateWimsOverallStatusFromBarriers();
        refreshWimsSchematicFromBarriers();
        $('#wims_edit_element_modal').removeClass('show');
    });

    // Add barrier element: submit – schematic element + selected patches
    $('#wims_add_element_submit_btn').off('click').on('click', function() {
        const tableType = $('#wims_add_table_type').val();
        var parsed = readWbeElementFromSelect('wims_add');
        if (!parsed) {
            showErrorMessage('Select an element from the schematic.');
            return;
        }
        var patchTypes = readWbePatchSelection('wims_add');
        if (patchTypes.length === 0) {
            showErrorMessage('Select at least one patch for this barrier element.');
            return;
        }
        const element = readWbeDisplayName('wims_add', parsed);
        if (!element) {
            showErrorMessage('Enter a name for the barrier table.');
            return;
        }
        const qualification = $('#wims_add_qualification').val().trim();
        const monitoring = $('#wims_add_monitoring').val().trim();
        const status = $('#wims_add_status').val();
        const remarks = $('#wims_add_remarks').val().trim();

        var addDepths = readWimsPartialRecolorDepths('wims_add');
        if (addDepths && addDepths.error) {
            showErrorMessage(addDepths.error);
            return;
        }

        const tbodyId = tableType === 'primary' ? 'wims_primary_barrier_tbody' : 'wims_secondary_barrier_tbody';
        const $tbody = $('#' + tbodyId);

        const $placeholder = $tbody.find('tr td[colspan="5"]');
        if ($placeholder.length) {
            $placeholder.closest('tr').remove();
        }

        const statusDotClass = (status === 'failed' || status === 'not-verified' || status === 'verified') ? status : 'verified';
        const statusDot = '<span class="wims-integrity-dot ' + statusDotClass + '" title="' + escapeHtml($('#wims_add_status option:selected').text()) + '"></span>';
        const remarkCell = remarks ? escapeHtml(remarks) : '';
        const depthAttrs = buildBarrierRowDepthAttrs(addDepths);
        const row = '<tr class="wims-barrier-data-row"' + depthAttrs + '><td>' + escapeHtml(element) + '</td><td>' + escapeHtml(qualification) + '</td><td>' + escapeHtml(monitoring) + '</td><td>' + statusDot + '</td><td>' + remarkCell + '</td></tr>';
        $tbody.append(row);
        var $newRow = $tbody.find('tr.wims-barrier-data-row').last();
        applyBarrierRowDataAttrs($newRow, parsed.element_name, parsed.element_type, patchTypes);

        $('#wims_add_element_from_schematic').val('');
        $('#wims_add_element_patches_wrap').hide();
        $('#wims_add_element_patches_list').empty();
        updateWbeDisplayNameField('wims_add', null);
        $('#wims_add_qualification').val('');
        $('#wims_add_monitoring').val('');
        $('#wims_add_status').val('verified');
        $('#wims_add_remarks').val('');
        resetWimsAddPartialRecolorFields();
        $('#wims_add_element_modal').removeClass('show');

        refreshWimsSchematicFromBarriers();
        updateWimsOverallStatusFromBarriers();
    });

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Forecasting panel: optimize (calibrate) corrosion model against logs
    $('#forecasting_optimize_btn').off('click').on('click', function() {
        optimizeCorrosionModel();
    });

    // Forecasting panel: run the selected prediction method (current wall thickness, years to min, ...)
    $('#forecasting_run_method_btn').off('click').on('click', function() {
        runForecastMethod();
    });

    // -- annulus monitors: add / edit / delete ----
    $('#wims_add_monitor_btn').off('click').on('click', function() {
        var well_name = $('#select_well').val();
        if (!well_name) {
            showErrorMessage('Please select a well first.');
            return;
        }
        openWimsMonitorModal(-1);
    });
    $('#wims_add_monitor_cancel_btn').off('click').on('click', function() {
        $('#wims_add_monitor_modal').removeClass('show');
    });
    $('#wims_add_monitor_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
    });
    $('#wims_add_monitor_submit_btn').off('click').on('click', function() {
        saveWimsMonitor();
    });
    $('#wims_add_monitor_delete_btn').off('click').on('click', function() {
        if (wimsMonitorEditIndex >= 0 && wimsMonitorEditIndex < wimsAnnulusMonitors.length) {
            removeWimsAnnulusMonitor(wimsMonitorEditIndex);
        }
        $('#wims_add_monitor_modal').removeClass('show');
    });
    $('#annulus_alarm_acknowledge_btn').off('click').on('click', function() {
        acknowledgeAnnulusMonitorAlarm();
    });
});

// =============================================================================
// WIMS PANEL SAVE / LOAD (associated with selected schematic)
// =============================================================================

/** Compute overall status from barrier elements: failed > not-verified > verified; if no rows, verified. */
function computeWimsOverallStatusFromBarriers() {
    var hasFailed = false;
    var hasNotVerified = false;
    $('#wims_primary_barrier_tbody tr.wims-barrier-data-row, #wims_secondary_barrier_tbody tr.wims-barrier-data-row').each(function() {
        var $dot = $(this).find('td').eq(3).find('.wims-integrity-dot');
        if ($dot.hasClass('failed')) hasFailed = true;
        else if ($dot.hasClass('not-verified')) hasNotVerified = true;
    });
    if (hasFailed) return 'failed';
    if (hasNotVerified) return 'not-verified';
    return 'verified';
}

/** Update Overall Integrity status dot from barrier elements. */
function updateWimsOverallStatusFromBarriers() {
    var status = computeWimsOverallStatusFromBarriers();
    var $dot = $('#wims_overall_status_dot');
    $dot.removeClass('verified failed not-verified').addClass(status);
    var title = status === 'failed' ? 'Failed' : (status === 'not-verified' ? 'Not verified or other issues' : 'Verified and in good state');
    $dot.attr('title', title);
}

function buildBarrierPanelEntryFromRow($tr, $tds) {
    const $statusSpan = $tds.eq(3).find('.wims-integrity-dot');
    let status = 'verified';
    if ($statusSpan.hasClass('failed')) status = 'failed';
    else if ($statusSpan.hasClass('not-verified')) status = 'not-verified';
    const remarksCell = $tds.eq(4)[0];
    const hasRemarkDot = $(remarksCell).find('.wims-barrier-remark-dot').length > 0;
    var parsed = parseBarrierElementCell($tds.eq(0).text().trim());
    var entry = {
        element: $tds.eq(0).text().trim(),
        element_name: $tr.attr('data-element-name') || parsed.element_name,
        element_type: $tr.attr('data-element-type') || parsed.element_type,
        qualification: $tds.eq(1).text().trim(),
        monitoring: $tds.eq(2).text().trim(),
        status: status,
        remarks: hasRemarkDot ? '' : $(remarksCell).text().trim()
    };
    var patchTypes = readBarrierRowPatchTypes($tr);
    if (patchTypes && patchTypes.length > 0) {
        entry.patch_types = patchTypes;
    }
    var topDepthM = $tr.attr('data-top-depth-m');
    var bottomDepthM = $tr.attr('data-bottom-depth-m');
    if (topDepthM !== undefined && topDepthM !== '' && bottomDepthM !== undefined && bottomDepthM !== '') {
        entry.top_depth_m = parseFloat(topDepthM);
        entry.bottom_depth_m = parseFloat(bottomDepthM);
    }
    return entry;
}

function buildWimsPanelData() {
    const statusClass = computeWimsOverallStatusFromBarriers();
    const primary = [];
    $('#wims_primary_barrier_tbody tr').each(function() {
        const $tr = $(this);
        if ($tr.find('td[colspan="5"]').length) return;
        const $tds = $tr.find('td');
        if ($tds.length < 5) return;
        primary.push(buildBarrierPanelEntryFromRow($tr, $tds));
    });
    const secondary = [];
    $('#wims_secondary_barrier_tbody tr').each(function() {
        const $tr = $(this);
        if ($tr.find('td[colspan="5"]').length) return;
        const $tds = $tr.find('td');
        if ($tds.length < 5) return;
        secondary.push(buildBarrierPanelEntryFromRow($tr, $tds));
    });
    var annulus_monitors = wimsAnnulusMonitors.map(function(m) {
        var entry = {
            tagName: m.tagName || null,
            tagText: m.tagText || null,
            tagUnit: m.tagUnit || null,
            annulusLetter: m.annulusLetter || getAnnulusLetterFromTag(m.tagName),
            lookbackDays: m.lookbackDays || 30
        };
        if (Object.prototype.hasOwnProperty.call(m, 'opLimitDescription')) {
            entry.opLimitDescription = m.opLimitDescription;
        }
        return entry;
    });
    var wbe_risks = [];
    $('#wims_wbe_risk_tbody tr.wims-wbe-risk-data-row').each(function() {
        var $tds = $(this).find('td');
        if ($tds.length < 8) return;
        wbe_risks.push({
            failure_mode: $tds.eq(0).text().trim(),
            effect: $tds.eq(1).text().trim(),
            l: $tds.eq(2).text().trim(),
            e: $tds.eq(3).text().trim(),
            rf: $tds.eq(4).text().trim(),
            action_plan: $tds.eq(5).text().trim(),
            months: $tds.eq(6).text().trim(),
            operate_during_failure: $tds.eq(7).text().trim()
        });
    });
    return {
        overall_status: statusClass,
        last_update_date: $('#wims_last_update_date').val() || '',
        primary_barrier_elements: primary,
        secondary_barrier_elements: secondary,
        annulus_monitors: annulus_monitors,
        wbe_risks: wbe_risks
    };
}

function buildBarrierRowHtml(item) {
    const statusClass = (item.status === 'failed' || item.status === 'not-verified' || item.status === 'verified') ? item.status : 'verified';
    const statusDot = '<span class="wims-integrity-dot ' + statusClass + '"></span>';
    const remarkCell = item.remarks
        ? (function() { const d = document.createElement('div'); d.textContent = item.remarks; return d.innerHTML; })()
        : '';
    const esc = function(t) { const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; };
    var parsed = parseBarrierElementCell(item.element || '');
    var elementName = item.element_name || parsed.element_name;
    var elementType = item.element_type || parsed.element_type;
    var depthAttrs = '';
    if (item.top_depth_m != null && item.bottom_depth_m != null && !isNaN(item.top_depth_m) && !isNaN(item.bottom_depth_m)) {
        depthAttrs = ' data-top-depth-m="' + esc(String(item.top_depth_m)) + '" data-bottom-depth-m="' + esc(String(item.bottom_depth_m)) + '"';
    }
    var patchAttr = '';
    if (Array.isArray(item.patch_types) && item.patch_types.length > 0) {
        patchAttr = ' data-patch-types="' + escapeHtmlAttr(JSON.stringify(item.patch_types)) + '"';
    }
    var nameAttr = elementName ? ' data-element-name="' + escapeHtmlAttr(elementName) + '"' : '';
    var typeAttr = elementType ? ' data-element-type="' + escapeHtmlAttr(elementType) + '"' : '';
    return '<tr class="wims-barrier-data-row"' + depthAttrs + nameAttr + typeAttr + patchAttr + '><td>' + esc(item.element) + '</td><td>' + esc(item.qualification) + '</td><td>' + esc(item.monitoring) + '</td><td>' + statusDot + '</td><td>' + remarkCell + '</td></tr>';
}

/** Collect barrier recolor rules from table rows (supports optional depth bands). */
function collectBarrierColorRules() {
    var rules = [];
    function addFromTbody(tbodyId, tableType) {
        $('#' + tbodyId + ' tr.wims-barrier-data-row').each(function() {
            var $tr = $(this);
            var name = ($tr.attr('data-element-name') || '').trim();
            var typeVal = ($tr.attr('data-element-type') || '').trim();
            if (!name || !typeVal) {
                var parsed = parseBarrierElementCell($tr.find('td').eq(0).text().trim());
                name = name || parsed.element_name;
                typeVal = typeVal || parsed.element_type;
            }
            if (!name || !typeVal) return;
            var rule = { name: name, typeVal: typeVal, tableType: tableType };
            var patchTypes = readBarrierRowPatchTypes($tr);
            if (patchTypes && patchTypes.length > 0) {
                rule.patchTypes = patchTypes;
            }
            var $statusSpan = $tr.find('td').eq(3).find('.wims-integrity-dot');
            if ($statusSpan.hasClass('failed')) rule.status = 'failed';
            else if ($statusSpan.hasClass('not-verified')) rule.status = 'not-verified';
            else rule.status = 'verified';
            var topRaw = $tr.attr('data-top-depth-m');
            var bottomRaw = $tr.attr('data-bottom-depth-m');
            if (topRaw !== undefined && topRaw !== '' && bottomRaw !== undefined && bottomRaw !== '') {
                var topDepthM = parseFloat(topRaw);
                var bottomDepthM = parseFloat(bottomRaw);
                if (!isNaN(topDepthM) && !isNaN(bottomDepthM)) {
                    rule.top_depth_m = topDepthM;
                    rule.bottom_depth_m = bottomDepthM;
                }
            }
            rules.push(rule);
        });
    }
    addFromTbody('wims_primary_barrier_tbody', 'primary');
    addFromTbody('wims_secondary_barrier_tbody', 'secondary');
    return rules;
}

function readWimsPartialRecolorDepths(prefix) {
    var enabled = $('#' + prefix + '_partial_recolor').is(':checked');
    if (!enabled) return null;
    var topDepthM = parseFloat($('#' + prefix + '_top_depth_m').val());
    var bottomDepthM = parseFloat($('#' + prefix + '_bottom_depth_m').val());
    if (isNaN(topDepthM) || isNaN(bottomDepthM)) return { error: 'Enter valid top and bottom depths [m].' };
    if (topDepthM >= bottomDepthM) return { error: 'Top depth must be less than bottom depth.' };
    return { top_depth_m: topDepthM, bottom_depth_m: bottomDepthM };
}

function buildBarrierRowDepthAttrs(depths) {
    if (!depths || depths.top_depth_m == null || depths.bottom_depth_m == null) return '';
    return ' data-top-depth-m="' + depths.top_depth_m + '" data-bottom-depth-m="' + depths.bottom_depth_m + '"';
}

function resetWimsAddPartialRecolorFields() {
    $('#wims_add_partial_recolor').prop('checked', false);
    $('#wims_add_partial_recolor_wrap').hide();
    $('#wims_add_top_depth_m, #wims_add_bottom_depth_m').val('');
}

function setWimsEditPartialRecolorFields($tr) {
    var topRaw = $tr.attr('data-top-depth-m');
    var bottomRaw = $tr.attr('data-bottom-depth-m');
    var hasBand = topRaw !== undefined && topRaw !== '' && bottomRaw !== undefined && bottomRaw !== '';
    $('#wims_edit_partial_recolor').prop('checked', hasBand);
    $('#wims_edit_partial_recolor_wrap').toggle(hasBand);
    $('#wims_edit_top_depth_m').val(hasBand ? topRaw : '');
    $('#wims_edit_bottom_depth_m').val(hasBand ? bottomRaw : '');
}

/** Schematic recolor: primary blue; secondary red; failed elements bright yellow. */
function getBarrierSchematicColor(tableType, status) {
    if (status === 'failed') return '#FFEB3B';
    if (tableType === 'secondary') return 'red';
    return '#0d6efd';
}

/** Build item_colors array from barrier tables. Returns [] when no barriers or no cache. */
function buildItemColorsFromBarriers() {
    var list = wimsCachedDrawnItems || [];
    var rules = collectBarrierColorRules();
    var itemColors = [];
    rules.forEach(function(rule) {
        list.forEach(function(item) {
            var name = (item.element_name || item.name || item.id || '').trim();
            var typeVal = (item.element_type || '').trim();
            var pt = (item.patch_type || '').trim();
            if (name !== rule.name || typeVal !== rule.typeVal || !pt) return;
            if (rule.patchTypes) {
                if (rule.patchTypes.indexOf(pt) === -1) return;
            } else if (typeVal === 'Valve' && pt.indexOf('valve_ellipse') === -1) {
                return;
            }
            var entry = {
                element_name: name,
                element_type: typeVal,
                patch_type: pt,
                color: getBarrierSchematicColor(rule.tableType, rule.status)
            };
            if (rule.top_depth_m != null && rule.bottom_depth_m != null) {
                entry.top_depth = rule.top_depth_m;
                entry.bottom_depth = rule.bottom_depth_m;
            }
            itemColors.push(entry);
        });
    });
    return itemColors;
}

/** Redraw the dashboard schematic image with barrier colors (one generate call). */
function refreshWimsSchematicFromBarriers() {
    if (!wimsCachedSchematicData) return;
    var itemColors = buildItemColorsFromBarriers();
    var payload = Object.assign({}, wimsCachedSchematicData);
    if (itemColors.length) payload.item_colors = itemColors;
    else delete payload.item_colors;
    var $dashImg = $('#dashboard_schematic_image_output');
    $dashImg.html('<span style="color:#888;">Updating schematic...</span>');
    $.ajax({
        url: '/app/wellintegrity/generate_schematic_image',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(payload),
        success: function(response) {
            if (response.image_base64) {
                $dashImg.html(
                    '<img src="data:image/png;base64,' + response.image_base64 + '" style="max-width:100%; height:auto; display:block;" />'
                );
            } else if (response.error) {
                $dashImg.html('<span class="text-danger">' + response.error + '</span>');
            }
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error updating schematic.';
            $dashImg.html('<span class="text-danger">' + msg + '</span>');
        }
    });
}

function applyWimsPanelData(panelData) {
    var data = panelData || {
        last_update_date: '',
        primary_barrier_elements: [],
        secondary_barrier_elements: [],
        annulus_monitors: [],
        wbe_risks: []
    };
    $('#wims_last_update_date').val(data.last_update_date || '');
    const $primary = $('#wims_primary_barrier_tbody');
    $primary.empty();
    if (data.primary_barrier_elements && data.primary_barrier_elements.length > 0) {
        data.primary_barrier_elements.forEach(function(item) {
            $primary.append(buildBarrierRowHtml(item));
        });
    } else {
        $primary.append('<tr><td colspan="5" class="text-muted text-center py-3">No primary barrier elements loaded.</td></tr>');
    }
    const $secondary = $('#wims_secondary_barrier_tbody');
    $secondary.empty();
    if (data.secondary_barrier_elements && data.secondary_barrier_elements.length > 0) {
        data.secondary_barrier_elements.forEach(function(item) {
            $secondary.append(buildBarrierRowHtml(item));
        });
    } else {
        $secondary.append('<tr><td colspan="5" class="text-muted text-center py-3">No secondary barrier elements loaded.</td></tr>');
    }
    updateWimsOverallStatusFromBarriers();
    if (data.annulus_monitors && Array.isArray(data.annulus_monitors)) {
        wimsAnnulusMonitors = data.annulus_monitors
            .map(function(m) {
                var tagName = m.tagName || null;
                if (!tagName) return null;
                var monitor = {
                    tagName: tagName,
                    tagText: m.tagText || tagName,
                    tagUnit: m.tagUnit || '',
                    annulusLetter: m.annulusLetter || getAnnulusLetterFromTag(tagName),
                    lookbackDays: m.lookbackDays != null ? (parseInt(m.lookbackDays, 10) || 30) : 30,
                    series: null
                };
                if (Object.prototype.hasOwnProperty.call(m, 'opLimitDescription')) {
                    monitor.opLimitDescription = m.opLimitDescription;
                }
                return monitor;
            })
            .filter(function(m) { return m !== null; });
        displayWimsAnnulusMonitors();
    } else {
        wimsAnnulusMonitors = [];
        displayWimsAnnulusMonitors();
    }
    var $riskTbody = $('#wims_wbe_risk_tbody');
    $riskTbody.empty();
    if (data.wbe_risks && Array.isArray(data.wbe_risks) && data.wbe_risks.length > 0) {
        var esc = function(t) { var d = document.createElement('div'); d.textContent = t == null ? '' : t; return d.innerHTML; };
        data.wbe_risks.forEach(function(r) {
            var row = '<tr class="wims-wbe-risk-data-row">' +
                '<td>' + esc(r.failure_mode) + '</td>' +
                '<td>' + esc(r.effect) + '</td>' +
                '<td>' + esc(r.l) + '</td>' +
                '<td>' + esc(r.e) + '</td>' +
                '<td>' + esc(r.rf) + '</td>' +
                '<td>' + esc(r.action_plan) + '</td>' +
                '<td>' + esc(r.months) + '</td>' +
                '<td>' + esc(r.operate_during_failure) + '</td>' +
                '</tr>';
            $riskTbody.append(row);
        });
    } else {
        $riskTbody.append('<tr class="wims-wbe-risk-placeholder"><td colspan="8" class="text-muted text-center py-3">No WBE risk rows loaded.</td></tr>');
    }
}

function loadWimsPanel(onPanelApplied) {
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    if (!well_name || !schematic_filename) return;
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_wims_panel',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function(data) {
            applyWimsPanelData(data.panel_data || null);
            if (typeof onPanelApplied === 'function') {
                onPanelApplied(data.panel_data || null);
            }
        },
        error: function(xhr) {
            console.error('Error loading WIMS panel:', xhr);
            if (typeof onPanelApplied === 'function') {
                onPanelApplied(null);
            }
        }
    });
}


// =============================================================================
// KPI DASHBOARD (manual fields + auto schematic image / casing OD sizes)
// =============================================================================

// Manual dashboard state (persisted per well + schematic via save_dashboard).
var DASHBOARD_OP_LIMIT_DESCRIPTIONS = [
    'Minimum wall thickness',
    'Temperature',
    'Annulus A pressure',
    'Annulus B pressure',
    'Annulus C pressure',
    'Custom'
];
var MIN_WALL_THICKNESS_DESCRIPTION = 'Minimum wall thickness';

var dashboardOpLimits = [];          // [{description, custom_description, casing, min, max, unit}]
var dashboardCasingSizes = [];       // [{od_inch, label}] auto from well tally
var dashboardHistory = [];           // [{date, event, document_id, document_filename}]
var dashboardMaintenance = [];       // [{maintenance_type, comments, interval, interval_custom_days, last_maintenance_date}]
var dashboardMaintenanceAlertToastShown = false;

var MAINTENANCE_INTERVAL_LABELS = {
    weekly: 'Weekly',
    monthly: 'Monthly',
    yearly: 'Yearly',
    custom: 'Custom'
};

function parseDashboardDateUtc(dateStr) {
    if (!dateStr || typeof dateStr !== 'string') return null;
    var parts = dateStr.trim().split('-');
    if (parts.length !== 3) return null;
    var y = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    var d = parseInt(parts[2], 10);
    if (!isFinite(y) || !isFinite(m) || !isFinite(d)) return null;
    return Date.UTC(y, m - 1, d);
}

function todayUtcMidnight() {
    var now = new Date();
    return Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
}

function addUtcDays(utcMs, days) {
    return utcMs + (days * 86400000);
}

function getMaintenanceIntervalDays(item) {
    if (!item || !item.interval) return null;
    if (item.interval === 'weekly') return 7;
    if (item.interval === 'monthly') return 30;
    if (item.interval === 'yearly') return 365;
    if (item.interval === 'custom') {
        var customDays = parseInt(item.interval_custom_days, 10);
        return isFinite(customDays) && customDays > 0 ? customDays : null;
    }
    return null;
}

function formatMaintenanceIntervalLabel(item) {
    if (!item || !item.interval) return '\u2014';
    if (item.interval === 'custom') {
        var days = getMaintenanceIntervalDays(item);
        return days ? ('Custom (' + days + ' days)') : 'Custom';
    }
    return MAINTENANCE_INTERVAL_LABELS[item.interval] || item.interval;
}

function computeMaintenanceSchedule(item) {
    var intervalDays = getMaintenanceIntervalDays(item);
    var lastMs = parseDashboardDateUtc(item && item.last_maintenance_date);
    if (!intervalDays || lastMs == null) {
        return { status: 'incomplete', overdueDays: null, percentRemaining: null, intervalDays: intervalDays };
    }
    var nextDueMs = addUtcDays(lastMs, intervalDays);
    var todayMs = todayUtcMidnight();
    var overdueDays = Math.floor((todayMs - nextDueMs) / 86400000);
    var remainingDays = -overdueDays;
    var percentRemaining = remainingDays / intervalDays;
    var status = 'ok';
    if (overdueDays > 0) {
        status = 'overdue';
    } else if (overdueDays === 0) {
        status = 'due_today';
    } else if (percentRemaining <= 0.10) {
        status = 'due_soon';
    }
    return {
        status: status,
        overdueDays: overdueDays,
        percentRemaining: percentRemaining,
        intervalDays: intervalDays,
        nextDueMs: nextDueMs
    };
}

function formatMaintenanceDueStatus(schedule) {
    if (!schedule || schedule.status === 'incomplete' || schedule.overdueDays == null) return '\u2014';
    if (schedule.overdueDays > 0) {
        return schedule.overdueDays + (schedule.overdueDays === 1 ? ' day overdue' : ' days overdue');
    }
    if (schedule.overdueDays === 0) return 'Due today';
    var remaining = -schedule.overdueDays;
    return remaining + (remaining === 1 ? ' day remaining' : ' days remaining');
}

function maintenanceDueStatusCellClass(schedule) {
    if (!schedule || schedule.status === 'incomplete') return '';
    if (schedule.status === 'overdue') return 'dashboard-maintenance-due-late';
    if (schedule.status === 'due_soon' || schedule.status === 'due_today') return 'dashboard-maintenance-due-today';
    return 'dashboard-maintenance-due-ok';
}

function normalizeMaintenanceEntry(x) {
    if (!x || typeof x !== 'object') {
        return {
            maintenance_type: '',
            comments: '',
            interval: '',
            interval_custom_days: null,
            last_maintenance_date: ''
        };
    }
    var customRaw = x.interval_custom_days;
    var customDays = customRaw == null || customRaw === '' ? null : parseInt(customRaw, 10);
    return {
        maintenance_type: x.maintenance_type || '',
        comments: x.comments || '',
        interval: x.interval || '',
        interval_custom_days: isFinite(customDays) && customDays > 0 ? customDays : null,
        last_maintenance_date: x.last_maintenance_date || ''
    };
}

function collectMaintenanceAlerts(items) {
    var alerts = [];
    (items || []).forEach(function(item) {
        var schedule = computeMaintenanceSchedule(item);
        var label = (item.maintenance_type || 'Maintenance item').trim() || 'Maintenance item';
        if (schedule.status === 'overdue') {
            alerts.push({
                type: 'overdue',
                text: label + ': ' + schedule.overdueDays + (schedule.overdueDays === 1 ? ' day' : ' days') + ' overdue'
            });
        } else if (schedule.status === 'due_today') {
            alerts.push({
                type: 'due_today',
                text: label + ': due today'
            });
        } else if (schedule.status === 'due_soon') {
            var remaining = -schedule.overdueDays;
            alerts.push({
                type: 'due_soon',
                text: label + ': ' + remaining + (remaining === 1 ? ' day' : ' days') + ' remaining'
            });
        }
    });
    return alerts;
}

function renderDashboardMaintenanceAlerts(items) {
    var alerts = collectMaintenanceAlerts(items);
    var $box = $('#dashboard_maintenance_alerts');
    if (!$box.length) return alerts;
    if (!alerts.length) {
        $box.hide().empty();
        return alerts;
    }
    var html = '<strong>Maintenance alerts</strong><ul>';
    alerts.forEach(function(a) {
        html += '<li>' + escapeDashboardHtml(a.text) + '</li>';
    });
    html += '</ul>';
    $box.html(html).show();
    return alerts;
}

function toggleMaintenanceCustomDaysField(interval) {
    $('#dashboard_maintenance_custom_days_group').toggle(interval === 'custom');
}

function readDashboardMaintenanceModalEntry() {
    var interval = ($('#dashboard_maintenance_interval').val() || '').trim();
    var customRaw = ($('#dashboard_maintenance_custom_days').val() || '').trim();
    var customDays = customRaw === '' ? null : parseInt(customRaw, 10);
    return {
        maintenance_type: ($('#dashboard_maintenance_type').val() || '').trim(),
        comments: ($('#dashboard_maintenance_comments').val() || '').trim(),
        interval: interval,
        interval_custom_days: interval === 'custom' && isFinite(customDays) && customDays > 0 ? customDays : null,
        last_maintenance_date: ($('#dashboard_maintenance_last_date').val() || '').trim()
    };
}

function escapeDashboardHtml(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : text;
    return div.innerHTML;
}

function normalizeHistoryEntry(x) {
    return {
        date: x && x.date ? x.date : '',
        event: x && x.event ? x.event : '',
        document_id: x && x.document_id ? x.document_id : null,
        document_filename: x && x.document_filename ? x.document_filename : null
    };
}

function newHistoryDocumentId() {
    return 'hist_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 9);
}

function getDashboardWellSchematic() {
    return {
        well: $('#select_well').val(),
        schematic: $('#saved_schematics_select').val()
    };
}

function historyDocumentDownloadUrl(item) {
    var ctx = getDashboardWellSchematic();
    if (!ctx.well || !ctx.schematic || !item || !item.document_id) return '#';
    return '/app/wellintegrity/history_document?selected_well=' + encodeURIComponent(ctx.well) +
        '&schematic_filename=' + encodeURIComponent(ctx.schematic) +
        '&document_id=' + encodeURIComponent(item.document_id) +
        '&document_filename=' + encodeURIComponent(item.document_filename || '');
}

function deleteHistoryDocumentRemote(documentId, done) {
    var ctx = getDashboardWellSchematic();
    if (!ctx.well || !ctx.schematic || !documentId) {
        if (typeof done === 'function') done(false);
        return;
    }
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/delete_history_document',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: ctx.well,
            schematic_filename: ctx.schematic,
            document_id: documentId
        }),
        success: function() {
            if (typeof done === 'function') done(true);
        },
        error: function() {
            if (typeof done === 'function') done(false);
        }
    });
}

function uploadHistoryDocument(documentId, file, done) {
    var ctx = getDashboardWellSchematic();
    if (!ctx.well || !ctx.schematic) {
        if (typeof done === 'function') done(null, 'Select a well and schematic first.');
        return;
    }
    var formData = new FormData();
    formData.append('history_document', file);
    formData.append('selected_well', ctx.well);
    formData.append('schematic_filename', ctx.schematic);
    formData.append('document_id', documentId);
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/upload_history_document',
        data: formData,
        processData: false,
        contentType: false,
        success: function(data) {
            if (typeof done === 'function') done(data, null);
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error uploading document.';
            if (typeof done === 'function') done(null, msg);
        }
    });
}

function updateHistoryDocumentCurrentDisplay(item) {
    var $current = $('#dashboard_history_document_current');
    var $removeWrap = $('#dashboard_history_remove_document_wrap');
    $('#dashboard_history_document').val('');
    $('#dashboard_history_remove_document').prop('checked', false);
    if (item && item.document_id && item.document_filename) {
        var url = historyDocumentDownloadUrl(item);
        $current.html(
            'Attached: <a href="' + url + '" class="dashboard-history-document-link" target="_blank" rel="noopener">' +
            escapeDashboardHtml(item.document_filename) + '</a>'
        ).show();
        $removeWrap.show();
    } else {
        $current.hide().empty();
        $removeWrap.hide();
    }
}

function finalizeHistoryEntrySave(idxRaw, entry) {
    if (idxRaw === '') {
        dashboardHistory.push(entry);
    } else {
        dashboardHistory[parseInt(idxRaw, 10)] = entry;
    }
    renderDashboardHistory();
    $('#dashboard_history_modal').removeClass('show');
}

function isMinimumWallThicknessLimit(item) {
    return item && item.description === MIN_WALL_THICKNESS_DESCRIPTION;
}

function getOpLimitDisplayDescription(item) {
    if (!item) return '';
    if (item.description === 'Custom') {
        return (item.custom_description || '').trim() || 'Custom';
    }
    return item.description || '';
}

function findOpLimitByStoredDescription(storedDesc) {
    if (storedDesc == null || storedDesc === '') return null;
    return (dashboardOpLimits || []).find(function(x) {
        return getOpLimitDisplayDescription(x) === storedDesc || x.description === storedDesc;
    }) || null;
}

function getMinimumWallThicknessLimits() {
    return (dashboardOpLimits || []).filter(isMinimumWallThicknessLimit);
}

function normalizeOpLimitEntry(x) {
    var desc = x && x.description ? String(x.description) : '';
    if (DASHBOARD_OP_LIMIT_DESCRIPTIONS.indexOf(desc) >= 0) {
        return {
            description: desc,
            custom_description: x.custom_description != null ? String(x.custom_description) : '',
            casing: x.casing != null ? String(x.casing) : '',
            min: x.min != null ? x.min : '',
            max: x.max != null ? x.max : '',
            unit: x.unit || ''
        };
    }
    return {
        description: 'Custom',
        custom_description: desc,
        casing: x.casing != null ? String(x.casing) : '',
        min: x.min != null ? x.min : '',
        max: x.max != null ? x.max : '',
        unit: x.unit || ''
    };
}

function wallThicknessLimitFromLegacyRow(row) {
    var label = row.casing != null ? String(row.casing) : '';
    if (!label) return null;
    var thicknessMm = row.current_min_thickness_mm != null ? row.current_min_thickness_mm : '';
    if (String(thicknessMm).trim() === '') return null;
    return {
        description: MIN_WALL_THICKNESS_DESCRIPTION,
        custom_description: '',
        casing: label,
        min: thicknessMm,
        max: '',
        unit: 'mm'
    };
}

function populateOpLimitCasingSelect(selectedLabel) {
    var $sel = $('#dashboard_op_limit_casing').empty().append('<option value="">Select casing...</option>');
    (dashboardCasingSizes || []).forEach(function(size) {
        var label = size.label != null ? String(size.label) : '';
        if (!label) return;
        $sel.append($('<option></option>').attr('value', label).text(label));
    });
    $sel.val(selectedLabel != null ? String(selectedLabel) : '');
}

function toggleOpLimitModalFields(description) {
    var desc = description || '';
    var isWall = desc === MIN_WALL_THICKNESS_DESCRIPTION;
    var isCustom = desc === 'Custom';

    $('#dashboard_op_limit_custom_group').toggle(isCustom);
    $('#dashboard_op_limit_casing_group').toggle(isWall);
    $('#dashboard_op_limit_max_group').toggle(!isWall);
    $('#dashboard_op_limit_unit_group').toggle(!isWall);
    $('#dashboard_op_limit_min_label').text(isWall ? 'Minimum thickness [mm]' : 'Min.');

    if (isWall) {
        populateOpLimitCasingSelect($('#dashboard_op_limit_casing').val());
    }
}

function readOpLimitModalEntry() {
    var description = ($('#dashboard_op_limit_description').val() || '').trim();
    var entry = {
        description: description,
        custom_description: ($('#dashboard_op_limit_custom_description').val() || '').trim(),
        casing: ($('#dashboard_op_limit_casing').val() || '').trim(),
        min: ($('#dashboard_op_limit_min').val() || '').trim(),
        max: ($('#dashboard_op_limit_max').val() || '').trim(),
        unit: ($('#dashboard_op_limit_unit').val() || '').trim()
    };

    if (description === MIN_WALL_THICKNESS_DESCRIPTION) {
        entry.max = '';
        entry.unit = 'mm';
    } else if (description !== 'Custom') {
        entry.custom_description = '';
        entry.casing = '';
    }

    return entry;
}

function validateOpLimitEntry(entry, editIndex) {
    if (!entry.description) {
        return 'Select a description.';
    }
    if (entry.description === 'Custom' && !entry.custom_description) {
        return 'Enter a custom description.';
    }
    if (isMinimumWallThicknessLimit(entry)) {
        if (!entry.casing) {
            return 'Select a casing.';
        }
        if (!entry.min || !isFinite(parseFloat(entry.min))) {
            return 'Enter a valid minimum thickness.';
        }
        var duplicate = (dashboardOpLimits || []).some(function(item, index) {
            if (editIndex >= 0 && index === editIndex) return false;
            return isMinimumWallThicknessLimit(item) && String(item.casing) === String(entry.casing);
        });
        if (duplicate) {
            return 'A Minimum wall thickness limit already exists for this casing.';
        }
    }
    return '';
}

/** Clear all manual dashboard fields back to defaults (does not touch casing sizes). */
function resetDashboardManualState() {
    dashboardOpLimits = [];
    dashboardHistory = [];
    dashboardMaintenance = [];
}

/** Called on well change: reset manual fields, set name, clear image, fetch casing sizes. */
function resetDashboardForWell(wellName) {
    $('#dashboard_well_name').text('Well');
    $('#dashboard_schematic_image_output').html('<span style="color:#888;">Select a schematic to view.</span>');
    dashboardCasingSizes = [];
    resetDashboardManualState();
    renderDashboardManualSections();
    if (wellName) {
        fetchDashboardTallySizes(wellName);
    }
}

// ---------------------------------------------------------------------------
// Renderers
// ---------------------------------------------------------------------------

function renderDashboardOpLimits() {
    var $tbody = $('#dashboard_op_limits_tbody');
    $tbody.empty();
    if (!dashboardOpLimits.length) {
        $tbody.append('<tr><td colspan="5" class="text-muted text-center py-3">No operational limits.</td></tr>');
        return;
    }
    dashboardOpLimits.forEach(function(item, index) {
        var casingCell = isMinimumWallThicknessLimit(item) && item.casing
            ? escapeDashboardHtml(item.casing)
            : '<span class="text-muted">&mdash;</span>';
        var row = '<tr class="dashboard-data-row" data-index="' + index + '">' +
            '<td>' + escapeDashboardHtml(getOpLimitDisplayDescription(item)) + '</td>' +
            '<td>' + casingCell + '</td>' +
            '<td>' + escapeDashboardHtml(item.min) + '</td>' +
            '<td>' + escapeDashboardHtml(item.max) + '</td>' +
            '<td>' + escapeDashboardHtml(item.unit) + '</td>' +
            '</tr>';
        $tbody.append(row);
    });
}

function renderDashboardHistory() {
    var $tbody = $('#dashboard_history_tbody');
    $tbody.empty();
    if (!dashboardHistory.length) {
        $tbody.append('<tr><td colspan="3" class="text-muted text-center py-3">No history entries.</td></tr>');
        return;
    }
    dashboardHistory.forEach(function(item, index) {
        var docCell = '<span class="text-muted">&mdash;</span>';
        if (item.document_id && item.document_filename) {
            var docUrl = historyDocumentDownloadUrl(item);
            docCell = '<a href="' + docUrl + '" class="dashboard-history-document-link" target="_blank" rel="noopener">' +
                escapeDashboardHtml(item.document_filename) + '</a>';
        }
        var row = '<tr class="dashboard-data-row" data-index="' + index + '">' +
            '<td>' + escapeDashboardHtml(item.date) + '</td>' +
            '<td>' + escapeDashboardHtml(item.event) + '</td>' +
            '<td>' + docCell + '</td>' +
            '</tr>';
        $tbody.append(row);
    });
}

function renderDashboardMaintenance() {
    var $tbody = $('#dashboard_maintenance_tbody');
    $tbody.empty();
    renderDashboardMaintenanceAlerts(dashboardMaintenance);
    if (!dashboardMaintenance.length) {
        $tbody.append('<tr><td colspan="5" class="text-muted text-center py-3">No maintenance items.</td></tr>');
        return;
    }
    dashboardMaintenance.forEach(function(item, index) {
        var schedule = computeMaintenanceSchedule(item);
        var dueStatusText = formatMaintenanceDueStatus(schedule);
        var dueStatusCls = maintenanceDueStatusCellClass(schedule);
        var commentsHtml = escapeDashboardHtml(item.comments || '');
        var row = '<tr class="dashboard-data-row" data-index="' + index + '">' +
            '<td>' + escapeDashboardHtml(item.maintenance_type) + '</td>' +
            '<td>' + commentsHtml + '</td>' +
            '<td>' + escapeDashboardHtml(formatMaintenanceIntervalLabel(item)) + '</td>' +
            '<td>' + escapeDashboardHtml(item.last_maintenance_date || '\u2014') + '</td>' +
            '<td class="' + dueStatusCls + '">' + escapeDashboardHtml(dueStatusText) + '</td>' +
            '</tr>';
        $tbody.append(row);
    });
}

/** Re-render every manual dashboard section. */
function renderDashboardManualSections() {
    renderDashboardOpLimits();
    renderDashboardHistory();
    renderDashboardMaintenance();
}

/** Set casing rows from fetched tally OD sizes. */
function renderDashboardCasingRows(sizes) {
    dashboardCasingSizes = Array.isArray(sizes) ? sizes : [];
}

// ---------------------------------------------------------------------------
// Data fetch / persistence
// ---------------------------------------------------------------------------

/** Fetch unique casing OD sizes from the well tally and render the casing rows. */
function fetchDashboardTallySizes(wellName) {
    if (!wellName) return;
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_tally_sizes',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: wellName }),
        success: function(data) {
            renderDashboardCasingRows((data && data.sizes) || []);
        },
        error: function() {
            renderDashboardCasingRows([]);
        }
    });
}

/** Assemble the manual dashboard state into a JSON-friendly object for saving. */
function buildDashboardData() {
    return {
        operational_limits: dashboardOpLimits,
        history: dashboardHistory,
        maintenance: dashboardMaintenance
    };
}

/** Populate dashboard state from a loaded JSON object, then re-render. */
function applyDashboardData(data) {
    var d = data || {};

    // -- operational limits (with legacy migration) -----
    dashboardOpLimits = Array.isArray(d.operational_limits)
        ? d.operational_limits.map(normalizeOpLimitEntry)
        : [];

    var wt = d.wall_thickness || {};
    var legacyRows = Array.isArray(wt.rows) ? wt.rows : [];
    legacyRows.forEach(function(row) {
        var migrated = wallThicknessLimitFromLegacyRow(row);
        if (!migrated) return;
        var exists = dashboardOpLimits.some(function(item) {
            return isMinimumWallThicknessLimit(item) && String(item.casing) === String(migrated.casing);
        });
        if (!exists) {
            dashboardOpLimits.push(migrated);
        }
    });

    // -- history / maintenance ----
    dashboardHistory = Array.isArray(d.history) ? d.history.map(normalizeHistoryEntry) : [];
    dashboardMaintenance = Array.isArray(d.maintenance) ? d.maintenance.map(function(x) {
        if (x && (x.comments != null || x.interval != null || x.last_maintenance_date != null)) {
            return normalizeMaintenanceEntry(x);
        }
        return normalizeMaintenanceEntry({
            maintenance_type: x.maintenance_type || '',
            comments: '',
            interval: '',
            interval_custom_days: null,
            last_maintenance_date: ''
        });
    }) : [];

    // -- re-render everything -----
    renderDashboardManualSections();
}

function saveDashboard() {
    var well_name = $('#select_well').val();
    var schematic_filename = $('#saved_schematics_select').val();
    if (!well_name || !schematic_filename) {
        showErrorMessage('Please select a well and a schematic first.');
        return;
    }
    var dashboardData = buildDashboardData();
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_dashboard',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename,
            dashboard_data: dashboardData
        }),
        success: function() {
            showSuccessMessage('Dashboard saved successfully.');
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error saving dashboard.';
            showErrorMessage(msg);
        }
    });
}

/**
 * Save the dashboard fields and the relocated WIMS panel together under the
 * current well + schematic, reporting a single combined result. This is the
 * sole save trigger now that the WIMS card lives inside the Dashboard card.
 */
function saveDashboardAndPanel() {
    var well_name = $('#select_well').val();
    var schematic_filename = $('#saved_schematics_select').val();
    if (!well_name || !schematic_filename) {
        showErrorMessage('Please select a well and a schematic first.');
        return;
    }

    // -- build both payloads -----
    var dashboardData = buildDashboardData();
    var panelData = buildWimsPanelData();

    // -- stamp the WIMS panel with today's date ----
    var today = new Date();
    var yyyy = today.getFullYear();
    var mm = String(today.getMonth() + 1).padStart(2, '0');
    var dd = String(today.getDate()).padStart(2, '0');
    panelData.last_update_date = yyyy + '-' + mm + '-' + dd;
    $('#wims_last_update_date').val(panelData.last_update_date);

    // -- fire dashboard + panel saves in parallel ----
    var dashboardReq = $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_dashboard',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename,
            dashboard_data: dashboardData
        })
    });
    var panelReq = $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_wims_panel',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename,
            panel_data: panelData
        })
    });

    // -- report a single combined result ----
    $.when(dashboardReq, panelReq).done(function() {
        showSuccessMessage('Dashboard saved successfully.');
    }).fail(function(xhr) {
        var msg = (xhr && xhr.responseJSON && xhr.responseJSON.error)
            ? xhr.responseJSON.error : 'Error saving dashboard.';
        showErrorMessage(msg);
    });
}

function loadDashboard() {
    var well_name = $('#select_well').val();
    var schematic_filename = $('#saved_schematics_select').val();
    if (!well_name || !schematic_filename) return;
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_dashboard',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function(data) {
            dashboardMaintenanceAlertToastShown = false;
            applyDashboardData(data && data.dashboard_data ? data.dashboard_data : null);
            var alerts = collectMaintenanceAlerts(dashboardMaintenance);
            if (alerts.length && !dashboardMaintenanceAlertToastShown) {
                dashboardMaintenanceAlertToastShown = true;
                var summary = alerts.map(function(a) { return a.text; }).join('; ');
                if (typeof showInfoMessage === 'function') {
                    showInfoMessage('Maintenance: ' + summary);
                }
            }
        },
        error: function(xhr) {
            console.error('Error loading dashboard:', xhr);
            applyDashboardData(null);
        }
    });
}

// ---------------------------------------------------------------------------
// Modal openers (Add / Edit)
// ---------------------------------------------------------------------------

function openDashboardOpLimitModal(index) {
    var isEdit = typeof index === 'number' && index >= 0 && index < dashboardOpLimits.length;
    var item = isEdit ? dashboardOpLimits[index] : {
        description: MIN_WALL_THICKNESS_DESCRIPTION,
        custom_description: '',
        casing: '',
        min: '',
        max: '',
        unit: ''
    };
    $('#dashboard_op_limit_index').val(isEdit ? index : '');
    $('#dashboard_op_limit_modal_title').text(isEdit ? 'Edit operational limit' : 'Add operational limit');
    $('#dashboard_op_limit_description').val(item.description || MIN_WALL_THICKNESS_DESCRIPTION);
    $('#dashboard_op_limit_custom_description').val(item.custom_description || '');
    populateOpLimitCasingSelect(item.casing || '');
    $('#dashboard_op_limit_min').val(item.min != null ? item.min : '');
    $('#dashboard_op_limit_max').val(item.max != null ? item.max : '');
    $('#dashboard_op_limit_unit').val(item.unit || '');
    toggleOpLimitModalFields(item.description || MIN_WALL_THICKNESS_DESCRIPTION);
    $('#dashboard_op_limit_delete_btn').toggle(isEdit);
    $('#dashboard_op_limit_modal').addClass('show');
}

function openDashboardHistoryModal(index) {
    var isEdit = typeof index === 'number' && index >= 0 && index < dashboardHistory.length;
    var item = isEdit ? dashboardHistory[index] : normalizeHistoryEntry(null);
    $('#dashboard_history_index').val(isEdit ? index : '');
    $('#dashboard_history_modal_title').text(isEdit ? 'Edit history entry' : 'Add history entry');
    $('#dashboard_history_date').val(item.date || '');
    $('#dashboard_history_event').val(item.event || '');
    updateHistoryDocumentCurrentDisplay(item);
    $('#dashboard_history_delete_btn').toggle(isEdit);
    $('#dashboard_history_modal').addClass('show');
}

function openDashboardMaintenanceModal(index) {
    var isEdit = typeof index === 'number' && index >= 0 && index < dashboardMaintenance.length;
    var item = isEdit ? dashboardMaintenance[index] : normalizeMaintenanceEntry(null);
    $('#dashboard_maintenance_index').val(isEdit ? index : '');
    $('#dashboard_maintenance_modal_title').text(isEdit ? 'Edit maintenance item' : 'Add maintenance item');
    $('#dashboard_maintenance_type').val(item.maintenance_type || '');
    $('#dashboard_maintenance_comments').val(item.comments || '');
    $('#dashboard_maintenance_interval').val(item.interval || '');
    $('#dashboard_maintenance_custom_days').val(
        item.interval_custom_days != null ? String(item.interval_custom_days) : ''
    );
    $('#dashboard_maintenance_last_date').val(item.last_maintenance_date || '');
    toggleMaintenanceCustomDaysField(item.interval || '');
    $('#dashboard_maintenance_delete_btn').toggle(isEdit);
    $('#dashboard_maintenance_modal').addClass('show');
}

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------

$(document).ready(function() {
    // -- Save dashboard (dashboard fields + relocated WIMS panel) ----
    $('#dashboard_save_btn').off('click').on('click', function() {
        saveDashboardAndPanel();
    });

    // -- Row clicks open the matching Edit modal ----
    $('#dashboard_op_limits_tbody').off('click').on('click', 'tr.dashboard-data-row', function() {
        openDashboardOpLimitModal(parseInt($(this).attr('data-index'), 10));
    });
    $('#dashboard_history_tbody').off('click').on('click', 'tr.dashboard-data-row', function(e) {
        if ($(e.target).closest('.dashboard-history-document-link').length) return;
        openDashboardHistoryModal(parseInt($(this).attr('data-index'), 10));
    });
    $('#dashboard_maintenance_tbody').off('click').on('click', 'tr.dashboard-data-row', function() {
        openDashboardMaintenanceModal(parseInt($(this).attr('data-index'), 10));
    });

    // -- Add buttons -----
    $('#dashboard_add_op_limit_btn').off('click').on('click', function() { openDashboardOpLimitModal(-1); });
    $('#dashboard_add_history_btn').off('click').on('click', function() { openDashboardHistoryModal(-1); });
    $('#dashboard_add_maintenance_btn').off('click').on('click', function() { openDashboardMaintenanceModal(-1); });

    $('#dashboard_maintenance_interval').off('change').on('change', function() {
        toggleMaintenanceCustomDaysField($(this).val());
    });

    $('#dashboard_op_limit_description').off('change').on('change', function() {
        toggleOpLimitModalFields($(this).val());
    });

    // -- Operational limit: save / delete / cancel ----
    $('#dashboard_op_limit_save_btn').off('click').on('click', function() {
        var idxRaw = $('#dashboard_op_limit_index').val();
        var editIndex = idxRaw === '' ? -1 : parseInt(idxRaw, 10);
        var entry = readOpLimitModalEntry();
        var validationError = validateOpLimitEntry(entry, editIndex);
        if (validationError) {
            if (typeof showErrorMessage === 'function') showErrorMessage(validationError);
            return;
        }
        if (idxRaw === '') {
            dashboardOpLimits.push(entry);
        } else {
            dashboardOpLimits[editIndex] = entry;
        }
        renderDashboardOpLimits();
        if (typeof displayWimsAnnulusMonitors === 'function') displayWimsAnnulusMonitors();
        $('#dashboard_op_limit_modal').removeClass('show');
    });
    $('#dashboard_op_limit_delete_btn').off('click').on('click', function() {
        var idxRaw = $('#dashboard_op_limit_index').val();
        if (idxRaw !== '') {
            dashboardOpLimits.splice(parseInt(idxRaw, 10), 1);
            renderDashboardOpLimits();
            if (typeof displayWimsAnnulusMonitors === 'function') displayWimsAnnulusMonitors();
        }
        $('#dashboard_op_limit_modal').removeClass('show');
    });
    $('#dashboard_op_limit_cancel_btn').off('click').on('click', function() {
        $('#dashboard_op_limit_modal').removeClass('show');
    });

    // -- History: save / delete / cancel ----
    $('#dashboard_history_save_btn').off('click').on('click', function() {
        var idxRaw = $('#dashboard_history_index').val();
        var isEdit = idxRaw !== '';
        var existing = isEdit ? dashboardHistory[parseInt(idxRaw, 10)] : null;
        var entry = normalizeHistoryEntry({
            date: ($('#dashboard_history_date').val() || '').trim(),
            event: ($('#dashboard_history_event').val() || '').trim(),
            document_id: existing && existing.document_id ? existing.document_id : null,
            document_filename: existing && existing.document_filename ? existing.document_filename : null
        });
        if (!entry.date && !entry.event) { return; }

        var fileInput = document.getElementById('dashboard_history_document');
        var file = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
        var removeDoc = $('#dashboard_history_remove_document').is(':checked');

        function afterDocumentOps() {
            finalizeHistoryEntrySave(idxRaw, entry);
        }

        if (removeDoc && entry.document_id) {
            deleteHistoryDocumentRemote(entry.document_id, function() {
                entry.document_id = null;
                entry.document_filename = null;
                afterDocumentOps();
            });
            return;
        }

        if (file) {
            if (!entry.document_id) {
                entry.document_id = newHistoryDocumentId();
            }
            uploadHistoryDocument(entry.document_id, file, function(data, err) {
                if (err) {
                    if (typeof showErrorMessage === 'function') showErrorMessage(err);
                    return;
                }
                entry.document_id = data.document_id || entry.document_id;
                entry.document_filename = data.document_filename || file.name;
                afterDocumentOps();
            });
            return;
        }

        afterDocumentOps();
    });
    $('#dashboard_history_delete_btn').off('click').on('click', function() {
        var idxRaw = $('#dashboard_history_index').val();
        if (idxRaw === '') {
            $('#dashboard_history_modal').removeClass('show');
            return;
        }
        var idx = parseInt(idxRaw, 10);
        var item = dashboardHistory[idx];
        function removeRow() {
            dashboardHistory.splice(idx, 1);
            renderDashboardHistory();
            $('#dashboard_history_modal').removeClass('show');
        }
        if (item && item.document_id) {
            deleteHistoryDocumentRemote(item.document_id, function() {
                removeRow();
            });
        } else {
            removeRow();
        }
    });
    $('#dashboard_history_cancel_btn').off('click').on('click', function() {
        $('#dashboard_history_modal').removeClass('show');
    });

    // -- Maintenance: save / delete / cancel ----
    $('#dashboard_maintenance_save_btn').off('click').on('click', function() {
        var idxRaw = $('#dashboard_maintenance_index').val();
        var entry = readDashboardMaintenanceModalEntry();
        if (!entry.maintenance_type) { return; }
        if (entry.interval === 'custom' && !entry.interval_custom_days) {
            if (typeof showErrorMessage === 'function') {
                showErrorMessage('Enter a custom interval in days.');
            }
            return;
        }
        if (idxRaw === '') {
            dashboardMaintenance.push(entry);
        } else {
            dashboardMaintenance[parseInt(idxRaw, 10)] = entry;
        }
        renderDashboardMaintenance();
        $('#dashboard_maintenance_modal').removeClass('show');
    });
    $('#dashboard_maintenance_delete_btn').off('click').on('click', function() {
        var idxRaw = $('#dashboard_maintenance_index').val();
        if (idxRaw !== '') {
            dashboardMaintenance.splice(parseInt(idxRaw, 10), 1);
            renderDashboardMaintenance();
        }
        $('#dashboard_maintenance_modal').removeClass('show');
    });
    $('#dashboard_maintenance_cancel_btn').off('click').on('click', function() {
        $('#dashboard_maintenance_modal').removeClass('show');
    });

    // -- Close any dashboard modal on overlay click ----
    [
        'dashboard_op_limit_modal',
        'dashboard_history_modal',
        'dashboard_maintenance_modal'
    ].forEach(function(modalId) {
        $('#' + modalId).off('click.dashboardOverlay').on('click.dashboardOverlay', function(e) {
            if (e.target === this) {
                $(this).removeClass('show');
            }
        });
    });

    // -- Erosion panel handlers ----
    $('#erosion_model_select').on('change', toggleErosionModelParams);
    toggleErosionModelParams();

    $('#erosion_add_component_btn').on('click', function() {
        addEspComponentRow({ component_type: 'custom', name: 'Custom', length_m: 0, od_inch: 0 });
    });
    $('#erosion_esp_components_tbody').on('click', '.erosion-remove-row', function() {
        $(this).closest('tr').remove();
    });
    $('#erosion_save_esp_geometry_btn').on('click', saveEspGeometry);
    $('#erosion_run_btn').on('click', runErosionCalculation);

    var erosionEnd = new Date();
    var erosionStart = new Date();
    erosionStart.setMonth(erosionStart.getMonth() - 3);
    $('#erosion_end_date').val(erosionEnd.toISOString().slice(0, 10));
    $('#erosion_start_date').val(erosionStart.toISOString().slice(0, 10));
});
