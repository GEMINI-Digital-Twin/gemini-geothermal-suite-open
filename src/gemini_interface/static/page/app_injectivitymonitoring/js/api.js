load_plant()

function load_plant() {

    var fieldID = $('#select_project').val();


    $.ajax({
        type: 'POST',
        url: '/app/injectionwellmonitoring/load_plant',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {

            get_well_list()

        }
    })
}

function get_well_list() {

    $.ajax({
        type: 'POST',
        url: '/app/injectionwellmonitoring/get_well_list',
        contentType: 'application/json',
        data: JSON.stringify(),
        success: function (data) {

            var select = document.getElementById('select_well');
            select.options.length = 1;

            for (var i = 0; i < data.length; i++) {
                select.options[select.options.length] = new Option(data[i], data[i]);
            }

        }
    })

}

function get_parameters() {

    var well_name = $('#select_well').val();

    $.ajax({
        type: 'POST',
        url: '/app/injectionwellmonitoring/get_parameters',
        contentType: 'application/json',
        data: JSON.stringify({ well_name: well_name }),
        success: function (data) {
            document.getElementById("reservoir_pressure").value = data.res_par.property.reservoir_pressure.slice(-1)[0]
            document.getElementById("reservoir_permeability").value = data.res_par.property.reservoir_permeability.slice(-1)[0]
            document.getElementById("reservoir_thickness").value = data.res_par.property.reservoir_thickness.slice(-1)[0]
            document.getElementById("liquid_density").value = data.res_par.property.liquid_density.slice(-1)[0]
            document.getElementById("liquid_viscosity").value = data.res_par.property.liquid_viscosity.slice(-1)[0]
        }
    })

}

$('#select_well').on('change', function () {
    get_parameters()
})

function calculate() {
    var well_name = $('#select_well').val();
    if (well_name == '') {
        alert('Please select well first')
        return
    }

    calculate_hall_integral_derivative()
    calculate_skin_lines()
}

function calculate_hall_integral_derivative() {
    
    boundary = {
        'start_time' : document.getElementById("starttime").value,
        'end_time' : document.getElementById("endtime").value,
        'reservoir_pressure' : parseFloat(document.getElementById("reservoir_pressure").value),
    }

    parameters = {
        'reservoir_pressure' : parseFloat(document.getElementById("reservoir_pressure").value),
        'reservoir_radius' : parseFloat(document.getElementById("reservoir_radius").value),
        'reservoir_permeability' : parseFloat(document.getElementById("reservoir_permeability").value),
        'reservoir_thickness' : parseFloat(document.getElementById("reservoir_thickness").value),
        'reservoir_top' : parseFloat(document.getElementById("reservoir_top").value),
        'liquid_density' : parseFloat(document.getElementById("liquid_density").value),
        'liquid_viscosity' : parseFloat(document.getElementById("liquid_viscosity").value),
    }

    $.ajax({
        type: 'POST',
        url: '/app/injectionwellmonitoring/calculate_hall_integral',
        contentType: 'application/json',
        data: JSON.stringify({ parameters: parameters, boundary: boundary }),
        success: function (data) {
            myProgress_hall = setInterval(function () { get_results_hall_integral(data) }, 500);

        },
        error: function (xhr) {
            alert("data is not available is selected time range")
        }
    })
}

function get_results_hall_integral(task_id) {
    $.ajax({
        type: 'POST',
        url: '/app/injectionwellmonitoring/get_results_hall_integral',
        contentType: 'application/json',
        data: JSON.stringify({ task_id: task_id }),
        success: function (data) {
            task_status = data.task_status
            if (task_status == "SUCCESS") {
                clearInterval(myProgress_hall)
                plot_hall_integral_hall_integral_derivative(data.task_result)
            }
        },
        error: function (xhr) {
            clearInterval(myProgress_hall)
        }
    })
}

