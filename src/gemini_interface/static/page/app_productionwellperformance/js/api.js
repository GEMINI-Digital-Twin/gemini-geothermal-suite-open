load_plant()

function load_plant() {

    var fieldID = $('#select_project').val();


    $.ajax({
        type: 'POST',
        url: '/app/productionwellperformance/load_plant',
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
        url: '/app/productionwellperformance/get_well_list',
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

BPD_to_m3h = 0.00662

function get_parameters() {

    var well_name = $('#select_well').val();

    $.ajax({
        type: 'POST',
        url: '/app/productionwellperformance/get_parameters',
        contentType: 'application/json',
        data: JSON.stringify({ well_name: well_name }),
        success: function (data) {

            document.getElementById("reservoir_pressure").value = data.res_par.property.reservoir_pressure.slice(-1)[0]
            document.getElementById("liquid_density").value = data.res_par.property.liquid_density.slice(-1)[0]
            document.getElementById("liquid_viscosity").value = data.res_par.property.liquid_viscosity.slice(-1)[0]

            document.getElementById("productivity_index").value = data.well_par.property.productionwell_productivity_index.slice(-1)[0]
            document.getElementById("soil_temperature").value = data.well_par.property.productionwell_soil_temperature.slice(-1)[0]
            document.getElementById("friction_correlation").value = data.well_par.property.productionwell_friction_correlation.slice(-1)[0]

            document.getElementById("esp_type").value = data.esp_par.property.esp_type.slice(-1)[0]

            document.getElementById("esp_no_stage").value = data.esp_par.property.esp_no_stage.slice(-1)[0]
            document.getElementById("esp_depth").value = data.esp_par.property.esp_depth.slice(-1)[0]
            document.getElementById("esp_tubing").value = data.esp_par.property.esp_tubing.slice(-1)[0]

            document.getElementById("esp_min_flow").value =data.esp_par.property.esp_min_flow.slice(-1)[0]
            document.getElementById("esp_max_flow").value = data.esp_par.property.esp_max_flow.slice(-1)[0]

            document.getElementById("esp_head_coeff").value = data.esp_par.property.esp_head_coeff.slice(-1)[0]
            document.getElementById("esp_power_coeff").value = data.esp_par.property.esp_power_coeff.slice(-1)[0]


        }
    })

}

$('#select_well').on('change', function () {
    get_parameters()
})



function calculate_vlp_ipr() {
    var well_name = $('#select_well').val();
    if (well_name == '') {
        alert('Please select well first')
        return
    }

    boundary = {
        'wellhead_pressure': parseFloat(document.getElementById("well_whp").value),
        'wellhead_temperature': parseFloat(document.getElementById("well_wht").value),
        'esp_freq': parseFloat(document.getElementById("esp_frequency").value),
        'soil_temperature': parseFloat(document.getElementById("soil_temperature").value),
    }

    parameters = {
        'reservoir_pressure': parseFloat(document.getElementById("reservoir_pressure").value),
        'productivity_index': parseFloat(document.getElementById("productivity_index").value),
        'liquid_density': parseFloat(document.getElementById("liquid_density").value),
        'liquid_viscosity': parseFloat(document.getElementById("liquid_viscosity").value),
        'esp_type': document.getElementById("esp_type").value,
        'esp_no_stage': parseFloat(document.getElementById("esp_no_stage").value),
        'esp_depth': parseFloat(document.getElementById("esp_depth").value),
        'esp_tubing': parseFloat(document.getElementById("esp_tubing").value),
        'esp_head_coeff': document.getElementById("esp_head_coeff").value,
        'esp_power_coeff': document.getElementById("esp_power_coeff").value,
        'esp_min_flow': parseFloat(document.getElementById("esp_min_flow").value),
        'esp_max_flow': parseFloat(document.getElementById("esp_max_flow").value),
        'friction_correlation': document.getElementById("friction_correlation").value,
    }



    $.ajax({
        type: 'POST',
        url: '/app/productionwellperformance/calculate',
        contentType: 'application/json',
        data: JSON.stringify({ parameters: parameters, boundary: boundary }),
        success: function (data) {

            myProgress = setInterval(function () { get_result_vlp_ipr(data) }, 500);

        }
    })
}


function get_result_vlp_ipr(task_id) {


    $.ajax({
        type: 'POST',
        url: '/app/productionwellperformance/get_results',
        contentType: 'application/json',
        data: JSON.stringify({ task_id: task_id }),
        success: function (data) {

            task_status = data.task_status

            if (task_status == "SUCCESS") {
                clearInterval(myProgress)
                plot_vlp_ipr(data.task_result)
            }

            console.log(task_status)


        }
    })


}

function plot_vlp_ipr(data) {
    var layout = {
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: {
            color: "#D2D2D5"

        },
        xaxis: {
            title: {
                text: 'Flow (m3/h)',
            },
        },
        yaxis: {
            title: {
                text: 'Pressure (bar)',
            },
        },
    }

    if (data.sol_flow == null) {
        alert('No solution point is found. No intersection between IPR and VLP.')
    }

    document.getElementById("result_flow").value = math.round(data.sol_flow * 100) / 100
    document.getElementById("result_bhp").value = math.round(data.sol_pbh * 100) / 100
    document.getElementById("result_esp_head").value = math.round(data.sol_esp_head * 100) / 100
    document.getElementById("result_esp_power").value = math.round(data.sol_esp_power * 100) / 100
    document.getElementById("result_esp_efficiency").value = math.round(data.sol_esp_eff * 100) / 100
    document.getElementById("result_intake_pressure").value = math.round(data.sol_intake_pressure * 100) / 100
    document.getElementById("result_discharge_pressure").value = math.round(data.sol_discharge_pressure * 100) / 100


    trace_pres = {
        x: data.flow,
        y: data.reservoir_pressure,
        name: "reservoir pressure",
    }
    trace_intake_esp = {
        x: data.flow,
        y: data.intake_pressure,
        name: "intake pressure",
    }
    trace_discharge_esp = {
        x: data.flow,
        y: data.discharge_pressure,
        name: "discharge pressure",
    }
    trace_vlp = {
        x: data.flow,
        y: data.bottomhole_pressure_from_well,
        name: "VLP",
    }
    trace_ipr = {
        x: data.flow,
        y: data.bottomhole_pressure_from_reservoir,
        name: "IPR",
    }

    if (data.sol_flow != null) {
        trace_sol_flow = {
            x: [data.sol_flow[0], data.sol_flow[0]],
            y: [0, data.bottomhole_pressure_from_well[data.bottomhole_pressure_from_well.length - 1]],
            name: "solution flow",
            mode: 'lines',
            line: {
                color: 'rgb(255, 0, 0)',
                dash: 'dot',
                width: 4
            }
        }
    }

    if (data.sol_flow == null) {
        Plotly.newPlot('plotVLPIPR', [trace_vlp, trace_ipr], layout)
    } else {
        Plotly.newPlot('plotVLPIPR', [trace_pres, trace_intake_esp, trace_discharge_esp, trace_vlp, trace_ipr, trace_sol_flow], layout)
    }
}




