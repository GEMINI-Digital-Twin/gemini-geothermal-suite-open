load_plant()

function load_plant() {

    var fieldID = $('#select_project').val();


    $.ajax({
        type: 'POST',
        url: '/app/esp/load_plant',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {

            get_esp_list()

        }
    })
}

function get_esp_list() {

    $.ajax({
        type: 'POST',
        url: '/app/esp/get_esp_list',
        contentType: 'application/json',
        data: JSON.stringify(),
        success: function (data) {

            var select = document.getElementById('select_esp');
            select.options.length = 1;

            for (var i = 0; i < data.length; i++) {
                select.options[select.options.length] = new Option(data[i], data[i]);
            }


        }
    })
}

$('#select_esp').on('change', function () {
    get_esp_parameters()
})

function get_esp_parameters() {

    var esp_name = $('#select_esp').val();

    $.ajax({
        type: 'POST',
        url: '/app/esp/get_esp_parameters',
        contentType: 'application/json',
        data: JSON.stringify({esp_name: esp_name }),
        success: function (data) {
            document.getElementById("esp_type").value = data.esp_par.property.esp_type.slice(-1)[0]
            document.getElementById("esp_type").dispatchEvent(new Event('change'))

            document.getElementById("esp_no_stage").value = data.esp_par.property.esp_no_stage.slice(-1)[0]
            document.getElementById("esp_correction_factor").value = data.esp_par.property.esp_correction_factor.slice(-1)[0]
        }
    })

}

function refresh_plot(){
    var esp_name = $('#select_esp').val();
    if (esp_name == '') {
        alert('Please select esp first')
        return
    }
    calculate_pump_curve()
}

function calculate_pump_curve() {
    range_time = document.getElementById("datetime").value
    range_time = range_time.split(" - ");
    start_time = range_time[0]
    end_time = range_time[1]

    boundary = {
        'start_time' : start_time,
        'end_time' : end_time,
        'min_frequency' : parseFloat(document.getElementById("min_frequency").value),
        'max_frequency' : parseFloat(document.getElementById("max_frequency").value)
    }

    parameters = {
        'esp_name': $('#select_esp').val()
    }

    $.ajax({
        type: 'POST',
        url: '/app/esp/calculate_pump_curve',
        contentType: 'application/json',
        data: JSON.stringify({ parameters: parameters, boundary: boundary}),
        success: function (data) {
            myProgress_pumpcurve = setInterval(function () { get_results_pump_curve(data) }, 500);
        }
    })
}

function get_results_pump_curve(task_id) {
    $.ajax({
        type: 'POST',
        url: '/app/esp/get_results_pump_curve',
        contentType: 'application/json',
        data: JSON.stringify({ task_id: task_id }),
        success: function (data) {
            task_status = data.task_status
            if (task_status == "SUCCESS") {
                clearInterval(myProgress_pumpcurve)
                plot_pump_curve(data.task_result)
                plotComparisonCurves(data.task_result)
                plot_flow_frequency(data.task_result)
            }
        },
        error: function () {
            clearInterval(myProgress_pumpcurve)
        }
    })
    
}

function fetchComparisonData(task_id) {
    fetch("/app/esp/get_results_pump_curve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: task_id })
    })
    .then(res => res.json())
    .then(data => {
        if (data.task_status === "SUCCESS") {
            plotComparisonCurves(data.task_result);
        } else {
            setTimeout(() => fetchComparisonData(task_id), 1000);
        }
    });
}

