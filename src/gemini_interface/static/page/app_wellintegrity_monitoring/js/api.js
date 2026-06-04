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

$('#select_well').off('change').on('change', function () {
    const well_name = $('#select_well').val();
    window.lastProcessedLogsData = null; // clear so dropdown uses get_log_status for this well
    if (!well_name) {
        hideDataUI();
        $('#processed_logs_panel').hide();
        $('#view_processed_log_block').hide();
        hideProcessedLogSection();
        $('#processing_results_container').hide().empty();
        hideSchematicMonitoringSection(true);
        return;
    }
    // Show Well Logs when well is selected; show View processed log + panel only when there are processed logs
    showDataUI();
    loadWellLogs();
    checkForSavedSchematics();
    hideSchematicMonitoringSection(true);
    setTimeout(syncProcessedLogPanelHeight, 150);
});


$('#processed_log_select').off('change').on('change', function() {
    const selectedLog = $('#processed_log_select').val();
    if (!selectedLog) {
        $('#processing_results_container').hide().empty();
        return;
    }
    // If we already have this log's data (e.g. after processing), render from cache
    if (window.lastProcessedLogsData && window.lastProcessedLogsData[selectedLog] && typeof window._renderProcessedLogTable === 'function') {
        window._renderProcessedLogTable(selectedLog);
    } else {
        loadProcessedLog(selectedLog);
    }
});

$('#saved_schematics_select').off('change').on('change', function() {
    const well_name = $('#select_well').val();
    const schematic_filename = $(this).val();
    const $wimsOutput = $('#wims_schematic_image_output');
    const $subcards = $('#wims_subcards_container');
    wimsAnnulusMonitors = [];
    wimsCachedAnnulusData = [];
    wimsCachedDrawnItems = [];
    wimsCachedSchematicData = null;
    displayWimsAnnulusMonitors();
    if (!schematic_filename) {
        $wimsOutput.hide().empty();
        $subcards.hide();
        return;
    }
    if (!well_name) {
        $wimsOutput.show().html('<span class="text-danger">Select a well first.</span>');
        $subcards.hide();
        return;
    }
    $subcards.show();
    $wimsOutput.show().html('<span style="color:#888">Loading schematic...</span>');
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_schematic',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, schematic_filename: schematic_filename }),
        success: function(schematicData) {
            wimsCachedSchematicData = schematicData;
            // Load WIMS panel first (from file) so it works even when schematic server is down
            $wimsOutput.html('<span style="color:#888">Loading panel...</span>');
            loadWimsPanel(function(panelData) {
                $wimsOutput.html('<span style="color:#888">Generating schematic...</span>');
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
                            wimsCachedAnnulusData = response.annulus_information || response.annulus_data || response.annuluses || [];
                            wimsCachedDrawnItems = response.drawn_items || [];
                            $wimsOutput.html(
                                '<img src="data:image/png;base64,' + response.image_base64 + '" style="max-width:100%; height:auto; display:block;" />'
                            );
                        } else if (response.error) {
                            $wimsOutput.html('<span class="text-danger">' + response.error + '</span>');
                        } else {
                            $wimsOutput.html('<span class="text-danger">No schematic returned.</span>');
                        }
                    },
                    error: function(xhr) {
                        const msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error generating schematic.';
                        $wimsOutput.html('<span class="text-danger">' + msg + '</span>');
                    }
                });
            });
        },
        error: function(xhr) {
            const msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error loading schematic.';
            $wimsOutput.html('<span class="text-danger">' + msg + '</span>');
        }
    });
});

function checkForSavedSchematics() {
    const well_name = $('#select_well').val();
    
    if (!well_name) {
        hideSchematicUI();
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
            showSchematicUI();
        },
        error: function (xhr) {
            console.error('Error loading saved schematics:', xhr);
            hideSchematicUI();
        }
    });
}

function generateSchematicImage(schematicData, caliperData) {
    const outputDiv = $('#schematic_image_output');
    outputDiv.html('<span style="color:gray">Generating schematic...</span>');
    
    // Show the schematic and monitoring section
    $('#schematic_monitoring_section').show();
    
    const payload = caliperData ? { ...schematicData, caliper_data: caliperData } : schematicData;
    $.ajax({
        url: '/app/wellintegrity/generate_schematic',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(payload),
        success: function(response) {
            if (response.image_base64) {
                outputDiv.html(
                    `<img src="data:image/png;base64,${response.image_base64}" style="max-width:100%; height:auto;" />`
                );
                // Load monitoring data after schematic is generated
                loadPressureElements();
                loadAnnulusReadings();
                // Load saved monitors if any exist
                loadSavedMonitors();
            } else if (response.error) {
                outputDiv.html(`<span style="color:red">${response.error}</span>`);
            } else {
                outputDiv.html('<span style="color:red">No schematic returned.</span>');
            }
        },
        error: function(xhr) {
            const msg = xhr.responseJSON?.error ? 
                `Error generating schematic: ${xhr.responseJSON.error}` : 
                'Error generating schematic.';
            outputDiv.html(`<span style="color:red">${msg}</span>`);
        }
    });
}

function displaySchematicData(data) {
    const displayDiv = $('#schematic_data_display');
    
    let html = '<div class="card">';
    html += '<div class="card-header"><h3>Integrity Schematic: ' + (data.schematic_name || 'Unnamed') + '</h3></div>';
    html += '<div class="card-body">';
    
    if (data.integrity_parameters) {
        html += '<h4>Integrity Parameters</h4>';
        html += '<table class="table table-bordered">';
        html += '<tr><td>Casing Pressure Limit</td><td>' + data.integrity_parameters.casing_pressure_limit + ' psi</td></tr>';
        html += '<tr><td>Tubing Pressure Limit</td><td>' + data.integrity_parameters.tubing_pressure_limit + ' psi</td></tr>';
        html += '<tr><td>Annulus Pressure Limit</td><td>' + data.integrity_parameters.annulus_pressure_limit + ' psi</td></tr>';
        html += '<tr><td>Temperature Limit</td><td>' + data.integrity_parameters.temperature_limit + ' °F</td></tr>';
        html += '</table>';
    }
    
    if (data.monitoring_points && data.monitoring_points.length > 0) {
        html += '<h4>Monitoring Points</h4>';
        html += '<table class="table table-bordered">';
        html += '<thead><tr><th>Name</th><th>Depth (ft)</th><th>Pressure Type</th></tr></thead>';
        html += '<tbody>';
        data.monitoring_points.forEach(point => {
            html += '<tr><td>' + point.name + '</td><td>' + point.depth + '</td><td>' + point.pressure_type + '</td></tr>';
        });
        html += '</tbody></table>';
    }
    
    html += '</div></div>';
    
    displayDiv.html(html);
}

function showSchematicUI() {
    $('#saved_schematics_section').show();
}

function hideSchematicUI() {
    $('#saved_schematics_section').hide();
}

function showDataUI() {
    $('#well_data_section').show();
    $('#wims_card').show();
    $('#forecasting_card').show();
    loadForecastingLogDatesForm();
    // Corrosion rate is only loaded when user clicks "Calculate corrosion rate"
    $('#forecasting_corrosion_rate_placeholder').show().text('');
    $('#forecasting_corrosion_rate_section').hide();
}

function hideDataUI() {
    $('#well_data_section').hide();
    $('#wims_card').hide();
    $('#forecasting_card').hide();
}

