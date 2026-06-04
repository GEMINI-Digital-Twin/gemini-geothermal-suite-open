load_plant()
hide_all_database_parameter_table()


function load_plant() {

    var fieldID = $('#select_project').val();


    $.ajax({
        type: 'POST',
        url: '/setting/plant/load_plant',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {
            get_database_parameters()
        }
    })
}


$('#select_database').on('change', function () {
    hide_all_database_parameter_table()
    show_database_parameter_table()
});

function hide_all_database_parameter_table() {
    document.getElementById("table-avevadb").style.display = "none"
    document.getElementById("table-pisystem").style.display = "none"
}

function show_database_parameter_table() {
    if (document.getElementById("select_database").value == 'avevadb') {
        document.getElementById("table-avevadb").style.display = "block"
    } else if (document.getElementById("select_database").value == 'pisystem') {
        document.getElementById("table-pisystem").style.display = "block"
    }
}

function get_database_parameters() {

    $.ajax({
        type: 'GET',
        url: '/setting/plant/get_plant_parameters',
        contentType: 'application/json',
        success: function (data) {

            document.getElementById("start_time").value = data.database.start_time
            document.getElementById("measured_interval").value = data.database.measured.interval
            document.getElementById("filtered_interval").value = data.database.filtered.interval
            document.getElementById("calculated_interval").value = data.database.calculated.interval
            document.getElementById("prediction_interval").value = data.database.prediction.interval
            document.getElementById("prediction_horizon").value = data.database.prediction.horizon

            document.getElementById("dashboard_url").value = data.dashboard.url
            document.getElementById("wims_backend_url").value = data.wims_backend_url
            document.getElementById("select_database").value = data.database.external_database

            show_database_parameter_table()

            document.getElementById("avevadb_url").value = data.database.avevadb.url
            document.getElementById("avevadb_tenant").value = data.database.avevadb.tenant
            document.getElementById("avevadb_client_id").value = data.database.avevadb.client_id
            document.getElementById("avevadb_client_secret").value = data.database.avevadb.client_secret
            document.getElementById("avevadb_namespace_id").value = data.database.avevadb.namespace_id

            document.getElementById("pisystem_url").value = data.database.pisystem.url
            document.getElementById("pisystem_username").value = data.database.pisystem.username
            document.getElementById("pisystem_password").value = data.database.pisystem.password

        }
    })
}


function save_parameters() {
    var fieldID = $('#select_project').val();


    $.ajax({
        type: 'GET',
        url: '/setting/plant/get_plant_parameters',
        contentType: 'application/json',
        success: function (data) {

            data.database.start_time = document.getElementById("start_time").value
            data.database.measured.interval = parseFloat(document.getElementById("measured_interval").value)
            data.database.filtered.interval = parseFloat(document.getElementById("filtered_interval").value)
            data.database.calculated.interval = parseFloat(document.getElementById("calculated_interval").value)
            data.database.prediction.interval = parseFloat(document.getElementById("prediction_interval").value)
            data.database.prediction.horizon = parseFloat(document.getElementById("prediction_horizon").value)

            data.dashboard.url = document.getElementById("dashboard_url").value
            data.wims_backend_url = document.getElementById("wims_backend_url").value

            data.database.external_database = document.getElementById("select_database").value

            data.database.avevadb.url = document.getElementById("avevadb_url").value,
            data.database.avevadb.tenant = document.getElementById("avevadb_tenant").value,
            data.database.avevadb.client_id = document.getElementById("avevadb_client_id").value,
            data.database.avevadb.client_secret = document.getElementById("avevadb_client_secret").value,
            data.database.avevadb.namespace_id = document.getElementById("avevadb_namespace_id").value


            $.ajax({
                type: 'POST',
                url: '/setting/plant/save_plant_parameters',
                contentType: 'application/json',
                data: JSON.stringify({ parameters: data }),
                success: function (data) {
                    alert('plant parameters are saved')
                }
            })
        }
    })


}

