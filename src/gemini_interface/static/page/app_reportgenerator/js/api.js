document.addEventListener('DOMContentLoaded', () => {
    load_plant();
});


toggleButton.addEventListener('click', () => {
    const isVisible = advancedSection.style.display === 'block';
    advancedSection.style.display = isVisible ? 'none' : 'block';
});


function load_plant() {
    const fieldID = $('#select_project').val();
    console.log('Selected field:', fieldID);

    $.ajax({
        type: 'POST',
        url: '/app/reportgenerator/load_plant',
        contentType: 'application/json',
        dataType: 'json',
        data: JSON.stringify({field_name: fieldID}),

        success: function (response) {
            // 2xx responses
            console.log('load_plant SUCCESS:', response);

            if (response.message) {
                console.log('Message:', response.message);
            }
        },

        error: function (xhr, status, error) {
            // Non-2xx responses
            console.error('load_plant ERROR');
            console.error('HTTP status:', xhr.status);
            console.error('Status text:', xhr.statusText);

            // Try to parse JSON error body
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
        }
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

    console.log(inputs);
    return inputs;
}



function generate_report() {
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
        ESP_Q_Pow_date_crossplot: document.getElementById("ESP_Q-Pow-date_checkbox").checked,
        ESP_freq_I_date_crossplot: document.getElementById("ESP_freq-I-date_checkbox").checked,
        esp_plots_options: esp_plots_options,
        // User comments
        inj_report_comments: document.getElementById("InjReportComments").value,
        prod_report_comments: document.getElementById("ProdReportComments").value,
        esp_report_comments: document.getElementById("ESPReportComments").value,
    };

    console.log("INPUTS:", inputs);

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
    var inputs = {
        ProjectName: document.getElementById("select_project").value,
        NlogPeriod: document.getElementById("nlog_period").value,
        LicenseHolder: document.getElementById("nlog_license_holder").value
    };

    $.ajax({
        type: 'POST',
        url: '/app/reportgenerator/generate_nlog_report',
        contentType: 'application/json',
        data: JSON.stringify(inputs),
        xhrFields: { responseType: 'blob' },

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

            var blob = new Blob([data], { type: contentType });
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
}