/** Load log dates form (processed log list + date inputs) in Forecasting panel. */
function loadForecastingLogDatesForm() {
    var well_name = $('#select_well').val();
    var $section = $('#forecasting_log_dates_section');
    var $calculateRow = $('#forecasting_calculate_row');
    if (!well_name) {
        $section.hide();
        $calculateRow.hide();
        return;
    }
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_log_status',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(logStatusList) {
            var processedNames = (logStatusList || []).filter(function(log) { return log.processed; }).map(function(log) { return log.name; });
            if (processedNames.length === 0) {
                $section.hide();
                $calculateRow.hide();
                return;
            }
            $.ajax({
                type: 'POST',
                url: '/app/wellintegrity/get_log_dates',
                contentType: 'application/json',
                data: JSON.stringify({ selected_well: well_name }),
                success: function(data) {
                    var saved = (data && data.log_dates) ? data.log_dates : {};
                    var startTime = (data && data.start_time) ? data.start_time : '';
                    var $tbody = $('#forecasting_log_dates_tbody');
                    $tbody.empty();
                    processedNames.forEach(function(logName) {
                        var $tr = $('<tr></tr>');
                        $tr.append($('<td></td>').text(logName));
                        var $input = $('<input type="date" class="form-control form-control-sm" style="background:#2a2d47;border:1px solid #444;color:#ccc;max-width:160px;">').attr('data-log-name', logName).val(saved[logName] || '');
                        $tr.append($('<td></td>').append($input));
                        $tbody.append($tr);
                    });
                    $('#forecasting_start_time_input').val(startTime || '');
                    var minThick = (data && data.minimum_remaining_thickness_mm != null && data.minimum_remaining_thickness_mm !== '') ? data.minimum_remaining_thickness_mm : '';
                    $('#forecasting_min_remaining_thickness').val(minThick);
                    $section.show();
                    $calculateRow.show();
                    updateForecastingCalculateButtonState();
                },
                error: function() {
                    var $tbody = $('#forecasting_log_dates_tbody');
                    $tbody.empty();
                    processedNames.forEach(function(logName) {
                        var $tr = $('<tr></tr>');
                        $tr.append($('<td></td>').text(logName));
                        $tr.append($('<td></td>').append($('<input type="date" class="form-control form-control-sm" style="background:#2a2d47;border:1px solid #444;color:#ccc;max-width:160px;">').attr('data-log-name', logName)));
                        $tbody.append($tr);
                    });
                    $('#forecasting_start_time_input').val('');
                    $('#forecasting_min_remaining_thickness').val('');
                    $section.show();
                    $calculateRow.show();
                    updateForecastingCalculateButtonState();
                }
            });
        },
        error: function() {
            $section.hide();
            $calculateRow.hide();
        }
    });
}

/** Enable Calculate corrosion rate button only when Baseline date and at least one log date are set. */
function updateForecastingCalculateButtonState() {
    var baseline = ($('#forecasting_start_time_input').val() || '').trim();
    var $inputs = $('#forecasting_log_dates_tbody input[type="date"]');
    var allLogDatesSet = $inputs.length > 0 && $inputs.filter(function() {
        return ($(this).val() || '').trim().length > 0;
    }).length === $inputs.length;
    var $btn = $('#forecasting_calculate_corrosion_btn');
    if (baseline && allLogDatesSet) {
        $btn.prop('disabled', false).attr('title', '');
    } else {
        $btn.prop('disabled', true).attr('title', 'Set Baseline date and a date for every log, then click Save dates.');
    }
}

/** Save corrosion limits (minimum remaining thickness [mm]). */
function saveForecastingCorrosionLimits() {
    var well_name = $('#select_well').val();
    if (!well_name) return;
    var val = $('#forecasting_min_remaining_thickness').val();
    var minimum_remaining_thickness_mm = (val !== '' && val != null) ? parseFloat(val) : null;
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_corrosion_limits',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, minimum_remaining_thickness_mm: minimum_remaining_thickness_mm }),
        success: function() {
            if (typeof showSuccessMessage === 'function') showSuccessMessage('Corrosion limits saved.');
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error saving corrosion limits.';
            if (typeof showErrorMessage === 'function') showErrorMessage(msg);
        }
    });
}

/** Save log dates and start time. */
function saveForecastingLogDates() {
    var well_name = $('#select_well').val();
    if (!well_name) return;
    var log_dates = {};
    $('#forecasting_log_dates_tbody input[type="date"]').each(function() {
        var name = $(this).attr('data-log-name');
        var val = $(this).val();
        if (name && val) log_dates[name] = val;
    });
    var start_time = $('#forecasting_start_time_input').val() || null;
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_log_dates',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, log_dates: log_dates, start_time: start_time }),
        success: function() {
            if (typeof showSuccessMessage === 'function') showSuccessMessage('Log dates saved.');
            // Corrosion rate is only calculated when user clicks Calculate
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error saving log dates.';
            if (typeof showErrorMessage === 'function') showErrorMessage(msg);
        }
    });
}

/** Load corrosion rate from logs and display in Forecasting panel. */
function loadCorrosionRateForPanel() {
    var well_name = $('#select_well').val();
    var $section = $('#forecasting_corrosion_rate_section');
    var $placeholder = $('#forecasting_corrosion_rate_placeholder');
    var $thead = $('#forecasting_corrosion_rate_thead');
    var $tbody = $('#forecasting_corrosion_rate_tbody');

    if (!well_name) {
        $section.hide();
        $placeholder.show().text('Select a well to view corrosion rate from logs.');
        return;
    }

    $placeholder.show().text('Loading corrosion rate from processed logs...');
    $section.hide();

    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_corrosion_rate_from_logs',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(data) {
            var cr = data.corrosion_rate;
            if (!cr || typeof cr !== 'object') {
                $placeholder.show().text(data.message || 'No corrosion rate data. Process logs for this well to compute corrosion rate.');
                $section.hide();
                return;
            }
            var cols = Object.keys(cr);
            if (cols.length === 0) {
                $placeholder.show().text('No corrosion rate columns.');
                $section.hide();
                return;
            }
            // Ensure Joint No. is the first column
            if (cols.indexOf('Joint No.') > 0) {
                cols = ['Joint No.'].concat(cols.filter(function(c) { return c !== 'Joint No.'; }));
            }
            // Ensure Remaining days to min. thickness is the last column
            var daysCol = 'Remaining days to min. thickness [days]';
            if (cols.indexOf(daysCol) >= 0 && cols.indexOf(daysCol) < cols.length - 1) {
                cols = cols.filter(function(c) { return c !== daysCol; }).concat(daysCol);
            }
            var nRows = Array.isArray(cr[cols[0]]) ? cr[cols[0]].length : 0;
            $thead.empty().append('<tr></tr>');
            cols.forEach(function(col) {
                $thead.find('tr').append($('<th></th>').text(col));
            });
            $tbody.empty();
            for (var r = 0; r < nRows; r++) {
                var $tr = $('<tr></tr>');
                cols.forEach(function(col) {
                    var val = cr[col][r];
                    if (val === null || val === undefined || (typeof val === 'number' && isNaN(val))) {
                        val = '—';
                    } else if (typeof val === 'number') {
                        val = Number(val).toFixed(5);
                    }
                    $tr.append($('<td></td>').text(val));
                });
                $tbody.append($tr);
            }
            $placeholder.hide();
            $section.show();
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error loading corrosion rate.';
            $placeholder.show().text(msg);
            $section.hide();
        }
    });
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
        }
    }
}

function showProcessedLogSection() {
    $('#processed_log_section').show();
}

function hideProcessedLogSection() {
    $('#processed_log_section').hide();
}

function hideSchematicMonitoringSection(clearMonitors = true) {
    $('#schematic_monitoring_section').hide();
    // Only clear monitors if explicitly requested (e.g., when changing wells/schematics)
    if (clearMonitors) {
        clearActiveMonitors();
    }
}

function clearActiveMonitors() {
    activeMonitors = [];
    stopMonitorUpdates();
}

function updateProcessedLogsDropdown(processedLogs) {
    const $select = $('#processed_log_select');
    $select.empty().append('<option value="">Select a processed log...</option>');
    
    if (processedLogs.length > 0) {
        processedLogs.forEach(logName => {
            $select.append(`<option value="${logName}">${logName}</option>`);
        });
        $('#view_processed_log_block').show();
        $('#processed_logs_panel').show();
        showProcessedLogSection();
    } else {
        $('#view_processed_log_block').hide();
        $('#processed_logs_panel').hide();
        hideProcessedLogSection();
        $('#processing_results_container').hide().empty();
    }
}