function plot_hall_integral_hall_integral_derivative(data) {
    var layout = {
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: {
            color: "#D2D2D5"

        },
        xaxis: {
            title: {
                text: 'Cummulative Flow Rate (m3)',
            },
        },
        yaxis: {
            title: {
                text: 'Hall integral (bar.h), Hall derivative',
            },
        },
    }

    var layout_loglog = {
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: {
            color: "#D2D2D5"

        },
        xaxis: {
            type: 'log',
            title: {
                text: 'Cummulative Flow Rate (m3)',
            },
        },
        yaxis: {
            type: 'log',
            title: {
                text: 'Hall integral (bar.h), Hall derivative',
            },
        },
    }

    trace_hall_integral = {
        x: data.cumulative_flow,
        y: data.hall_integral,
        name: "Hall integral",
    }
    trace_hall_derivative = {
        x: data.cumulative_flow,
        y: data.hall_derivative_numerical,
        name: "Hall derivative",
    }

    Plotly.newPlot('plotHall', [trace_hall_integral, trace_hall_derivative], layout)
    Plotly.newPlot('plotHall_loglog', [trace_hall_integral, trace_hall_derivative], layout_loglog)


}


function calculate_skin_lines() {
    boundary = {
        'min_flow_plot' : parseFloat(document.getElementById("min_flow_plot").value),
        'max_flow_plot' : parseFloat(document.getElementById("max_flow_plot").value),
        'no_interval_flow_plot' : parseFloat(document.getElementById("no_interval_flow_plot").value),
        'min_skin_plot' : parseFloat(document.getElementById("min_skin_plot").value),
        'max_skin_plot' : parseFloat(document.getElementById("max_skin_plot").value),
        'no_interval_skin_plot' : parseFloat(document.getElementById("no_interval_skin_plot").value),
        'max_pressure' : parseFloat(document.getElementById("max_pressure").value),
        'max_flow_rate' : parseFloat(document.getElementById("max_flow_rate").value),
        'wellbore_radius' : parseFloat(document.getElementById("wellbore_radius").value),
        'start_time' : document.getElementById("starttime").value,
        'end_time' : document.getElementById("endtime").value
    }

    parameters = {
        'reservoir_pressure' : parseFloat(document.getElementById("reservoir_pressure").value),
        'reservoir_radius' : parseFloat(document.getElementById("reservoir_radius").value),
        'reservoir_permeability' : parseFloat(document.getElementById("reservoir_permeability").value),
        'reservoir_thickness' : parseFloat(document.getElementById("reservoir_thickness").value),
        'reservoir_top' : parseFloat(document.getElementById("reservoir_top").value),
        'liquid_density' : parseFloat(document.getElementById("liquid_density").value),
        'liquid_viscosity' : parseFloat(document.getElementById("liquid_viscosity").value),
    }

    $.ajax({
        type: 'POST',
        url: '/app/injectionwellmonitoring/calculate_skin_lines',
        contentType: 'application/json',
        data: JSON.stringify({ parameters: parameters, boundary: boundary}),
        success: function (data) {
            myProgress_skin = setInterval(function () { get_results_skin_lines(data) }, 500);
        }
    })
}

function get_results_skin_lines(task_id) {
    $.ajax({
        type: 'POST',
        url: '/app/injectionwellmonitoring/get_results_skin_lines',
        contentType: 'application/json',
        data: JSON.stringify({ task_id: task_id }),
        success: function (data) {
            task_status = data.task_status
            if (task_status == "SUCCESS") {
                clearInterval(myProgress_skin)
                plot_skin_lines(data.task_result)
                
            }
        },
        error: function (xhr) {
            clearInterval(myProgress_skin)
        }
    })
    
}

