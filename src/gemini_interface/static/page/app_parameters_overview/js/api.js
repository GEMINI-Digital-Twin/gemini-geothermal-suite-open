function get_component_list() {
    var field_name = $('#select_project').val();

    // Call get_component_list python function
    $.ajax({
        type: 'POST',
        url: '/app/parameters_overview/get_component_list',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: field_name }),
        success: function (data) {
            var select = document.getElementById('select_component');
            select.options.length = 1;

            for (var i = 0; i < data.length; i++) {
                select.options[select.options.length] = new Option(data[i], data[i]);
            }
        }
    })
}

var parameters
var tagnames

function show() {
    var field_name = $('#select_project').val();
    var component_name = $('#select_component').val();

    // Call get_component_parameters python function
    $.ajax({
        type: 'POST',
        url: '/app/parameters_overview/get_component_parameters',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: field_name, component_name: component_name }),
        success: function (data) {
            // Retrieve parameters and tagnames from data
            parameters = data.parameters;
            tagnames = data.tagnames;

            

            var select = document.getElementById('select_parameters_timestamps');
            select.options.length = 0;
            for (var i = 0; i < data.parameters_timestamps.length; i++) {
                select.options[select.options.length] = new Option(data.parameters_timestamps[i], data.parameters_timestamps[i]);
            }
            parameters_idx = select.selectedIndex

            var select = document.getElementById('select_tagnames_timestamps');
            select.options.length = 0;
            for (var i = 0; i < data.tagnames_timestamps.length; i++) {
                select.options[select.options.length] = new Option(data.tagnames_timestamps[i], data.tagnames_timestamps[i]);
            }
            tagnames_idx = select.selectedIndex

            // Show the parameters and tagnames tables
            show_parameters(parameters_idx);
            show_tagnames(tagnames_idx);
        }
    })
}

$('#select_parameters_timestamps').on('change', function () {
    parameters_idx = document.getElementById('select_parameters_timestamps').selectedIndex
    show_parameters(parameters_idx)
})
$('#select_tagnames_timestamps').on('change', function () {
    tagnames_idx = document.getElementById('select_tagnames_timestamps').selectedIndex
    show_tagnames(tagnames_idx)
})

function show_parameters(parameters_idx) {
    // Clear previous tables
    $('#parametersTable').empty();

    // Create new tables
    var parameters_table = $('<table>').addClass('parameters_table_class');

    // Create table header for parameters
    var header_parameters = $('<thead>').append(
        $('<tr>').append(
            $('<th style="color: white">').text('Parameter Name'),
            $('<th style="color: white">').text('Value')
        )
    );

    // Append headers to tables
    parameters_table.append(header_parameters);

    // Create table bodies
    var tbody_parameters = $('<tbody>');

    // Append parameters to table body
    flag_productionwell_trajectory_table = false
    flag_injectionwell_trajectory_table = false

    for (var key in parameters) {
        if (parameters.hasOwnProperty(key)) {
            // If the parameter is productionwell trajectory table, a secondar table within the main table is created
            if (key == 'productionwell_trajectory_table') {
                flag_productionwell_trajectory_table = true

            } else if (key == 'injectionwell_trajectory_table') {
                parameters.injectionwell_trajectory_table
                flag_injectionwell_trajectory_table = true

            } else {
                
                var row = $('<tr>').append(
                    $('<td>').addClass('parameter-name').text(key),
                    $('<td>').append(
                        $('<input>').addClass('form-control').attr('id', key).attr('type', typeof (parameters[key])).attr('data-name', 'value').val(parameters[key][parameters_idx]).css('color', 'white')
                    )
                );
            }
            tbody_parameters.append(row);
        }
    }

    // Append tbody to table
    parameters_table.append(tbody_parameters);

    // Append table to the HTML element with id "parametersTable" and "tagnamesTable
    $('#parametersTable').append(parameters_table);

    if (flag_productionwell_trajectory_table) {
        add_trajectory_table(parameters.productionwell_trajectory_table[parameters_idx])
    };
    if (flag_injectionwell_trajectory_table) {
        add_trajectory_table(parameters.injectionwell_trajectory_table[parameters_idx])
    };

}

function add_trajectory_table(trajectory_table) {
    // Create new table
    var trajectory_table = $('<table>').addClass('data-table-injectionwelltrajectory');

    // Create table header for parameters
    var header_parameters = $('<thead>').append(
        $('<tr>').append(
            $('<th>').addClass('column-header').text('True vertical depth [m]'),
            $('<th>').addClass('column-header').text('Measured depth [m]'),
            $('<th>').addClass('column-header').text('Inner diameter [m]'),
            $('<th>').addClass('column-header').text('Material [ST/PE/HDPE/PVC]'),
            $('<th>').addClass('column-header').text('Roughness [m]')
        )
    );

    // Append headers to table
    trajectory_table.append(header_parameters);

    // Create table body
    var tbody_parameters = $('<tbody>');

    var trajectory_parameters = ['TVD', 'MD', 'ID', 'material', 'roughness']
    // Append parameters to table body
    for (var ii = 0; ii < trajectory_table.length; ii++) {
        var row = $('<tr>');

        for (var key of trajectory_parameters) {
            if (trajectory_table[ii].hasOwnProperty(key)) {
                row.append(
                    $('<td>').append(
                        $('<input>').addClass('form-control').attr('id', key).attr('type', typeof (trajectory_table[ii][key])).attr('data-name', 'value').val(trajectory_table[ii][key]).css('color', 'white')
                    )
                );
            }
        }
        tbody_parameters.append(row);

    }

    // Append tbody to table
    trajectory_table.append(tbody_parameters);

    // Append table to the HTML element with id "parametersTable"
    $('#parametersTable').append(trajectory_table);
}

function show_tagnames(tagnames_idx) {
    // Clear previous tables
    $('#tagnamesTable').empty();

    // Create new table
    var tagnames_table = $('<table>').addClass('tagnames_table');

    // Create table header for tagnames
    var header_tagnames = $('<thead>').append(
        $('<tr>').append(
            $('<th style="color: white">').addClass('column-header').text('Tagname'),
            $('<th style="color: white">').addClass('column-header').text('Value'),
            $('<th style="color: white">').addClass('column-header').text('Measured/Calculated')
        )
    );

    // Append headers to tables
    tagnames_table.append(header_tagnames);

    // Create table bodies
    var tbody_tagnames = $('<tbody>');

    // Append tagnames to table body
    for (var key in tagnames) {
        if (tagnames.hasOwnProperty(key)) {
            var row = $('<tr>').append(
                $('<td>').addClass('parameter-name').text(key),
                $('<td>').append(
                    $('<input>').addClass('form-control').attr('id', key).attr('data-name', 'value').val(tagnames[key]["value"][tagnames_idx]).css('color', 'white')
                ),
                $('<td>').append(
                    $('<input>').addClass('form-control').attr('id', key).attr('data-name', 'value').val(tagnames[key]["type"]).css('color', 'white')
                )
            );
            tbody_tagnames.append(row);
        }
    }

    // Append tbody to table
    tagnames_table.append(tbody_tagnames);

    // Append table to the HTML element with id "tagnamesTable
    $('#tagnamesTable').append(tagnames_table);
}


// ----- MAIN SCRIPT -----
// Execute get_parameters function
get_component_list()

// Execute when a component is selected from the drop down menu
$('#select_component').on('change', function () {
    // Execute show() function
    show()
})