// Global variable to track unprocessed logs
let unprocessedLogsList = [];

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
            
            if (data.length > 0) {
                let unprocessedLogs = [];
                let processedLogs = [];
                
                data.forEach(log => {
                    const statusBadge = log.processed ? 
                        '<span class="badge badge-success">Processed</span>' : 
                        '<span class="badge badge-secondary">Not Processed</span>';
                    
                    const row = `<tr>
                        <td>${log.name}</td>
                        <td>${statusBadge}</td>
                    </tr>`;
                    tbody.append(row);
                    
                    if (log.processed) {
                        processedLogs.push(log.name);
                    } else {
                        unprocessedLogs.push(log.name);
                    }
                });
                
                unprocessedLogsList = unprocessedLogs;
                updateProcessButtonState();
                // Always use the full list of processed logs from get_log_status (files on disk), not lastProcessedLogsData,
                // which may only contain the last loaded log and would incorrectly limit the dropdown to one option
                updateProcessedLogsDropdown(processedLogs);
            } else {
                tbody.append('<tr><td colspan="2" class="text-muted text-center py-3">No logs found. Upload a .las file below.</td></tr>');
                unprocessedLogsList = [];
                updateProcessButtonState();
                updateProcessedLogsDropdown([]);
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
    const processBtn = $('#process_logs_btn');
    
    if (unprocessedLogsList.length > 0) {
        processBtn.prop('disabled', false).text(`Process Logs (${unprocessedLogsList.length})`);
    } else {
        processBtn.prop('disabled', true).text('Process Logs');
    }
}

function loadProcessedLog(logName) {
    const well_name = $('#select_well').val();
    
    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }
    
    showInfoMessage('Loading processed log data...');
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_processed_logs',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            selected_logs: [logName]
        }),
        success: function (data) {
            showSuccessMessage('Processed log loaded successfully!');
            console.log('Loaded processed log:', data);
            
            // Display the results using the same structure as processing
            if (data.results && data.results.processedLogs) {
                displayProcessingResults(data.results, [logName]);
            } else {
                console.warn('No processed log data in response:', data);
                $('#processing_results_container').html('<div class="alert alert-warning">No processed data available</div>').show();
            }
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Error loading processed log';
            showErrorMessage(errorMsg);
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
    
    if (unprocessedLogsList.length === 0) {
        showErrorMessage('No unprocessed logs to process');
        return;
    }
    
    // Show processing message
    showInfoMessage(`Starting processing of ${unprocessedLogsList.length} caliper logs... This may take a moment.`);
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/process_caliper_logs',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            selected_logs: unprocessedLogsList
        }),
        success: function (data) {
            if (data.task_id) {
                showInfoMessage('Processing started. Please wait...');
                // Poll for results
                pollProcessingResults(data.task_id, unprocessedLogsList);
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
                        displayProcessingResults(data.task_result.results, selectedLogs);
                        // Corrosion rate is only calculated when user clicks Calculate
                    } else {
                        console.warn('No processed logs data in response:', data);
                        $('#processing_results_container').html('<div class="alert alert-warning">No processed data available</div>').show();
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

function displayProcessingResults(results, processedLogs) {
    window.lastProcessedLogsData = results.processedLogs;
    // The new structure: results.processedLogs is a dictionary with log names as keys
    let processedLogsData = results.processedLogs;
    
    console.log('Displaying processing results:', {
        results: results,
        processedLogs: processedLogs,
        processedLogsData: processedLogsData
    });
    
    if (!processedLogsData || typeof processedLogsData !== 'object') {
        console.error('Invalid processed logs data structure:', processedLogsData);
        $('#processing_results_container').html('<div class="alert alert-warning">No valid processed data available</div>').show();
        return;
    }

    // Get the log names from the dictionary keys
    let logNames = Object.keys(processedLogsData);
    
    console.log('Log names found:', logNames);
    
    if (logNames.length === 0) {
        $('#processing_results_container').html('<div class="alert alert-warning">No processed logs found</div>').show();
        return;
    }

    // Set dropdown to the log we're displaying; do not replace options (dropdown is populated by get_log_status)
    const $viewSelect = $('#processed_log_select');
    $viewSelect.val(logNames[0] || '');

    // Function to render the table for a given log name
    function renderProcessedLogTable(logName) {
        let logData = processedLogsData[logName];
        console.log(`Rendering table for log: ${logName}`, logData);
        
        let resultsHtml = '';
        
        if (logData && Array.isArray(logData) && logData.length > 0) {
            // Get columns from the first record
            const columns = Object.keys(logData[0]);
            console.log(`Columns for ${logName}:`, columns);
            
            let tableHtml = '<div class="card processed-log-card">';
            tableHtml += '<div class="card-body">';
            tableHtml += '<div class="table-responsive">';
            tableHtml += '<table class="table table-sm align-middle processed-log-table">';
            tableHtml += '<thead><tr>';
            columns.forEach(col => {
                tableHtml += `<th>${col}</th>`;
            });
            tableHtml += '</tr></thead><tbody>';
            
            logData.forEach(row => {
                tableHtml += '<tr>';
                columns.forEach(col => {
                    let cell = row[col];
                    if (cell === null || cell === undefined || cell === "None") {
                        cell = "";
                    } else if (typeof cell === 'object' && cell !== null) {
                        cell = JSON.stringify(cell);
                    } else if (typeof cell === 'number') {
                        // Format numbers to reasonable precision
                        cell = cell.toFixed(6);
                    }
                    tableHtml += `<td>${cell}</td>`;
                });
                tableHtml += '</tr>';
            });
            tableHtml += '</tbody></table></div></div></div>';
            resultsHtml += tableHtml;
        } else {
            resultsHtml = '<div class="card processed-log-card"><div class="card-body"><div class="alert alert-info">No data available for this log</div></div></div>';
        }
        
        $('#processing_results_container').html(resultsHtml).show();
        setTimeout(syncProcessedLogPanelHeight, 50);
    }

    // Expose so "View processed log" change can render from cache when data is already loaded
    window._renderProcessedLogTable = renderProcessedLogTable;

    // Initial render with the first log
    renderProcessedLogTable(logNames[0]);
}

// =============================================================================
// MONITORING FUNCTIONS
// =============================================================================

function loadPressureElements() {
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    
    if (!well_name || !schematic_filename) {
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_pressure_elements',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function (data) {
            displayPressureElements(data.pressure_elements);
        },
        error: function (xhr) {
            console.error('Error loading pressure elements:', xhr);
            $('#integrity_monitoring_content').html('<div class="alert alert-warning">Error loading pressure elements</div>');
        }
    });
}

function displayPressureElements(elements) {
    const container = $('#integrity_monitoring_content');
    
    if (!elements || elements.length === 0) {
        container.html('<p class="text-muted">No pressure elements found</p>');
        return;
    }
    
    let html = '<div class="table-responsive" style="max-height: 300px; overflow-y: auto;">';
    html += '<table class="table table-sm table-bordered pressure-elements-table">';
    html += '<thead class="table-dark">';
    html += '<tr><th>ID</th><th>Name</th><th>Type</th><th>Sealed</th><th>Depth</th></tr>';
    html += '</thead><tbody>';
    
    elements.forEach(elem => {
        const sealedStatus = elem.sealed !== null ? (elem.sealed ? 'Yes' : 'No') : 'N/A';
        const depth = elem.depth !== null ? elem.depth : 'N/A';
        
        html += `<tr>
            <td>${elem.id}</td>
            <td>${elem.name}</td>
            <td>${elem.type}</td>
            <td>${sealedStatus}</td>
            <td>${depth}</td>
        </tr>`;
    });
    
    html += '</tbody></table></div>';
    container.html(html);
}

function loadAnnulusReadings() {
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    
    if (!well_name || !schematic_filename) {
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_annulus_readings',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function (data) {
            displayAnnulusReadings(data.annulus_data);
        },
        error: function (xhr) {
            console.error('Error loading annulus data:', xhr);
            $('#annulus_monitoring_content').html('<div class="alert alert-warning">Error loading annulus data</div>');
        }
    });
}

