function addESP() {
    componentStyling = {
        ".label": {
            text: "ESP",
            fontSize: 12
        },
    };
    inports = ["in"]
    outports = ["out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'esp' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })

}
function addInjectionPump() {
    componentStyling = {
        ".label": {
            text: "Injection Pump",
            fontSize: 12
        },
    };
    inports = ["in"]
    outports = ["out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'injection_pump' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}
function addBoosterPump() {
    componentStyling = {
        ".label": {
            text: "Booster Pump",
            fontSize: 12
        },
    };
    inports = ["in"]
    outports = ["out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'booster_pump' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}
function addFilter() {
    componentStyling = {
        ".label": {
            text: "Filter",
            fontSize: 12
        },
    };
    inports = ["in"]
    outports = ["out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'filter' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}
function addProductionWell() {
    componentStyling = {
        ".label": {
            text: "Production Well",
            fontSize: 12
        },
    };
    inports = ["in"]
    outports = ["out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'production_well' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}
function addInjectionWell() {
    componentStyling = {
        ".label": {
            text: "Injection Well",
            fontSize: 12
        },
    };
    inports = ["in"]
    outports = ["out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'injection_well' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}
function addReservoir() {
    componentStyling = {
        ".label": {
            text: "Reservoir",
            fontSize: 12
        },
    };
    inports = ["in"]
    outports = ["out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'reservoir' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}
function addDegasser() {
    componentStyling = {
        ".label": {
            text: "Degasser",
            fontSize: 12
        },
    };
    const inports = ["in"]
    const outports = ["out1", "out2"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'degasser' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}
function addHeatExchanger() {
    componentStyling = {
        ".label": {
            text: "Heat Exchanger",
            fontSize: 12
        },
    };
    const inports = ["PrimIn", "PrimOut"]
    const outports = ["SecIn", "SecOut"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'heat_exchanger' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })

}
function addGasBoiler() {
    componentStyling = {
        ".label": {
            text: "Gas Boiler",
            fontSize: 12
        },
    };
    inports = ["In"]
    outports = ["HeatIn", "HeatOut"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'gas_boiler' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}

function addElectricBoiler() {
    componentStyling = {
        ".label": {
            text: "Electric Boiler",
            fontSize: 12
        },
    };
    inports = ["In"]
    outports = ["HeatIn", "HeatOut"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'elec_boiler' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}

function addCHP() {
    componentStyling = {
        ".label": {
            text: "CHP",
            fontSize: 12
        },
    };
    inports = ["GasIn"]
    outports = ["SecIn", "SecOut", 'ElecOut']

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'chp' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}


function addHeatpump() {
    componentStyling = {
        ".label": {
            text: "Heat pump",
            fontSize: 12
        },
    };
    inports = ["PrimIn", "PrimOut"]
    outports = ["SecIn", "SecOut"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'heat_pump' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}

function addHeatDemand() {
    componentStyling = {
        ".label": {
            text: "Heat Demand",
            fontSize: 12
        },
    };
    inports = ["In"]
    outports = ["Out"]

    $.ajax({
        type: 'POST',
        url: '/app/builder/get_template_component',
        contentType: 'application/json',
        data: JSON.stringify({ component: 'heat_demand' }),
        success: function (data) {
            addComponent(componentStyling, inports, outports, data);
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}

function addComponent(styling, inports, outports, properties) {
    element = new joint.shapes.devs.Model({
        position: { x: 100, y: 100 },
        size: { width: 100, height: 50 },
        inPorts: inports,
        outPorts: outports,
        attrs: styling,
        properties: properties,
        ports: {
            groups: {
                in: {
                    attrs: {
                        ".port-body": {
                            fill: "#000000",
                            r: 5,
                        },
                    },
                },
                out: {
                    attrs: {
                        ".port-body": {
                            fill: "#000000",
                            r: 5,
                        },
                    },
                },
            },
        },
    });

    element.attributes.properties.id = element.id
    element.attributes.properties.name = element.attributes.properties.type + "_" + element.attributes.properties.id.substr(0, 4)

    element.addTo(graph);
}

function addNode() {


    var portsIn = {
        position: {
            name: 'left'
        },
        attrs: {
            portBody: {
                magnet: true,
                r: 5,
                fill: "#000000",
            }
        },
        markup: [{
            tagName: 'circle',
            selector: 'portBody'
        }]
    };

    var portsOut = {
        position: {
            name: 'right'
        },
        attrs: {
            portBody: {
                magnet: true,
                r: 5,
                fill: "#000000",
            }
        },
        markup: [{
            tagName: 'circle',
            selector: 'portBody'
        }]
    };


    var model = new joint.shapes.standard.Circle({
        position: { x: 100, y: 100 },
        size: { width: 20, height: 20 },
        ports: {
            groups: {
                'in': portsIn,
                'out': portsOut
            }
        }
    });


    model.addPorts([
        {
            group: 'in',
            attrs: { label: { text: 'in' } }
        },
        {
            group: 'out',
            attrs: { label: { text: 'out' } }
        }
    ]);

    model.addTo(graph);
}



function open_element_parameter(element) {
    hide_all_parameter_table()

    var fieldselect = document.getElementById('select_parameters_timestamps');
    fieldselect.options.length = 0;
    data = element.attributes.properties.parameters.timestamps
    for (var i = 0; i < data.length; i++) {
        fieldselect.options[fieldselect.options.length] = new Option(data[i], data[i]);
    }
    timestampsIndex = fieldselect.selectedIndex

    var fieldselect = document.getElementById('select_tagnames_timestamps');
    fieldselect.options.length = 0;
    data = element.attributes.properties.tagnames.timestamps
    for (var i = 0; i < data.length; i++) {
        fieldselect.options[fieldselect.options.length] = new Option(data[i], data[i]);
    }
    timestampsIndex = fieldselect.selectedIndex



    read_parameters()

}

function read_parameters() {

    element = selected_cell

    parameterstimestampsIndex = document.getElementById('select_parameters_timestamps').selectedIndex

    document.getElementById("component_type").value = element.attributes.properties.type
    document.getElementById("component_id").value = element.id
    document.getElementById("component_name").value = element.attributes.properties.name

    prop_names = []

    if (element.attributes.properties.type == 'esp') {
        document.getElementById("table-tagnames-measured-esp").style.display = "block"
        document.getElementById("table-component-properties-esp").style.display = "block"

        prop_names = ['esp_type', 'esp_no_stage', 'esp_tubing', 'esp_depth', 'esp_min_flow', 'esp_max_flow', 'esp_bep_flow', 'esp_power_coeff', 'esp_head_coeff']
    }
    if (element.attributes.properties.type == 'injection_pump') {
        document.getElementById("table-tagnames-measured-injectionpump").style.display = "block"
        document.getElementById("table-component-properties-injectionpump").style.display = "block"

        prop_names = ['injectionpump_type', 'injectionpump_no_stage']
    }
    if (element.attributes.properties.type == 'booster_pump') {
        document.getElementById("table-tagnames-measured-boosterpump").style.display = "block"
        document.getElementById("table-component-properties-boosterpump").style.display = "block"

        prop_names = ['boosterpump_type', 'boosterpump_no_stage']
    }

    if (element.attributes.properties.type == 'production_well') {
        document.getElementById("table-tagnames-measured-productionwell").style.display = "block"
        document.getElementById("table-component-properties-productionwell").style.display = "block"
        document.getElementById("div-data-table-productionwelltrajectory").style.display = "block"
        document.getElementById("div-data-table-productionwelltally").style.display = "block"

        data = { "data": element.attributes.properties.parameters.property.productionwell_trajectory_table[parameterstimestampsIndex] }
        update_productionwell_trajectory_table(data)

        tally_data = { "data": (element.attributes.properties.parameters.property.productionwell_tally_table && element.attributes.properties.parameters.property.productionwell_tally_table[parameterstimestampsIndex]) || [] }
        update_productionwell_tally_table(tally_data)

        prop_names = ['productionwell_soil_temperature', 'productionwell_productivity_index', 'productionwell_friction_correlation']
    }
    if (element.attributes.properties.type == 'injection_well') {
        document.getElementById("table-tagnames-measured-injectionwell").style.display = "block"
        document.getElementById("table-component-properties-injectionwell").style.display = "block"
        document.getElementById("div-data-table-injectionwelltrajectory").style.display = "block"
        document.getElementById("div-data-table-injectionwelltally").style.display = "block"

        data = { "data": element.attributes.properties.parameters.property.injectionwell_trajectory_table[parameterstimestampsIndex] }
        update_injectionwell_trajectory_table(data)

        tally_data = { "data": (element.attributes.properties.parameters.property.injectionwell_tally_table && element.attributes.properties.parameters.property.injectionwell_tally_table[parameterstimestampsIndex]) || [] }
        update_injectionwell_tally_table(tally_data)

        prop_names = ['injectionwell_soil_temperature', 'injectionwell_injectivity_index', 'injectionwell_friction_correlation']
    }
    if (element.attributes.properties.type == 'reservoir') {
        document.getElementById("table-tagnames-measured-reservoir").style.display = "block"
        document.getElementById("table-component-properties-reservoir").style.display = "block"

        prop_names = ['reservoir_pressure', 'reservoir_temperature', 'reservoir_thickness', 'reservoir_permeability', 'liquid_density', 'liquid_viscosity']
    }
    if (element.attributes.properties.type == 'chp') {
        document.getElementById("table-tagnames-measured-chp").style.display = "block"
        document.getElementById("table-component-properties-chp").style.display = "block"

        prop_names = ['chp_system_efficiency']
    }
    if (element.attributes.properties.type == 'heat_exchanger') {
        document.getElementById("table-tagnames-measured-heatexchanger").style.display = "block"
        document.getElementById("table-component-properties-heatexchanger").style.display = "block"

        prop_names = ['heat_transfer_coeff']
    }
    if (element.attributes.properties.type == 'heatpump') {
        document.getElementById("table-tagnames-measured-heatpump").style.display = "block"
        document.getElementById("table-component-properties-heatpump").style.display = "block"

        prop_names = ['heatpump_efficiency', 'heatpump_model']
    }
    if (element.attributes.properties.type == 'gas_boiler') {
        document.getElementById("table-tagnames-measured-gasboiler").style.display = "block"
        document.getElementById("table-component-properties-gasboiler").style.display = "block"

        prop_names = ['gasboiler_efficiency']
    }
    if (element.attributes.properties.type == 'electric_boiler') {
        document.getElementById("table-tagnames-measured-eboiler").style.display = "block"
        document.getElementById("table-component-properties-eboiler").style.display = "block"

        prop_names = ['eboiler_efficiency']
    }
    if (element.attributes.properties.type == 'heatdemand') {
        document.getElementById("table-tagnames-measured-heatdemand").style.display = "block"
        document.getElementById("table-component-properties-heatdemand").style.display = "block"

        prop_names = []
    }
    if (element.attributes.properties.type == 'degasser') {
        document.getElementById("table-tagnames-measured-degasser").style.display = "block"
        document.getElementById("table-component-properties-degasser").style.display = "block"

        prop_names = []
    }
    if (element.attributes.properties.type == 'filter') {
        document.getElementById("table-tagnames-measured-filter").style.display = "block"
        document.getElementById("table-component-properties-filter").style.display = "block"

        prop_names = []
    }

    for (let i = 0; i < prop_names.length; i++) {
        document.getElementById(prop_names[i]).value = eval('element.attributes.properties.parameters.property.' + prop_names[i] + '[' + parameterstimestampsIndex + ']')
    }

    tagnamestimestampsIndex = document.getElementById('select_tagnames_timestamps').selectedIndex


    tag_names = Object.keys(element.attributes.properties.tagnames.measured)
    for (let i = 0; i < tag_names.length; i++) {
        document.getElementById(tag_names[i]).value = eval('element.attributes.properties.tagnames.measured.' + tag_names[i] + '[' + tagnamestimestampsIndex + ']')
    }
}


hide_all_parameter_table()

function hide_all_parameter_table() {
    document.getElementById("table-tagnames-measured-injectionpump").style.display = "none"
    document.getElementById("table-tagnames-measured-boosterpump").style.display = "none"
    document.getElementById("table-tagnames-measured-esp").style.display = "none"
    document.getElementById("table-tagnames-measured-productionwell").style.display = "none"
    document.getElementById("table-tagnames-measured-injectionwell").style.display = "none"
    document.getElementById("table-tagnames-measured-reservoir").style.display = "none"
    document.getElementById("table-tagnames-measured-heatdemand").style.display = "none"
    document.getElementById("table-tagnames-measured-heatpump").style.display = "none"
    document.getElementById("table-tagnames-measured-heatexchanger").style.display = "none"
    document.getElementById("table-tagnames-measured-chp").style.display = "none"
    document.getElementById("table-tagnames-measured-gasboiler").style.display = "none"
    document.getElementById("table-tagnames-measured-eboiler").style.display = "none"
    document.getElementById("table-tagnames-measured-degasser").style.display = "none"
    document.getElementById("table-tagnames-measured-filter").style.display = "none"

    document.getElementById("table-component-properties-reservoir").style.display = "none"
    document.getElementById("table-component-properties-productionwell").style.display = "none"
    document.getElementById("table-component-properties-injectionwell").style.display = "none"
    document.getElementById("table-component-properties-esp").style.display = "none"
    document.getElementById("table-component-properties-injectionpump").style.display = "none"
    document.getElementById("table-component-properties-boosterpump").style.display = "none"
    document.getElementById("table-component-properties-gasboiler").style.display = "none"
    document.getElementById("table-component-properties-eboiler").style.display = "none"
    document.getElementById("table-component-properties-chp").style.display = "none"
    document.getElementById("table-component-properties-heatpump").style.display = "none"
    document.getElementById("table-component-properties-heatexchanger").style.display = "none"
    document.getElementById("table-component-properties-degasser").style.display = "none"
    document.getElementById("table-component-properties-filter").style.display = "none"
    document.getElementById("table-component-properties-heatdemand").style.display = "none"

    document.getElementById("div-data-table-productionwelltrajectory").style.display = "none"
    document.getElementById("div-data-table-injectionwelltrajectory").style.display = "none"
    document.getElementById("div-data-table-productionwelltally").style.display = "none"
    document.getElementById("div-data-table-injectionwelltally").style.display = "none"

}


function save_parameters() {
    console.log("saving parameter")
    element = selected_cell

    if (element.attributes.properties.name == '') {
        element.attributes.properties.name = document.getElementById("component_type").value + '_' + element.id.substr(0, 4)
    } else {
        element.attributes.properties.name = document.getElementById('component_name').value
    }

    parameterstimestampsIndex = document.getElementById('select_parameters_timestamps').selectedIndex


    if (element.attributes.properties.type == 'reservoir') {
        element.attributes.properties.parameters.property.reservoir_pressure[parameterstimestampsIndex] = parseFloat(document.getElementById("reservoir_pressure").value)
        element.attributes.properties.parameters.property.reservoir_temperature[parameterstimestampsIndex] = parseFloat(document.getElementById("reservoir_temperature").value)
        element.attributes.properties.parameters.property.reservoir_thickness[parameterstimestampsIndex] = parseFloat(document.getElementById("reservoir_thickness").value)
        element.attributes.properties.parameters.property.reservoir_permeability[parameterstimestampsIndex] = parseFloat(document.getElementById("reservoir_permeability").value)
        element.attributes.properties.parameters.property.liquid_density[parameterstimestampsIndex] = parseFloat(document.getElementById("liquid_density").value)
        element.attributes.properties.parameters.property.liquid_viscosity[parameterstimestampsIndex] = parseFloat(document.getElementById("liquid_viscosity").value)
    }
    if (element.attributes.properties.type == 'production_well') {
        element.attributes.properties.parameters.property.productionwell_soil_temperature[parameterstimestampsIndex] = parseFloat(document.getElementById("productionwell_soil_temperature").value)
        element.attributes.properties.parameters.property.productionwell_friction_correlation[parameterstimestampsIndex] = document.getElementById("productionwell_friction_correlation").value
        element.attributes.properties.parameters.property.productionwell_productivity_index[parameterstimestampsIndex] = parseFloat(document.getElementById("productionwell_productivity_index").value)
        element.attributes.properties.parameters.property.productionwell_trajectory_table[parameterstimestampsIndex] = $('#data-table-productionwelltrajectory').DataTable().data().toArray()
        if (!element.attributes.properties.parameters.property.productionwell_tally_table) {
            element.attributes.properties.parameters.property.productionwell_tally_table = element.attributes.properties.parameters.timestamps.map(function () { return []; });
        }
        if ($.fn.dataTable.isDataTable('#data-table-productionwelltally')) {
            element.attributes.properties.parameters.property.productionwell_tally_table[parameterstimestampsIndex] = $('#data-table-productionwelltally').DataTable().data().toArray()
        }
    }
    if (element.attributes.properties.type == 'injection_well') {
        element.attributes.properties.parameters.property.injectionwell_soil_temperature[parameterstimestampsIndex] = parseFloat(document.getElementById("injectionwell_soil_temperature").value)
        element.attributes.properties.parameters.property.injectionwell_friction_correlation[parameterstimestampsIndex] = document.getElementById("injectionwell_friction_correlation").value
        element.attributes.properties.parameters.property.injectionwell_injectivity_index[parameterstimestampsIndex] = parseFloat(document.getElementById("injectionwell_injectivity_index").value)
        element.attributes.properties.parameters.property.injectionwell_trajectory_table[parameterstimestampsIndex] = $('#data-table-injectionwelltrajectory').DataTable().data().toArray()
        if (!element.attributes.properties.parameters.property.injectionwell_tally_table) {
            element.attributes.properties.parameters.property.injectionwell_tally_table = element.attributes.properties.parameters.timestamps.map(function () { return []; });
        }
        if ($.fn.dataTable.isDataTable('#data-table-injectionwelltally')) {
            element.attributes.properties.parameters.property.injectionwell_tally_table[parameterstimestampsIndex] = $('#data-table-injectionwelltally').DataTable().data().toArray()
        }
    }
    if (element.attributes.properties.type == 'esp') {
        element.attributes.properties.parameters.property.esp_no_stage[parameterstimestampsIndex] = parseFloat(document.getElementById("esp_no_stage").value)
        element.attributes.properties.parameters.property.esp_type[parameterstimestampsIndex] = document.getElementById("esp_type").value
        element.attributes.properties.parameters.property.esp_tubing[parameterstimestampsIndex] = parseFloat(document.getElementById("esp_tubing").value)
        element.attributes.properties.parameters.property.esp_depth[parameterstimestampsIndex] = parseFloat(document.getElementById("esp_depth").value)
        element.attributes.properties.parameters.property.esp_head_coeff[parameterstimestampsIndex] = document.getElementById("esp_head_coeff").value
        element.attributes.properties.parameters.property.esp_power_coeff[parameterstimestampsIndex] = document.getElementById("esp_power_coeff").value
        element.attributes.properties.parameters.property.esp_min_flow[parameterstimestampsIndex] = parseFloat(document.getElementById("esp_min_flow").value)
        element.attributes.properties.parameters.property.esp_max_flow[parameterstimestampsIndex] = parseFloat(document.getElementById("esp_max_flow").value)
        element.attributes.properties.parameters.property.esp_bep_flow[parameterstimestampsIndex] = parseFloat(document.getElementById("esp_bep_flow").value)

    }
    if (element.attributes.properties.type == 'injection_pump') {
        element.attributes.properties.parameters.property.injectionpump_no_stage[parameterstimestampsIndex] = parseFloat(document.getElementById("injectionpump_no_stage").value)
        element.attributes.properties.parameters.property.injectionpump_type[parameterstimestampsIndex] = document.getElementById("injectionpump_type").value
    }
    if (element.attributes.properties.type == 'booster_pump') {
        element.attributes.properties.parameters.property.boosterpump_no_stage[parameterstimestampsIndex] = parseFloat(document.getElementById("boosterpump_no_stage").value)
        element.attributes.properties.parameters.property.boosterpump_type[parameterstimestampsIndex] = document.getElementById("boosterpump_type").value
    }
    if (element.attributes.properties.type == 'gas_boiler') {
        element.attributes.properties.parameters.property.gasboiler_efficiency[parameterstimestampsIndex] = parseFloat(document.getElementById("gasboiler_efficiency").value)
    }
    if (element.attributes.properties.type == 'electric_boiler') {
        element.attributes.properties.parameters.property.gasboiler_efficiency[parameterstimestampsIndex] = parseFloat(document.getElementById("eboiler_efficiency").value)
    }
    if (element.attributes.properties.type == 'chp') {
        element.attributes.properties.parameters.property.chp_system_efficiency[parameterstimestampsIndex] = parseFloat(document.getElementById("chp_system_efficiency").value)
    }
    if (element.attributes.properties.type == 'heatpump') {
        element.attributes.properties.parameters.property.heatpump_efficiency[parameterstimestampsIndex] = parseFloat(document.getElementById("heatpump_efficiency").value)
        element.attributes.properties.parameters.property.heatpump_model[parameterstimestampsIndex] = document.getElementById("heatpump_model").value
    }
    if (element.attributes.properties.type == 'heat_exchanger') {
        element.attributes.properties.parameters.property.heat_transfer_coeff[parameterstimestampsIndex] = parseFloat(document.getElementById("heat_transfer_coeff").value)
    }
    if (element.attributes.properties.type == 'heatdemand') {

    }
    if (element.attributes.properties.type == 'degasser') {

    }
    if (element.attributes.properties.type == 'filter') {

    }

    tagnamestimestampsIndex = document.getElementById('select_tagnames_timestamps').selectedIndex

    tag_names = Object.keys(element.attributes.properties.tagnames.measured)
    for (let i = 0; i < tag_names.length; i++) {
        eval('element.attributes.properties.tagnames.measured.' + tag_names[i] + '[' + tagnamestimestampsIndex + '] = document.getElementById("' + tag_names[i] + '").value')
    }

}


$.ajax({
    dataType: "json",
    url: '../static/database/pumpdatabase.json',
    success: function (data) {
        var select = document.getElementById('injectionpump_type');
        select.options.length = 1;

        for (var i = 0; i < data.data.length; i++) {
            select.options[select.options.length] = new Option(data.data[i].pumptype, data.data[i].pumptype);
        }

        var select = document.getElementById('esp_type');
        select.options.length = 1;

        for (var i = 0; i < data.data.length; i++) {
            select.options[select.options.length] = new Option(data.data[i].pumptype, data.data[i].pumptype);
        }

        var select = document.getElementById('boosterpump_type');
        select.options.length = 1;

        for (var i = 0; i < data.data.length; i++) {
            select.options[select.options.length] = new Option(data.data[i].pumptype, data.data[i].pumptype);
        }
    }
})

$('#esp_type').on('change', function () {

    var esp_type = $('#esp_type').val()

    BPD_to_m3h = 0.006624

    $.ajax({
        dataType: "json",
        url: '../static/database/pumpdatabase.json',
        success: function (data) {
            for (var i = 0; i < data.data.length; i++) {
                if (data.data[i].pumptype == esp_type) {

                    document.getElementById("esp_min_flow").value = Math.round(data.data[i].minrate * BPD_to_m3h * 100) / 100
                    document.getElementById("esp_max_flow").value = Math.round(data.data[i].maxrate * BPD_to_m3h * 100) / 100
                    document.getElementById("esp_bep_flow").value = Math.round(data.data[i].beprate * BPD_to_m3h * 100) / 100

                    document.getElementById("esp_head_coeff").value = data.data[i].hC0 + ';' + data.data[i].hC1 + ';' + data.data[i].hC2 + ';' + data.data[i].hC3 + ';' + data.data[i].hC4 + ';' + data.data[i].hC5
                    document.getElementById("esp_power_coeff").value = data.data[i].bC0 + ';' + data.data[i].bC1 + ';' + data.data[i].bC2 + ';' + data.data[i].bC3 + ';' + data.data[i].bC4 + ';' + data.data[i].bC5

                }
            }

        }

    })

});

$('#select_timestamps').on('change', function () {
    read_parameters()
})

function upload_production_well_trajectory() {

    var fileInput = document.getElementById('production_well_trajectory_csv');

    // Check if a file is selected
    if (fileInput.files.length === 0) {
        return; // Exit the function if no file is selected
    }

    var form_data = new FormData()
    form_data.append('file', $('#production_well_trajectory_csv')[0].files[0])

    $.ajax({
        type: 'POST',
        url: '/app/builder/upload_well_trajectory',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        success: function (data) {

            update_productionwell_trajectory_table(data)
        }
    })
}


function upload_injection_well_trajectory() {

    var fileInput = document.getElementById('injection_well_trajectory_csv');

    // Check if a file is selected
    if (fileInput.files.length === 0) {
        return; // Exit the function if no file is selected
    }

    var form_data = new FormData()
    form_data.append('file', $('#injection_well_trajectory_csv')[0].files[0])

    $.ajax({
        type: 'POST',
        url: '/app/builder/upload_well_trajectory',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        success: function (data) {
            update_injectionwell_trajectory_table(data)
        }
    })
}

function upload_production_well_tally() {
    var fileInput = document.getElementById('production_well_tally_csv');
    if (fileInput.files.length === 0) {
        return;
    }
    var form_data = new FormData();
    form_data.append('file', $('#production_well_tally_csv')[0].files[0]);
    $.ajax({
        type: 'POST',
        url: '/app/builder/upload_well_tally',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        success: function (data) {
            update_productionwell_tally_table(data);
        },
        error: function (xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : xhr.responseText || 'Upload failed';
            alert(msg);
        }
    });
}

function upload_injection_well_tally() {
    var fileInput = document.getElementById('injection_well_tally_csv');
    if (fileInput.files.length === 0) {
        return;
    }
    var form_data = new FormData();
    form_data.append('file', $('#injection_well_tally_csv')[0].files[0]);
    $.ajax({
        type: 'POST',
        url: '/app/builder/upload_well_tally',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        success: function (data) {
            update_injectionwell_tally_table(data);
        },
        error: function (xhr) {
            var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : xhr.responseText || 'Upload failed';
            alert(msg);
        }
    });
}

function update_productionwell_tally_table(table_data_json) {
    if ($.fn.dataTable.isDataTable('#data-table-productionwelltally')) {
        $('#data-table-productionwelltally').DataTable().destroy();
    }
    var data = table_data_json.data || [];
    $('#data-table-productionwelltally').DataTable({
        data: data,
        columns: [
            { data: "Joint", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "TopMD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "BottomMD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "TopTVD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "BottomTVD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "ID", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "OD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "Roughness", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } }
        ],
        scrollX: true,
        bSort: false,
    });
}

function update_injectionwell_tally_table(table_data_json) {
    if ($.fn.dataTable.isDataTable('#data-table-injectionwelltally')) {
        $('#data-table-injectionwelltally').DataTable().destroy();
    }
    var data = table_data_json.data || [];
    $('#data-table-injectionwelltally').DataTable({
        data: data,
        columns: [
            { data: "Joint", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "TopMD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "BottomMD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "TopTVD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "BottomTVD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "ID", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "OD", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } },
            { data: "Roughness", render: function (d) { return '<font color="black">' + (d != null ? d : '') + '</font>'; } }
        ],
        scrollX: true,
        bSort: false,
    });
}

function update_productionwell_trajectory_table(table_data_json) {

    if ($.fn.dataTable.isDataTable('#data-table-productionwelltrajectory')) {
        $('#data-table-productionwelltrajectory').DataTable().destroy()
    }

    $('#data-table-productionwelltrajectory').DataTable({
        data: table_data_json.data,
        columns: [
            {
                data: "TVD",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "MD",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "ID",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "material",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "roughness",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            }
        ],
        scrollX: true,
        bSort: false,
    })

}

function update_injectionwell_trajectory_table(table_data_json) {

    if ($.fn.dataTable.isDataTable('#data-table-injectionwelltrajectory')) {
        $('#data-table-injectionwelltrajectory').DataTable().destroy()
    }

    $('#data-table-injectionwelltrajectory').DataTable({
        data: table_data_json.data,
        columns: [
            {
                data: "TVD",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "MD",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "ID",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "material",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "roughness",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            }
        ],
        scrollX: true,
        bSort: false,
    })

}

function add_parameters_timestamps() {

    element = selected_cell

    timestamps = document.getElementById("parameters_timestamps").value;

    if (element.attributes.properties.parameters.timestamps.includes(timestamps)) {
        alert("Timestamp already exists")
        return
    }

    fieldselect = document.getElementById('select_parameters_timestamps');
    fieldselect.options[fieldselect.options.length] = new Option(timestamps, timestamps);

    element.attributes.properties.parameters.timestamps.push(timestamps)

    prop_names = Object.keys(element.attributes.properties.parameters.property)
    for (var ii = 0; ii < prop_names.length; ii++) {
        eval('element.attributes.properties.parameters.property.' + prop_names[ii] + '.push(element.attributes.properties.parameters.property. ' + prop_names[ii] + '.slice(-1)[0])')
    }
    fieldselect.value = timestamps

    $('#myParametersTimestampsModal').modal('hide');

    alert('parameters at : ' + timestamps + " is added")
}

function delete_parameters_timestamps() {

    element = selected_cell

    timestamps = document.getElementById("select_parameters_timestamps").value;

    if (element.attributes.properties.parameters.timestamps.length == 1) {
        alert("Can't delete the only parameter's timestamp")
        return
    }

    index = element.attributes.properties.parameters.timestamps.indexOf(timestamps)

    element.attributes.properties.parameters.timestamps.splice(index, 1)

    prop_names = Object.keys(element.attributes.properties.parameters.property)
    for (var ii = 0; ii < prop_names.length; ii++) {
        eval('element.attributes.properties.parameters.property.' + prop_names[ii] + '.splice(' + index + ',1)')
    }

    fieldselect = document.getElementById('select_parameters_timestamps');
    fieldselect.options.remove(index)

    alert('parameters at : ' + timestamps + " is deleted")
}

function add_tagnames_timestamps() {

    element = selected_cell

    timestamps = document.getElementById("tagnames_timestamps").value;

    fieldselect = document.getElementById('select_tagnames_timestamps');
    fieldselect.options[fieldselect.options.length] = new Option(timestamps, timestamps);

    element.attributes.properties.tagnames.timestamps.push(timestamps)

    category = ['measured', 'filtered', 'calculated']
    for (var j = 0; j < category.length; j++) {
        prop_names = eval('Object.keys(element.attributes.properties.tagnames.' + category[j] + ')')
        for (var i = 0; i < prop_names.length; i++) {
            eval('element.attributes.properties.tagnames.' + category[j] + '.' + prop_names[i] + '.push(element.attributes.properties.tagnames.' + category[j] + '.' + prop_names[i] + '.slice(-1)[0])')
        }
    }


    fieldselect.value = timestamps

    $('#myParametersTimestampsModal').modal('hide');

    alert('tagnames at : ' + timestamps + " is added")
}

function delete_tagnames_timestamps() {

    element = selected_cell

    timestamps = document.getElementById("select_tagnames_timestamps").value;

    if (element.attributes.properties.tagnames.timestamps.length == 1) {
        alert("Can't delete the only tagnames's timestamp")
        return
    }

    index = element.attributes.properties.tagnames.timestamps.indexOf(timestamps)

    element.attributes.properties.tagnames.timestamps.splice(index, 1)

    category = ['measured', 'filtered', 'calculated']
    for (var j = 0; j < category.length; j++) {
        prop_names = eval('Object.keys(element.attributes.properties.tagnames.' + category[j] + ')')
        for (var i = 0; i < prop_names.length; i++) {
            eval('element.attributes.properties.tagnames.' + category[j] + '.' + prop_names[i] + '.splice(' + index + ',1)')
        }
    }

    fieldselect = document.getElementById('select_tagnames_timestamps');
    fieldselect.options.remove(index)

    alert('tagnames at : ' + timestamps + " is deleted")
}


$('#select_parameters_timestamps').change(function () {
    read_parameters()
})
$('#select_tagnames_timestamps').change(function () {
    read_parameters()
})