function plot_skin_lines(data) {

    var layout = {
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: {
            color: "#D2D2D5"

        },
        xaxis: {
            title: {
                text: 'Flow Rate (m3/h)',
            },
        },
        yaxis: {
            title: {
                text: 'Injection Pressure (bar)',
            },
        }
    }

    var traces = [];

    // Function to format dates
    var realTimeDates = data.realTime_time.map(t => new Date(t));

    function formatDate(date) {
        var options = { day: 'numeric', month: 'short', year: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }

    // Real-time scatter plot trace
    var numTicks = 5;
    var realTimeDatesLength = realTimeDates.length;
    var stepSize = Math.max(1, Math.floor(realTimeDatesLength / (numTicks - 1)));
    var tickDates = [];
    for (var i = 0; i < numTicks; i++) {
        tickDates.push(realTimeDates[Math.min(i * stepSize, realTimeDatesLength - 1)]);
    }
    var tickvals = tickDates.map(date => date.getTime());
    var ticktext = tickDates.map(date => formatDate(date));
    var trace_real_time = {
        x: data.realTime_flow,
        y: data.realTime_pressure,
        mode: 'markers',
        marker: {
            color: realTimeDates.map(date => date.getTime()),
            colorscale: 'Jet',
            colorbar: {
                title: 'Real Time Data',
                tickvals: tickvals,
                ticktext: ticktext,
                tickmode: 'array',
                tickformat: '%d %B %Y',
                tickfont: {
                    size: 10
                }
            }
        },
        text: realTimeDates.map(date => formatDate(date)), // Add formatted date as hover text
        hoverinfo: 'text', // Display hover text
        name: 'Real Time Data', // Use a descriptive name for the trace
        showlegend: false
    };
    traces.push(trace_real_time);

    // Skin lines
    data.skin_array.forEach((skin, idx) => {
        var trace_skin = {
            x: data.flow_array,
            y: data.injection_pressure[idx],
            mode: 'lines',
            line: {
                dash: 'dot',
                color: 'dimgray'
            },
            name: `Skin = ${skin}`,
            showlegend: false
        };
        traces.push(trace_skin);
    });

    // Create annotation for each skin
    var annotations = [];
    data.skin_array.forEach((skin, idx) => {
        var lastFlow = data.flow_array[data.flow_array.length - 1];
        var lastPressure = data.injection_pressure[idx][data.injection_pressure[idx].length - 1];

        var annotation_skin = {
            x: lastFlow,
            y: lastPressure,
            xref: 'x',
            yref: 'y',
            text: `Skin = ${skin}`,
            showarrow: false,
            font: {
                color: 'white',
                size: 10
            }
        };
        annotations.push(annotation_skin);
    });
    layout.annotations = annotations;

    // Max flow rate line
    var trace_max_flow = {
        x: [data.max_flow_rate, data.max_flow_rate],
        y: [0, data.max_cal_P_inj + 10],
        mode: 'lines',
        line: {
            dash: 'dash',
            color: '#F47B10'
        },
        name: `Max Q = ${data.max_flow_rate} m3/h`,
        showlegend: false
    };
    traces.push(trace_max_flow);

    // Max flow rate line --> annotation
    var max_flow_rate_value = data.max_flow_rate.toFixed(0);
    var annotation_max_flow = {
        x: data.max_flow_rate - 7,
        y: data.max_cal_P_inj - 100,
        xref: 'x',
        yref: 'y',
        text: `Max Q = ${max_flow_rate_value} m3/h`,
        showarrow: false,
        font: {
            color: '#F47B10',
            size: 10
        },
        align: 'center',
        xanchor: 'left',
        yanchor: 'bottom',
        textangle: 270
    };
    layout.annotations = layout.annotations || [];
    layout.annotations.push(annotation_max_flow);

    // Max pressure line
    var trace_max_pressure = {
        x: [data.min_flow_plot, data.max_flow_plot + 10],
        y: [data.max_pressure, data.max_pressure],
        mode: 'lines',
        line: {
            dash: 'dashdot',
            color: '#F47B10'
        },
        name: `Max P = ${data.max_pressure} bar`,
        showlegend: false
    };
    traces.push(trace_max_pressure);

    // Max pressure line --> annotation
    var max_pressure_value = data.max_pressure.toFixed(0);
    var annotation_max_pressure = {
        x: data.min_flow_plot + 2,
        y: data.max_pressure + 2,
        xref: 'x',
        yref: 'y',
        text: `Max P = ${max_pressure_value} bar`,
        showarrow: false,
        font: {
            color: '#F47B10',
            size: 10
        },
        align: 'center',
        xanchor: 'left',
        yanchor: 'bottom'
    };
    layout.annotations = layout.annotations || [];
    layout.annotations.push(annotation_max_pressure);

    // Plot the data
    Plotly.newPlot('plotSkin', traces, layout);

}