function displayAnnulusReadings(annuluses) {
    const container = $('#annulus_monitoring_content');
    
    if (!annuluses || annuluses.length === 0) {
        container.html('<p class="text-muted">No annulus data available</p>');
        return;
    }
    
    let html = '<div class="mb-2">';
    
    // Add configuration section
    html += `<div class="card mb-3" style="background: #2a2d47; border: 1px solid #444;">
        <div class="card-header" style="background: #32355a; border-bottom: 1px solid #444; padding: 8px 12px;">
            <h6 class="mb-0" style="font-size: 0.85em;">Configure Monitoring</h6>
        </div>
        <div class="card-body" style="padding: 12px;">
            <div class="row">
                <div class="col-md-6">
                    <label style="font-size: 0.8em; margin-bottom: 4px;">Select Annulus:</label>
                    <select id="annulus_select" class="form-control form-control-sm">
                        <option value="">Select annulus...</option>`;
    
    annuluses.forEach(annulus => {
        html += `<option value="${annulus.annulus_id}">Annulus ${annulus.annulus_id}</option>`;
    });
    
    html += `</select>
                </div>
                <div class="col-md-6">
                    <label style="font-size: 0.8em; margin-bottom: 4px;">Select Tag:</label>
                    <select id="tag_select" class="form-control form-control-sm" disabled>
                        <option value="">Select tag...</option>
                    </select>
                </div>
            </div>
            <div class="row mt-2">
                <div class="col-md-4">
                    <label style="font-size: 0.8em; margin-bottom: 4px;">Min Value:</label>
                    <input type="number" id="min_value" class="form-control form-control-sm" step="0.1" disabled>
                </div>
                <div class="col-md-4">
                    <label style="font-size: 0.8em; margin-bottom: 4px;">Max Value:</label>
                    <input type="number" id="max_value" class="form-control form-control-sm" step="0.1" disabled>
                </div>
                <div class="col-md-4">
                    <label style="font-size: 0.8em; margin-bottom: 4px;">&nbsp;</label>
                    <button id="add_monitoring" class="btn btn-success btn-sm form-control" disabled>Add Monitor</button>
                </div>
            </div>
        </div>
    </div>`;
    
    // Add monitoring display section
    html += '<div id="active_monitors"></div>';
    
    html += '</div>';
    container.html(html);
    
    // Store annulus data globally for reference
    window.annulusData = annuluses;
    
    // Set up event handlers
    setupAnnulusMonitoringHandlers();
}

// Global variable to store active monitors
let activeMonitors = [];

// WIMS card: annulus monitors (annuli selected for monitoring from API)
let wimsAnnulusMonitors = [];
// Cached annulus list from last generate_schematic_image response (single POST returns image + annulus info)
let wimsCachedAnnulusData = [];
// Cached drawn items from schematic (element_name, element_type, patch_type) for "From schematic" element picker
let wimsCachedDrawnItems = [];
// Cached schematic JSON used for WIMS panel (so we can re-call generate with item_colors for recoloring)
let wimsCachedSchematicData = null;

function setupAnnulusMonitoringHandlers() {
    // Annulus selection handler
    $('#annulus_select').off('change').on('change', function() {
        const selectedAnnulusId = $(this).val();
        const tagSelect = $('#tag_select');
        
        if (selectedAnnulusId) {
            // Load measured tags from the unit
            loadMeasuredTags();
        } else {
            tagSelect.empty().append('<option value="">Select tag...</option>').prop('disabled', true);
            $('#min_value, #max_value').prop('disabled', true);
            $('#add_monitoring').prop('disabled', true);
        }
    });
    
    // Tag selection handler
    $('#tag_select').off('change').on('change', function() {
        const selectedTag = $(this).val();
        if (selectedTag) {
            $('#min_value, #max_value').prop('disabled', false);
            $('#add_monitoring').prop('disabled', false);
            // Get tag data when tag is selected
            getTagData(selectedTag);
        } else {
            $('#min_value, #max_value').prop('disabled', true);
            $('#add_monitoring').prop('disabled', true);
        }
    });
    
    // Add monitoring handler
    $('#add_monitoring').off('click').on('click', function() {
        const annulusId = $('#annulus_select').val();
        const tagValue = $('#tag_select').val();
        const tagText = $('#tag_select option:selected').text();
        const tagUnit = $('#tag_select option:selected').data('unit') || '';
        const minValue = parseFloat($('#min_value').val());
        const maxValue = parseFloat($('#max_value').val());
        
        if (annulusId && tagValue && !isNaN(minValue) && !isNaN(maxValue)) {
            if (minValue >= maxValue) {
                showErrorMessage('Min value must be less than max value');
                return;
            }
            
            // Check if this monitor already exists
            const existingMonitor = activeMonitors.find(m => m.annulusId === annulusId && m.tagValue === tagValue);
            if (existingMonitor) {
                showErrorMessage('This monitor already exists');
                return;
            }
            
            // Use real tag data if available, otherwise null
            const currentValue = window.currentTagData && window.currentTagData.current_value !== null 
                ? window.currentTagData.current_value 
                : null; // No artificial value if data not available
            
            const monitor = {
                annulusId: annulusId,
                tagValue: tagValue,
                tagText: tagText,
                tagUnit: tagUnit,
                minValue: minValue,
                maxValue: maxValue,
                currentValue: currentValue,
                tagName: tagValue // Store the actual tag name for data retrieval
            };
            
            activeMonitors.push(monitor);
            displayActiveMonitors();
            
            // Start periodic updates if this is the first monitor
            if (activeMonitors.length === 1) {
                startMonitorUpdates();
            }
            
            // Auto-save monitors
            autoSaveMonitors();
            
            // Clear form
            $('#min_value, #max_value').val('');
            showSuccessMessage('Monitor added successfully');
        } else {
            showErrorMessage('Please fill in all fields');
        }
    });
}

function loadMeasuredTags() {
    const well_name = $('#select_well').val();
    
    if (!well_name) {
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_measured_tags',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name
        }),
        success: function (data) {
            const tagSelect = $('#tag_select');
            tagSelect.empty().append('<option value="">Select tag...</option>');
            
            if (data.measured_tags && data.measured_tags.length > 0) {
                data.measured_tags.forEach(tag => {
                    const label = tag.description || tag.tag_name;
                    const unitText = tag.unit ? ` (${tag.unit})` : '';
                    tagSelect.append(`<option value="${tag.tag_name}" data-unit="${tag.unit}" data-description="${tag.description}">${label}${unitText}</option>`);
                });
                tagSelect.prop('disabled', false);
            } else {
                tagSelect.append('<option value="">No measured tags found</option>');
                tagSelect.prop('disabled', true);
            }
        },
        error: function (xhr) {
            console.error('Error loading measured tags:', xhr);
            showErrorMessage('Error loading measured tags');
        }
    });
}

function getTagData(tagName) {
    const well_name = $('#select_well').val();
    
    if (!well_name || !tagName) {
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_tag_data',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            tag_name: tagName
        }),
        success: function (data) {
            if (data.tag_data && data.tag_data.current_value !== null) {
                const currentValue = data.tag_data.current_value;
                console.log(`Tag ${tagName} current value: ${currentValue} ${data.tag_data.unit}`);
                // Store the current tag data for monitoring
                window.currentTagData = data.tag_data;
            } else {
                console.log(`Tag ${tagName} has no current value`);
                window.currentTagData = null;
            }
        },
        error: function (xhr) {
            console.error('Error getting tag data:', xhr);
            showErrorMessage('Error getting tag data');
        }
    });
}