function plot_pump_curve(data) {

    var layout = {
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: { color: "#D2D2D5" },
        xaxis: {
            title: { text: 'Flow Rate (m3/h)' }
        },
        yaxis: {
            title: { text: 'Pump Head (m)' },
            range: [0, Math.max(...[].concat(...data.pump_head)) * 10.1972 * 1.1],
            autorange: false
        },
        legend: {
            title: {
                text: 'Theoretical Frequency',
                font: { size: 12, color: '#D2D2D5' }
            },
            orientation: 'h',
            x: 0.5,
            xanchor: 'center',
            y: 1.15,
            yanchor: 'bottom',
            font: { size: 12, color: '#D2D2D5' },
            bgcolor: 'rgba(39, 41, 61, 0.8)',
            bordercolor: '#444',
            borderwidth: 1
        }

    };

    var traces = [];

    for (var i = 0; i < data.frequency.length; i++) {
        var freq = data.frequency[i];
        var flow = data.xValues[i];
        var head = data.pump_head[i].map(h => h * 10.1972);

        var trace_curve = {
            x: flow,
            y: head,
            mode: 'lines',
            name: `${freq} Hz`,
            line: { width: 2 }
        };
        traces.push(trace_curve);
    }

    var realTimeDates = data.realTime_time.map(t => new Date(t));
    function formatDate(date) {
        var options = { day: 'numeric', month: 'short', year: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }

    var numTicks = 5;
    var stepSize = Math.max(1, Math.floor(realTimeDates.length / (numTicks - 1)));
    var tickDates = [];
    for (var i = 0; i < numTicks; i++) {
        tickDates.push(realTimeDates[Math.min(i * stepSize, realTimeDates.length - 1)]);
    }
    var tickvals = tickDates.map(date => date.getTime());
    var ticktext = tickDates.map(date => formatDate(date));
    
    let a = 1, b = 0;

    const correctionInput = document.getElementById("esp_correction_factor");
    if (correctionInput && correctionInput.value.includes(';')) {
        [a, b] = correctionInput.value.split(';').map(Number);
    }

    var head_corrected = data.esp_vlp_head_calculated.map(h => (a * h + b) * 10.1972);

    var trace_real_time = {
        x: data.realTime_flow,
        y: head_corrected,
        mode: 'markers',
        marker: {
            color: realTimeDates.map(date => date.getTime()),
            colorscale: 'Jet',
            colorbar: {
                title: 'Real Time Data',
                tickvals: tickvals,
                ticktext: ticktext,
                tickmode: 'array',
                tickfont: { size: 10 }
            },
            size: 8
        },
        text: realTimeDates.map(date => formatDate(date)),
        hoverinfo: 'text',
        showlegend: false
    };
    traces.push(trace_real_time);

    Plotly.newPlot('plot_pump_curve', traces, layout);
}

function plot_flow_frequency(data) {
    var plotDiv = document.getElementById('plot_flow_frequency');
    if (!plotDiv) {
        return;
    }

    const time = (data.realTime_time || []).map(t => new Date(t));
    const realTime_flow = data.realTime_flow || [];
    const frequency_measured = data.frequency_measured || [];

    if (time.length === 0 || (realTime_flow.length === 0 && frequency_measured.length === 0)) {
        plotDiv.innerHTML = '<div class="alert alert-warning">No flow or frequency data available.</div>';
        return;
    }

    var traces = [];

    if (realTime_flow.length > 0) {
        traces.push({
            x: time,
            y: realTime_flow,
            mode: 'lines+markers',
            name: 'Measured Flow',
            line: { color: '#1f77b4', width: 1.5 },
            marker: { color: '#1f77b4', size: 4 },
            yaxis: 'y'
        });
    }

    if (frequency_measured.length > 0) {
        traces.push({
            x: time,
            y: frequency_measured,
            mode: 'lines+markers',
            name: 'Measured Frequency',
            line: { color: '#ff7f0e', width: 1.5 },
            marker: { color: '#ff7f0e', size: 4 },
            yaxis: 'y2'
        });
    }

    var layout = {
        title: 'Flow and Frequency vs Time',
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: { color: "#D2D2D5" },
        xaxis: {
            title: 'Time',
            plot_bgcolor: "#27293D",
            paper_bgcolor: "#27293D",
            font: { color: "#D2D2D5" }
        },
        yaxis: {
            title: {
                text: 'Flow Rate (m³/h)',
                font: { color: "#1f77b4" }
            },
            side: 'left',
            plot_bgcolor: "#27293D",
            paper_bgcolor: "#27293D",
            tickfont: { color: "#1f77b4" }
        },
        yaxis2: {
            title: {
                text: 'Frequency (Hz)',
                font: { color: '#ff7f0e' }
            },
            overlaying: 'y',
            side: 'right',
            showgrid: false,
            tickfont: { color: '#ff7f0e' }
        },
        showlegend: false,
        margin: { r: 80 },
        autosize: true,
        hovermode: 'x unified'
    };

    Plotly.newPlot(plotDiv, traces, layout, { responsive: true }).then(function() {
        Plotly.Plots.resize(plotDiv);
    });
}

function plotComparisonCurves(data) {

    let a = 1, b = 0;

    const correctionInput = document.getElementById("esp_correction_factor");
    if (correctionInput && correctionInput.value.includes(';')) {
        [a, b] = correctionInput.value.split(';').map(Number);
    }

    let a_cal = null, b_cal = null;

    const calibratedInput = document.getElementById("esp_correction_factor_calibrated");
    if (calibratedInput && calibratedInput.value.includes(';')) {
        [a_cal, b_cal] = calibratedInput.value.split(';').map(Number);
    }

    const time = (data.realTime_time || []).map(t => new Date(t));
    const esp_vlp_head_calculated = data.esp_vlp_head_calculated || [];
    const esp_theoretical_head_calculated = data.esp_theoretical_head_calculated || [];
    const esp_vlp_outlet_pressure_calculated = data.esp_vlp_outlet_pressure_calculated || [];
    const esp_theoretical_outlet_pressure_calculated = data.esp_theoretical_outlet_pressure_calculated || [];
    const inlet_pressure_measured = data.inlet_pressure_measured || [];
    const esp_vlp_ipr_inlet_pressure_calculated = data.esp_vlp_ipr_inlet_pressure_calculated || [];

    const head_corrected = esp_vlp_head_calculated.map(h => h !== null ? (a * h + b) : null);

    const head_calibrated = a_cal !== null && b_cal !== null
    ? esp_vlp_head_calculated.map(h => h !== null ? (a_cal * h + b_cal) : null)
    : null;


    const subplots = [
        {
            y: esp_vlp_head_calculated,
            y2: esp_theoretical_head_calculated,
            y3: head_corrected,
            y4: head_calibrated,
            traces: [
                { label: 'Calculated VLP Head', color: '#1f77b4' },
                { label: 'Calculated Theoretical Head', color: '#ff7f0e' },
                { label: `Initial Calibrated Head (${a.toFixed(2)}x + ${b.toFixed(2)})`, color: '#2ca02c', dash: 'dash' },
                a_cal !== null && b_cal !== null ? {
                    label: `New Calibrated Head (${a_cal.toFixed(2)}x + ${b_cal.toFixed(2)})`,
                    color: '#9467bd',
                    dash: 'dash'
                } : null
            ].filter(t => t !== null),
            title: 'Head vs Time'
        },

        {

            y: esp_vlp_outlet_pressure_calculated,
            y2: esp_theoretical_outlet_pressure_calculated,
            traces: [
                { label: 'Calculated VLP Outlet Pressure', color: '#1f77b4' },
                { label: 'Calculated Theoretical Outlet Pressure', color: '#ff7f0e' }
            ],
            title: 'Outlet Pressure vs Time'
        },
        {
            y: inlet_pressure_measured,
            y2: esp_vlp_ipr_inlet_pressure_calculated,
            traces: [
                { label: 'Measured Inlet Pressure', color: '#1f77b4' },
                { label: 'Calculated IPR Inlet Pressure', color: '#ff7f0e' }
            ],
            title: 'Inlet Pressure vs Time'
        }
    ];

    const layout = {
        grid: { rows: subplots.length, columns: 1, pattern: 'independent' },
        height: subplots.length * 320,
        margin: { t: 80, b: 80, r: 250 },
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: { color: "#D2D2D5" },
        showlegend: false,
        annotations: [],
        autosize: true
    };

    const yAxisTitles = [
        'Head (m)',
        'Outlet Pressure (bar)',
        'Inlet Pressure (bar)'
    ];

    const traces = [];

    subplots.forEach((plot, i) => {
        const xaxis = `x${i + 1}`;
        const yaxis = `y${i + 1}`;
        
        if (plot.useDualAxis && plot.y2) {
            traces.push({
                x: time,
                y: plot.y,
                mode: 'lines',
                name: plot.traces[0].label,
                xaxis: xaxis,
                yaxis: yaxis,
                line: { color: plot.traces[0].color }
            });
            
            const yaxisRight = `y${i + 1}2`;
            traces.push({
                x: time,
                y: plot.y2,
                mode: 'lines',
                name: plot.traces[1].label,
                xaxis: xaxis,
                yaxis: yaxisRight,
                line: { color: plot.traces[1].color }
            });
        } else {
            traces.push({
                x: time,
                y: plot.y,
                mode: 'lines',
                name: plot.traces[0].label,
                xaxis: xaxis,
                yaxis: yaxis,
                line: { color: plot.traces[0].color }
            });

            if (plot.y2 && plot.traces[1]) {
                traces.push({
                    x: time,
                    y: plot.y2,
                    mode: 'lines',
                    name: plot.traces[1].label,
                    xaxis: xaxis,
                    yaxis: yaxis,
                    line: { color: plot.traces[1].color }
                });
            }

            if (plot.y3 && plot.traces[2]) {
                traces.push({
                    x: time,
                    y: plot.y3,
                    mode: 'lines',
                    name: plot.traces[2].label,
                    xaxis: xaxis,
                    yaxis: yaxis,
                    line: {
                        color: plot.traces[2].color,
                        dash: plot.traces[2].dash || 'solid'
                    }
                });
            }

            if (plot.y4 && plot.traces[3]) {
                traces.push({
                    x: time,
                    y: plot.y4,
                    mode: 'lines',
                    name: plot.traces[3].label,
                    xaxis: xaxis,
                    yaxis: yaxis,
                    line: {
                        color: plot.traces[3].color,
                        dash: plot.traces[3].dash || 'solid'
                    }
                });
            }
        }


        const annotationX = 1.02;
        const yStart = 1;
        const yStep = 0.1;

        plot.traces.forEach((trace, j) => {
            layout.annotations.push({
                xref: `${xaxis} domain`,
                yref: `${yaxis} domain`,
                x: annotationX,
                y: yStart - j * yStep,
                xanchor: 'left',
                yanchor: 'top',
                text: trace.label,
                font: { color: trace.color, size: 12 },
                showarrow: false
            });
        });

        layout.annotations.push({
            xref: 'paper',
            yref: 'paper',
            x: 0.5,
            y: 1 - (i / subplots.length) - 0.035,
            xanchor: 'center',
            yanchor: 'bottom',
            text: `<b>${plot.title}</b>`,
            font: { size: 16, color: '#D2D2D5' },
            showarrow: false
        });

        const xLayoutKey = `xaxis${i + 1}`;
        const yLayoutKey = `yaxis${i + 1}`;

        layout[xLayoutKey] = layout[xLayoutKey] || {};
        layout[yLayoutKey] = layout[yLayoutKey] || {};

        if (plot.useDualAxis && plot.y2) {
            layout[yLayoutKey].title = {
                text: 'Flow (m³/h)',
                font: { size: 14, color: '#D2D2D5' }
            };
            layout[yLayoutKey].side = 'left';
            
            const yaxisRightKey = `yaxis${i + 1}2`;
            layout[yaxisRightKey] = {
                title: {
                    text: 'Frequency (Hz)',
                    font: { size: 14, color: '#D2D2D5' }
                },
                side: 'right',
                overlaying: `y${i + 1}`,
                showgrid: false
            };
        } else {
            layout[yLayoutKey].title = {
                text: yAxisTitles[i],
                font: { size: 14, color: '#D2D2D5' }
            };
        }

        if (i === subplots.length - 1) {
            layout[xLayoutKey].title = { text: 'Time' };
            layout[xLayoutKey].showticklabels = true;
        } else {
            layout[xLayoutKey].title = { text: '' };
            layout[xLayoutKey].showticklabels = false;
        }
    });

    Plotly.newPlot('plot_comparison', traces, layout);
}

function calibrate_esp_factor() {
    range_time_cal = document.getElementById("datetimecalibration").value
    range_time_cal = range_time_cal.split(" - ");
    start_time_cal = range_time_cal[0]
    end_time_cal = range_time_cal[1]
    
    boundary = {
        'calibration_start_time': start_time_cal,
        'calibration_end_time': end_time_cal
    };

    parameters = {
        'esp_name': $('#select_esp').val()
    };

    $.ajax({
        type: 'POST',
        url: '/app/esp/calibrate_esp_factor',
        contentType: 'application/json',
        data: JSON.stringify({ parameters: parameters, boundary: boundary }),
        success: function (data) {
            myProgress_calibration = setInterval(function () {
                get_results_calibration_factor(data)
            }, 500);
        }
    });
}

function get_results_calibration_factor(task_id) {
    $.ajax({
        type: 'POST',
        url: '/app/esp/get_results_calibration_factor',
        contentType: 'application/json',
        data: JSON.stringify({ task_id: task_id }),
        success: function (data) {
            task_status = data.task_status;
            if (task_status === "SUCCESS") {
                clearInterval(myProgress_calibration);
                let a = 1, b = 0;
                if (data.task_result.esp_correction_factor && data.task_result.esp_correction_factor.length > 0) {
                    [a, b] = data.task_result.esp_correction_factor;
                }
                document.getElementById("esp_correction_factor_calibrated").value = `${a.toFixed(2)}; ${b.toFixed(2)}`;

                calculate_pump_curve()
            }
        },
        error: function () {
            clearInterval(myProgress_calibration);
        }
    });
}

function updateCorrectionFactors() {
    var esp_name = $('#select_esp').val();
    var field_name = $('#select_project').val();
    var esp_correction_factor = $('#esp_correction_factor_calibrated').val();

    if (!esp_name || !field_name || !esp_correction_factor.includes(';')) {
        alert('Invalid input.');
        return;
    }

    $.ajax({
        type: 'POST',
        url: '/esp/update_correction_factors',
        contentType: 'application/json',
        data: JSON.stringify({
            esp_name: esp_name,
            field_name: field_name,
            esp_correction_factor: esp_correction_factor
        }),
        success: function (data) {
            alert(data.message);
        },
        error: function (xhr) {
            const error = JSON.parse(xhr.responseText);
            alert("Error: " + error.message);
        }
    });
}

$('#datetime').on('change', function () {
    document.getElementById("datetimecalibration").value = document.getElementById("datetime").value
})


$(document).ready(function() {
    $('.tab-links a').on('click', function(e) {
        var currentAttrValue = $(this).attr('href');
        
        $('.tab-content').removeClass('active');
        
        $(currentAttrValue).addClass('active');
        
        $('.tab-links li').removeClass('active');
        $(this).parent('li').addClass('active');
        
        setTimeout(function() {
            if (currentAttrValue === '#calibration') {
                var plotDiv = document.getElementById('plot_comparison');
                if (plotDiv && plotDiv.data) {
                    Plotly.Plots.resize('plot_comparison');
                }
            }
            if (currentAttrValue === '#monitoring') {
                var plotDiv = document.getElementById('plot_pump_curve');
                if (plotDiv && plotDiv.data) {
                    Plotly.Plots.resize('plot_pump_curve');
                }
            }
        }, 100);
        
        e.preventDefault();
    });

    $('input[name="datetime"]').daterangepicker({
        timePicker: true,
        singleDatePicker: false,
        showDropdowns: true,
        timePicker24Hour: true,
        timePickerSeconds: false,
        startDate: moment().startOf('day').subtract(7, 'days'),
        endDate: moment().startOf('hour'),
        locale: {
            format: 'YYYY-MM-DD HH:mm:ss'
        }
    });
    
    $('input[name="datetimecalibration"]').daterangepicker({
        timePicker: true,
        singleDatePicker: false,
        showDropdowns: true,
        timePicker24Hour: true,
        timePickerSeconds: false,
        startDate: moment().startOf('day').subtract(7, 'days'),
        endDate: moment().startOf('hour'),
        locale: {
            format: 'YYYY-MM-DD HH:mm:ss'
        }
    });
    
});
