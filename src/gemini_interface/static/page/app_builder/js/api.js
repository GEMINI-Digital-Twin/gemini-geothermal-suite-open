function save_diagram() {

    commit_message = prompt("Please enter the message", "");
    if (commit_message == null || commit_message == "") {
        return;
    }

    var jsonObject = graph.toJSON();

    var fieldID = $('#select_project').val();
    if (fieldID) {
        $.ajax({
            type: 'POST',
            url: '/app/builder/save_diagram',
            contentType: 'application/json',
            data: JSON.stringify({ field_name: fieldID, diagram: jsonObject, commit_message: commit_message }),
            success: function (data) {
                alert('diagram is saved')
            }
        })
    }

}

function load_diagram() {

    var fieldID = $('#select_project').val();

    if (fieldID) {
        $.ajax({
            type: 'POST',
            url: '/app/builder/load_diagram',
            contentType: 'application/json',
            data: JSON.stringify({ field_name: fieldID }),
            success: function (data) {

                graph.fromJSON(data)



            },
            error: function () {
                graph.fromJSON({ "cells": [] })
            }
        })
    }

}

function log_status() {

    $('#myLogsModal').modal('show');

    var fieldID = $('#select_project').val();

    if (fieldID) {
        $.ajax({
            type: 'POST',
            url: '/app/builder/log_status',
            contentType: 'application/json',
            data: JSON.stringify({ field_name: fieldID }),
            success: function (data) {

                update_log_status_table(data)
            },
            error: function () {

            }
        })
    }

}

function update_log_status_table(table_data_json) {

    if ($.fn.dataTable.isDataTable('#data-table-logstatus')) {
        $('#data-table-logstatus').DataTable().destroy()
    }

    $('#data-table-logstatus').DataTable({
        data: table_data_json.data,
        columns: [
            {
                data: "date_modified",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "message",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
            {
                data: "author",
                render: function (data, type, row, meta) {
                    return '<font color="black">' + data + '</font>';
                }
            },
        ],
        bSort: false,
        searching: false,
        paging: false,
    })


}

$('#select_project').on('change', function () {
    load_diagram()
})


load_diagram()



function print_all_cells() {
    console.log(graph.getCells())
}



function load_template() {


    $.ajax({
        type: 'GET',
        url: '/app/builder/load_template',
        contentType: 'application/json',
        success: function (data) {

            graph.fromJSON(data)
        },
        error: function () {

        }
    })
}