function displayActiveMonitors() {
    const container = $('#active_monitors');
    
    if (activeMonitors.length === 0) {
        container.html('<p class="text-muted" style="font-size: 0.8em;">No active monitors</p>');
        return;
    }
    
    let html = '<div class="mb-2">';
    
    activeMonitors.forEach((monitor, index) => {
        const status = getReadingStatus(monitor);
        const statusColor = getStatusColor(status);
        const statusIcon = getStatusIcon(status);
        
        const valueDisplay = monitor.currentValue !== null 
            ? `${monitor.currentValue.toFixed(2)} ${monitor.tagUnit}`
            : `No Data ${monitor.tagUnit}`;
            
        html += `<div class="monitoring-reading d-flex justify-content-between align-items-center mb-2">
            <div>
                <div class="font-weight-bold" style="font-size: 0.9em;">Annulus ${monitor.annulusId}</div>
                <div class="text-muted" style="font-size: 0.8em;">${monitor.tagText}</div>
            </div>
            <div class="text-right">
                <div class="d-flex align-items-center">
                    <span class="mr-2" style="font-size: 0.9em;">${valueDisplay}</span>
                    <span class="status-indicator" style="background-color: ${statusColor};">
                        ${statusIcon}
                    </span>
                    <button class="btn btn-sm btn-danger ml-2" onclick="removeMonitor(${index})" style="padding: 2px 6px; font-size: 0.7em;">×</button>
                </div>
                <div class="text-muted" style="font-size: 0.7em;">
                    ${monitor.minValue} - ${monitor.maxValue} ${monitor.tagUnit}
                </div>
            </div>
        </div>`;
    });
    
    html += '</div>';
    container.html(html);
}

function removeMonitor(index) {
    activeMonitors.splice(index, 1);
    displayActiveMonitors();

    // Stop periodic updates if no monitors remain
    if (activeMonitors.length === 0) {
        stopMonitorUpdates();
    }

    // Auto-save monitors
    autoSaveMonitors();

    showSuccessMessage('Monitor removed');
}

function formatGaugeLabel(val) {
    if (val == null || isNaN(val)) return '--';
    if (Math.floor(val) === val) return String(val);
    if (Math.abs(val) >= 100 || Math.abs(val) < 0.01) return val.toFixed(1);
    return val.toFixed(2);
}

function wimsAnnulusLatterLabel(m) {
    var latter = m.label || '';
    var id = m.annulus_id || '';
    if (id && latter) {
        var prefix = id + ' - ';
        var prefix2 = id + ' – ';
        if (latter.indexOf(prefix) === 0) latter = latter.substring(prefix.length);
        else if (latter.indexOf(prefix2) === 0) latter = latter.substring(prefix2.length);
    }
    return latter ? 'Annulus – ' + latter : 'Annulus – ' + id;
}

function displayWimsAnnulusMonitors() {
    var container = $('#wims_annulus_monitors_list');
    var esc = function(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; };
    if (wimsAnnulusMonitors.length === 0) {
        container.html('<p class="text-muted mb-0 small">No annulus monitors. Click Add monitor to select an annulus from the schematic.</p>');
        return;
    }
    var html = '';
    wimsAnnulusMonitors.forEach(function(m, index) {
        var displayLetter = esc(m.annulus_id || '');
        var configured = m.tagName && m.minValue != null && m.maxValue != null && !isNaN(m.minValue) && !isNaN(m.maxValue);
        var minVal = configured ? parseFloat(m.minValue) : 0;
        var maxVal = configured ? parseFloat(m.maxValue) : 1;
        var currentVal = m.currentValue != null ? parseFloat(m.currentValue) : null;
        var range = maxVal - minVal;
        var pct = range && currentVal != null ? Math.max(0, Math.min(1, (currentVal - minVal) / range)) : 0.5;
        var needleAngle = -90 + pct * 180;
        var gradId = 'wimsGaugeGrad_' + index;
        var valueNum = currentVal != null ? esc(currentVal.toFixed(2)) : '--';
        var valueUnit = m.tagUnit ? esc(m.tagUnit) : '';
        var minLabel = esc(formatGaugeLabel(minVal));
        var maxLabel = esc(formatGaugeLabel(maxVal));

        html += '<div class="wims-monitor-item">';
        html += '<div class="wims-gauge-wrap" data-index="' + index + '">';
        html += '<div class="wims-gauge-label">' + displayLetter + '</div>';
        if (configured) {
            html += '<div class="wims-gauge-semi-wrap">';
            html += '<svg viewBox="0 0 100 68" xmlns="http://www.w3.org/2000/svg">';
            html += '<defs><linearGradient id="' + gradId + '" x1="0%" y1="0%" x2="100%" y2="0%">';
            html += '<stop offset="0%" stop-color="#28a745"/><stop offset="33%" stop-color="#ffc107"/>';
            html += '<stop offset="66%" stop-color="#fd7e14"/><stop offset="100%" stop-color="#dc3545"/>';
            html += '</linearGradient></defs>';
            html += '<path d="M 8 54 A 42 42 0 0 1 92 54" fill="none" stroke="url(#' + gradId + ')" stroke-width="8" stroke-linecap="round"/>';
            html += '<line x1="50" y1="54" x2="50" y2="14" stroke="#1a1a1a" stroke-width="2" stroke-linecap="round" transform="rotate(' + needleAngle + ' 50 54)"/>';
            html += '<circle cx="50" cy="54" r="4" fill="#333"/>';
            html += '<text x="50" y="40" font-size="10" font-weight="600" fill="#eee" text-anchor="middle">' + valueNum + '</text>';
            if (valueUnit) html += '<text x="50" y="50" font-size="5" fill="#aaa" text-anchor="middle">' + valueUnit + '</text>';
            html += '<text x="12" y="64" font-size="7" fill="#28a745" font-weight="600">' + minLabel + '</text>';
            html += '<text x="88" y="64" font-size="7" fill="#dc3545" font-weight="600" text-anchor="end">' + maxLabel + '</text>';
            html += '</svg>';
            html += '</div>';
        } else {
            html += '<div class="wims-gauge-placeholder-circle">?</div>';
            html += '<div class="wims-gauge-placeholder">Click to configure</div>';
        }
        html += '</div>';
        html += '</div>';
    });
    container.html(html);
    container.find('.wims-gauge-wrap').on('click', function(e) {
        var idx = parseInt($(this).data('index'), 10);
        openWimsGaugeConfig(idx);
    });
}

function removeWimsAnnulusMonitor(index) {
    wimsAnnulusMonitors.splice(index, 1);
    displayWimsAnnulusMonitors();
}

var wimsGaugeConfigIndex = -1;

function openWimsGaugeConfig(index) {
    wimsGaugeConfigIndex = index;
    $('#wims_configure_gauge_modal').addClass('show');
    $('#wims_gauge_error').hide();
    var m = wimsAnnulusMonitors[index] || {};
    $('#wims_gauge_min').val(m.minValue != null ? m.minValue : '');
    $('#wims_gauge_max').val(m.maxValue != null ? m.maxValue : '');
    var well_name = $('#select_well').val();
    $('#wims_gauge_tag_select').empty().append('<option value="">Select tag...</option>');
    if (!well_name) {
        $('#wims_gauge_tag_select').append('<option value="">Select a well first</option>');
        return;
    }
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_measured_tags',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function(data) {
            var $sel = $('#wims_gauge_tag_select');
            $sel.empty().append('<option value="">Select tag...</option>');
            if (data.measured_tags && data.measured_tags.length > 0) {
                data.measured_tags.forEach(function(tag) {
                    var label = tag.description || tag.tag_name;
                    var unitText = tag.unit ? ' (' + tag.unit + ')' : '';
                    $sel.append($('<option></option>').attr('value', tag.tag_name).attr('data-unit', tag.unit || '').attr('data-description', tag.description || '').text(label + unitText));
                });
                if (m.tagName) $sel.val(m.tagName);
            }
        },
        error: function() {
            $('#wims_gauge_tag_select').append('<option value="">Error loading tags</option>');
        }
    });
}

function saveWimsGaugeConfig() {
    var idx = wimsGaugeConfigIndex;
    if (idx < 0 || idx >= wimsAnnulusMonitors.length) return;
    var tagVal = $('#wims_gauge_tag_select').val();
    var tagOpt = $('#wims_gauge_tag_select option:selected');
    var minVal = parseFloat($('#wims_gauge_min').val());
    var maxVal = parseFloat($('#wims_gauge_max').val());
    if (!tagVal) {
        $('#wims_gauge_error').text('Select a tag.').show();
        return;
    }
    if (isNaN(minVal) || isNaN(maxVal) || minVal >= maxVal) {
        $('#wims_gauge_error').text('Enter valid min and max (min < max).').show();
        return;
    }
    var m = wimsAnnulusMonitors[idx];
    m.tagName = tagVal;
    m.tagText = tagOpt.text();
    m.tagUnit = tagOpt.data('unit') || '';
    m.minValue = minVal;
    m.maxValue = maxVal;
    m.currentValue = null;
    $('#wims_configure_gauge_modal').removeClass('show');
    displayWimsAnnulusMonitors();
    fetchWimsGaugeTagData(idx);
    startWimsGaugeRefresh();
}

function fetchWimsGaugeTagData(index) {
    var m = wimsAnnulusMonitors[index];
    if (!m || !m.tagName) return;
    var well_name = $('#select_well').val();
    if (!well_name) return;
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/get_tag_data',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name, tag_name: m.tagName }),
        success: function(data) {
            if (data.tag_data && data.tag_data.current_value != null) {
                m.currentValue = data.tag_data.current_value;
                displayWimsAnnulusMonitors();
            }
        }
    });
}

var wimsGaugeRefreshInterval;

function startWimsGaugeRefresh() {
    if (wimsGaugeRefreshInterval) clearInterval(wimsGaugeRefreshInterval);
    wimsGaugeRefreshInterval = setInterval(function() {
        var well_name = $('#select_well').val();
        if (!well_name) return;
        wimsAnnulusMonitors.forEach(function(m, idx) {
            if (m.tagName) fetchWimsGaugeTagData(idx);
        });
    }, 10000);
}

// Make functions globally accessible
window.removeMonitor = removeMonitor;
window.saveMonitors = saveMonitors;
window.loadSavedMonitors = loadSavedMonitors;

// Function to update monitor values (get real data from application)
function updateMonitorValues() {
    if (activeMonitors.length > 0) {
        const well_name = $('#select_well').val();
        if (!well_name) return;
        
        // Update each monitor with real tag data
        let updatesInProgress = 0;
        let hasChanges = false;
        
        activeMonitors.forEach((monitor, index) => {
            updatesInProgress++;
            
            $.ajax({
                type: 'POST',
                url: '/app/wellintegrity/get_tag_data',
                contentType: 'application/json',
                data: JSON.stringify({
                    selected_well: well_name,
                    tag_name: monitor.tagName
                }),
                success: function (data) {
                    console.log(data)
                    updatesInProgress--;
                    
                    const oldValue = monitor.currentValue;
                    
                    if (data.tag_data && data.tag_data.current_value !== null) {
                        monitor.currentValue = data.tag_data.current_value;
                        
                        // Check for changes - need to handle null values
                        if (oldValue !== null && Math.abs(oldValue - monitor.currentValue) > 0.01) {
                            hasChanges = true;
                        } else if (oldValue === null && monitor.currentValue !== null) {
                            hasChanges = true;
                        }
                    } else {
                        monitor.currentValue = null;
                        
                        // Check if value changed from non-null to null
                        if (oldValue !== null) {
                            hasChanges = true;
                        }
                    }
                    
                    // If all updates are complete and there are changes, refresh display
                    if (updatesInProgress === 0 && hasChanges) {
                        displayActiveMonitors();
                    }
                },
                error: function (xhr) {
                    updatesInProgress--;
                    console.error(`Error updating monitor ${monitor.tagName}:`, xhr);
                    
                    // If all updates are complete (even with errors), check if we need to refresh
                    if (updatesInProgress === 0 && hasChanges) {
                        displayActiveMonitors();
                    }
                }
            });
        });
    }
}

// Start periodic updates when monitors are active
let monitorUpdateInterval;

function startMonitorUpdates() {
    if (monitorUpdateInterval) {
        clearInterval(monitorUpdateInterval);
    }
    monitorUpdateInterval = setInterval(updateMonitorValues, 5000); // Update every 5 seconds
}

function stopMonitorUpdates() {
    if (monitorUpdateInterval) {
        clearInterval(monitorUpdateInterval);
        monitorUpdateInterval = null;
    }
}

function getReadingStatus(monitor) {
    if (monitor.currentValue === null) {
        return 'no_data';
    } else if (monitor.currentValue < monitor.minValue) {
        return 'low';
    } else if (monitor.currentValue > monitor.maxValue) {
        return 'high';
    } else {
        return 'normal';
    }
}

function getStatusColor(status) {
    switch(status) {
        case 'low': return '#dc3545'; // Red
        case 'high': return '#dc3545'; // Red
        case 'normal': return '#28a745'; // Green
        case 'no_data': return '#6c757d'; // Gray
        default: return '#6c757d'; // Gray
    }
}

function getStatusIcon(status) {
    switch(status) {
        case 'low': return '↓';
        case 'high': return '↑';
        case 'normal': return '●';
        case 'no_data': return '?';
        default: return '?';
    }
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

// =============================================================================
// MONITOR SAVE/LOAD FUNCTIONS
// =============================================================================

function saveMonitors() {
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    
    if (!well_name || !schematic_filename) {
        showErrorMessage('Please select a well and schematic first');
        return;
    }
    
    if (activeMonitors.length === 0) {
        showErrorMessage('No monitors to save');
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_monitors',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename,
            monitors: activeMonitors
        }),
        success: function (data) {
            showSuccessMessage('Monitors saved successfully!');
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Error saving monitors';
            showErrorMessage(errorMsg);
        }
    });
}

function loadSavedMonitors() {
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    
    if (!well_name || !schematic_filename) {
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/load_monitors',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function (data) {
            if (data.monitors && data.monitors.length > 0) {
                activeMonitors = data.monitors;
                displayActiveMonitors();
                
                // Start periodic updates if monitors were loaded
                if (activeMonitors.length > 0) {
                    startMonitorUpdates();
                }
                
                showSuccessMessage(`Loaded ${data.monitors.length} saved monitors`);
            }
        },
        error: function (xhr) {
            console.error('Error loading saved monitors:', xhr);
            // Don't show error message as this is called automatically
        }
    });
}

function autoSaveMonitors() {
    // Automatically save monitors without showing messages
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    
    if (!well_name || !schematic_filename) {
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_monitors',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename,
            monitors: activeMonitors
        }),
        success: function (data) {
            // Silent save - no message
        },
        error: function (xhr) {
            console.error('Error auto-saving monitors:', xhr);
        }
    });
}

// Event handlers
$(document).ready(function() {
    $('#upload_log_btn').on('click', uploadLog);
    $('#process_logs_btn').on('click', processCaliperLogs);

    // Drag and drop for log upload
    const dropzone = $('#dropzone');
    const fileInput = $('#log_upload');
    const dropzoneText = $('#dropzone-text');

    // Highlight dropzone on dragover
    dropzone.on('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropzone.addClass('dragover');
    });
    dropzone.on('dragleave dragend', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropzone.removeClass('dragover');
    });
    dropzone.on('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropzone.removeClass('dragover');
        const files = e.originalEvent.dataTransfer.files;
        if (files && files.length > 0) {
            fileInput[0].files = files;
            dropzoneText.text(files[0].name);
        }
    });
    // Click dropzone to open file dialog
    dropzone.on('click', function() {
        fileInput.trigger('click');
    });
    // Show file name when selected via dialog
    fileInput.on('change', function() {
        if (fileInput[0].files && fileInput[0].files.length > 0) {
            dropzoneText.text(fileInput[0].files[0].name);
        } else {
            dropzoneText.text('Drag & drop .las file or click to browse');
        }
    });

    // When Well Logs card grows (e.g. more logs), match Processed Logs panel height
    $(window).on('resize', function() {
        syncProcessedLogPanelHeight();
    });

    // Add barrier element: open modal – populate drawn items only (no redraw here)
    $('#wims_add_element_btn').off('click').on('click', function() {
        var list = wimsCachedDrawnItems || [];
        var seen = {};
        var unique = [];
        list.forEach(function(item) {
            var name = (item.element_name || item.name || item.id || '').trim();
            var typeVal = (item.element_type || '').trim();
            var key = name + '|' + typeVal;
            if (name && !seen[key]) {
                seen[key] = true;
                unique.push({ element_name: name, element_type: typeVal });
            }
        });
        var $sel = $('#wims_add_element_from_schematic');
        $sel.empty().append('<option value="">— Select from schematic —</option>');
        unique.forEach(function(item) {
            var label = item.element_type ? (item.element_name + ' | ' + item.element_type) : item.element_name;
            $sel.append($('<option></option>').attr('value', item.element_name).attr('data-element-type', item.element_type || '').text(label));
        });
        var useSchematic = unique.length > 0;
        $('#wims_add_element_source_schematic').prop('checked', useSchematic);
        $('#wims_add_element_source_custom').prop('checked', !useSchematic);
        $('#wims_add_element_schematic_wrap').toggle(useSchematic);
        $('#wims_add_element_custom_wrap').toggle(!useSchematic);
        $('#wims_add_element').val('');
        $('#wims_add_element_modal').addClass('show');
    });

    // Add barrier element: toggle Between "From schematic" and "Custom"
    $('input[name="wims_add_element_source"]').off('change').on('change', function() {
        var isSchematic = $('#wims_add_element_source_schematic').is(':checked');
        $('#wims_add_element_schematic_wrap').toggle(isSchematic);
        $('#wims_add_element_custom_wrap').toggle(!isSchematic);
        if (!isSchematic) $('#wims_add_element_from_schematic').val('');
        else $('#wims_add_element').val('');
    });

    // Add barrier element: close modal
    $('#wims_add_element_cancel_btn').off('click').on('click', function() {
        $('#wims_add_element_modal').removeClass('show');
    });
    $('#wims_add_element_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
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
        $('#wims_edit_risk_rf').val($tds.eq(4).text().trim());
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

        $('#wims_edit_element').val(element);
        $('#wims_edit_qualification').val(qualification);
        $('#wims_edit_monitoring').val(monitoring);
        $('#wims_edit_status').val(status);
        $('#wims_edit_remarks').val(remarks);
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
        var element = $('#wims_edit_element').val().trim();
        var qualification = $('#wims_edit_qualification').val().trim();
        var monitoring = $('#wims_edit_monitoring').val().trim();
        var status = $('#wims_edit_status').val();
        var remarks = $('#wims_edit_remarks').val().trim();
        if (!element) {
            $('#wims_edit_element_modal').removeClass('show');
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
        updateWimsOverallStatusFromBarriers();
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
        $('#wims_edit_element_modal').removeClass('show');
    });

    // Add barrier element: submit – element from schematic dropdown or custom input
    $('#wims_add_element_submit_btn').off('click').on('click', function() {
        const tableType = $('#wims_add_table_type').val();
        const fromSchematic = $('#wims_add_element_source_schematic').is(':checked');
        var elementName = fromSchematic
            ? ($('#wims_add_element_from_schematic').val() || '').trim()
            : ($('#wims_add_element').val() || '').trim();
        var elementType = fromSchematic ? ($('#wims_add_element_from_schematic option:selected').attr('data-element-type') || '').trim() : '';
        const element = fromSchematic && elementName && elementType
            ? (elementName + ' | ' + elementType)
            : elementName;
        const qualification = $('#wims_add_qualification').val().trim();
        const monitoring = $('#wims_add_monitoring').val().trim();
        const status = $('#wims_add_status').val();
        const remarks = $('#wims_add_remarks').val().trim();

        if (!element) {
            return;
        }

        const tbodyId = tableType === 'primary' ? 'wims_primary_barrier_tbody' : 'wims_secondary_barrier_tbody';
        const $tbody = $('#' + tbodyId);

        // Remove placeholder row if present
        const $placeholder = $tbody.find('tr td[colspan="5"]');
        if ($placeholder.length) {
            $placeholder.closest('tr').remove();
        }

        const statusDotClass = (status === 'failed' || status === 'not-verified' || status === 'verified') ? status : 'verified';
        const statusDot = '<span class="wims-integrity-dot ' + statusDotClass + '" title="' + escapeHtml($('#wims_add_status option:selected').text()) + '"></span>';
        const remarkCell = remarks ? escapeHtml(remarks) : '';
        const row = '<tr class="wims-barrier-data-row"><td>' + escapeHtml(element) + '</td><td>' + escapeHtml(qualification) + '</td><td>' + escapeHtml(monitoring) + '</td><td>' + statusDot + '</td><td>' + remarkCell + '</td></tr>';
        $tbody.append(row);

        $('#wims_add_element').val('');
        $('#wims_add_element_from_schematic').val('');
        $('#wims_add_qualification').val('');
        $('#wims_add_monitoring').val('');
        $('#wims_add_status').val('verified');
        $('#wims_add_remarks').val('');
        $('#wims_add_element_modal').removeClass('show');

        refreshWimsSchematicFromBarriers();
        updateWimsOverallStatusFromBarriers();
    });

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Save WIMS panel button
    $('#wims_save_panel_btn').off('click').on('click', function() {
        saveWimsPanel();
    });

    // Forecasting panel: save log dates
    $('#forecasting_save_log_dates_btn').off('click').on('click', function() {
        saveForecastingLogDates();
    });

    $('#forecasting_save_corrosion_limits_btn').off('click').on('click', function() {
        saveForecastingCorrosionLimits();
    });

    // Forecasting panel: calculate corrosion rate (only when Baseline + log dates set)
    $('#forecasting_calculate_corrosion_btn').off('click').on('click', function() {
        if ($(this).prop('disabled')) return;
        loadCorrosionRateForPanel();
    });
    $(document).on('change input', '#forecasting_start_time_input, #forecasting_log_dates_tbody input[type="date"]', function() {
        updateForecastingCalculateButtonState();
    });

    // Add annulus monitor: open modal; use only cached annulus data from generate_schematic_image response (single POST)
    $('#wims_add_monitor_btn').off('click').on('click', function() {
        const well_name = $('#select_well').val();
        const schematic_filename = $('#saved_schematics_select').val();
        if (!well_name || !schematic_filename) {
            showErrorMessage('Please select a well and a schematic first.');
            return;
        }
        $('#wims_add_monitor_modal').addClass('show');
        $('#wims_add_monitor_error').hide();
        var list = wimsCachedAnnulusData || [];
        var $select = $('#wims_add_monitor_annulus');

        function annulusItemId(item) {
            return item.designation || item.annulus_id || item.id || item.annulusId || '';
        }
        function annulusItemLabel(item) {
            if (item.label) return item.label;
            if (item.designation != null && (item.outer_tubular != null || item.inner_tubular != null)) {
                var parts = [item.designation];
                if (item.outer_tubular || item.inner_tubular) {
                    parts.push((item.outer_tubular || '') + ' / ' + (item.inner_tubular || ''));
                }
                return parts.join(' – ');
            }
            if (item.outer_unit && item.inner_unit) return item.outer_unit + ' / ' + item.inner_unit;
            if (item.outer_unit) return item.outer_unit;
            return annulusItemId(item);
        }
        function populateAnnulusDropdown(list) {
            $select.empty().append('<option value="">Select annulus...</option>');
            (list || []).forEach(function(item) {
                var id = annulusItemId(item);
                var label = annulusItemLabel(item);
                if (id) {
                    $select.append($('<option></option>').attr('value', id).text(label || id));
                }
            });
            if ((list || []).length === 0) {
                $('#wims_add_monitor_error').text('No annuli in response. Select a schematic to load image and annulus info.').show();
            }
        }

        populateAnnulusDropdown(list);
    });

    $('#wims_add_monitor_cancel_btn').off('click').on('click', function() {
        $('#wims_add_monitor_modal').removeClass('show');
    });
    $('#wims_add_monitor_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
    });

    $('#wims_gauge_cancel_btn').off('click').on('click', function() {
        $('#wims_configure_gauge_modal').removeClass('show');
    });
    $('#wims_configure_gauge_modal').off('click').on('click', function(e) {
        if (e.target === this) {
            $(this).removeClass('show');
        }
    });
    $('#wims_gauge_save_btn').off('click').on('click', function() {
        saveWimsGaugeConfig();
    });
    $('#wims_gauge_delete_btn').off('click').on('click', function() {
        var idx = wimsGaugeConfigIndex;
        if (idx >= 0 && idx < wimsAnnulusMonitors.length) {
            removeWimsAnnulusMonitor(idx);
            $('#wims_configure_gauge_modal').removeClass('show');
        }
    });

    $('#wims_add_monitor_submit_btn').off('click').on('click', function() {
        const annulusId = $('#wims_add_monitor_annulus').val();
        const annulusText = $('#wims_add_monitor_annulus option:selected').text();
        if (!annulusId) {
            return;
        }
        if (wimsAnnulusMonitors.find(function(m) { return m.annulus_id === annulusId; })) {
            showErrorMessage('This annulus is already being monitored.');
            return;
        }
        wimsAnnulusMonitors.push({ annulus_id: annulusId, label: annulusText });
        displayWimsAnnulusMonitors();
        $('#wims_add_monitor_modal').removeClass('show');
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

function buildWimsPanelData() {
    const statusClass = computeWimsOverallStatusFromBarriers();
    const primary = [];
    $('#wims_primary_barrier_tbody tr').each(function() {
        const $tr = $(this);
        if ($tr.find('td[colspan="5"]').length) return;
        const $tds = $tr.find('td');
        if ($tds.length < 5) return;
        const $statusSpan = $tds.eq(3).find('.wims-integrity-dot');
        let status = 'verified';
        if ($statusSpan.hasClass('failed')) status = 'failed';
        else if ($statusSpan.hasClass('not-verified')) status = 'not-verified';
        const remarksCell = $tds.eq(4)[0];
        const hasRemarkDot = $(remarksCell).find('.wims-barrier-remark-dot').length > 0;
        primary.push({
            element: $tds.eq(0).text().trim(),
            qualification: $tds.eq(1).text().trim(),
            monitoring: $tds.eq(2).text().trim(),
            status: status,
            remarks: hasRemarkDot ? '' : $(remarksCell).text().trim()
        });
    });
    const secondary = [];
    $('#wims_secondary_barrier_tbody tr').each(function() {
        const $tr = $(this);
        if ($tr.find('td[colspan="5"]').length) return;
        const $tds = $tr.find('td');
        if ($tds.length < 5) return;
        const $statusSpan = $tds.eq(3).find('.wims-integrity-dot');
        let status = 'verified';
        if ($statusSpan.hasClass('failed')) status = 'failed';
        else if ($statusSpan.hasClass('not-verified')) status = 'not-verified';
        const remarksCell = $tds.eq(4)[0];
        const hasRemarkDot = $(remarksCell).find('.wims-barrier-remark-dot').length > 0;
        secondary.push({
            element: $tds.eq(0).text().trim(),
            qualification: $tds.eq(1).text().trim(),
            monitoring: $tds.eq(2).text().trim(),
            status: status,
            remarks: hasRemarkDot ? '' : $(remarksCell).text().trim()
        });
    });
    var annulus_monitors = wimsAnnulusMonitors.map(function(m) {
        return {
            annulus_id: m.annulus_id,
            label: m.label,
            tagName: m.tagName || null,
            tagText: m.tagText || null,
            tagUnit: m.tagUnit || null,
            minValue: m.minValue != null ? m.minValue : null,
            maxValue: m.maxValue != null ? m.maxValue : null
        };
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
    return '<tr class="wims-barrier-data-row"><td>' + esc(item.element) + '</td><td>' + esc(item.qualification) + '</td><td>' + esc(item.monitoring) + '</td><td>' + statusDot + '</td><td>' + remarkCell + '</td></tr>';
}

/** Build item_colors array from barrier tables (primary #0d6efd, secondary red). Returns [] when no barriers or no cache. */
function buildItemColorsFromBarriers() {
    var list = wimsCachedDrawnItems || [];
    var tableElementPairs = {};
    $('#wims_primary_barrier_tbody tr.wims-barrier-data-row').each(function() {
        var cellText = $(this).find('td').eq(0).text().trim();
        if (cellText.indexOf(' | ') !== -1) {
            var parts = cellText.split(' | ');
            var name = parts[0].trim();
            var typeVal = parts.slice(1).join(' | ').trim();
            if (name && typeVal !== undefined) tableElementPairs[name + '|' + typeVal] = 'primary';
        }
    });
    $('#wims_secondary_barrier_tbody tr.wims-barrier-data-row').each(function() {
        var cellText = $(this).find('td').eq(0).text().trim();
        if (cellText.indexOf(' | ') !== -1) {
            var parts = cellText.split(' | ');
            var name = parts[0].trim();
            var typeVal = parts.slice(1).join(' | ').trim();
            if (name && typeVal !== undefined) tableElementPairs[name + '|' + typeVal] = 'secondary';
        }
    });
    var itemColors = [];
    list.forEach(function(item) {
        var name = (item.element_name || item.name || item.id || '').trim();
        var typeVal = (item.element_type || '').trim();
        var pt = (item.patch_type || '').trim();
        var tableType = tableElementPairs[name + '|' + typeVal];
        if (!name || !pt || !tableType) return;
        if (typeVal === 'Valve' && pt.indexOf('valve_ellipse') === -1) return;
        itemColors.push({
            element_name: name,
            element_type: typeVal,
            patch_type: pt,
            color: tableType === 'primary' ? '#0d6efd' : 'red'
        });
    });
    return itemColors;
}

/** Redraw WIMS schematic image with barrier colors (one generate call). */
function refreshWimsSchematicFromBarriers() {
    if (!wimsCachedSchematicData) return;
    var itemColors = buildItemColorsFromBarriers();
    var payload = Object.assign({}, wimsCachedSchematicData);
    if (itemColors.length) payload.item_colors = itemColors;
    else delete payload.item_colors;
    var $wimsOutput = $('#wims_schematic_image_output');
    $wimsOutput.html('<span style="color:#888">Updating schematic...</span>');
    $.ajax({
        url: '/app/wellintegrity/generate_schematic_image',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(payload),
        success: function(response) {
            if (response.image_base64) {
                $wimsOutput.html(
                    '<img src="data:image/png;base64,' + response.image_base64 + '" style="max-width:100%; height:auto; display:block;" />'
                );
            } else if (response.error) {
                $wimsOutput.html('<span class="text-danger">' + response.error + '</span>');
            }
        },
        error: function(xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error updating schematic.';
            $wimsOutput.html('<span class="text-danger">' + msg + '</span>');
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
        wimsAnnulusMonitors = data.annulus_monitors.map(function(m) {
            return {
                annulus_id: m.annulus_id,
                label: m.label || '',
                tagName: m.tagName || null,
                tagText: m.tagText || null,
                tagUnit: m.tagUnit || null,
                minValue: m.minValue != null ? m.minValue : null,
                maxValue: m.maxValue != null ? m.maxValue : null,
                currentValue: null
            };
        });
        displayWimsAnnulusMonitors();
        if (wimsAnnulusMonitors.some(function(m) { return m.tagName; })) {
            startWimsGaugeRefresh();
        }
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

function saveWimsPanel() {
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    if (!well_name || !schematic_filename) {
        showErrorMessage('Please select a well and a schematic first.');
        return;
    }
    const panelData = buildWimsPanelData();
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    panelData.last_update_date = yyyy + '-' + mm + '-' + dd;
    $('#wims_last_update_date').val(panelData.last_update_date);
    $.ajax({
        type: 'POST',
        url: '/app/wellintegrity/save_wims_panel',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename,
            panel_data: panelData
        }),
        success: function() {
            showSuccessMessage('WIMS panel saved successfully.');
        },
        error: function(xhr) {
            const msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : 'Error saving WIMS panel.';
            showErrorMessage(msg);
        }
    });
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
