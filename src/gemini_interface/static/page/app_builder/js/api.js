function save_diagram() {

    if (inspectorDirty && !save_parameters()) return;
    recordDiagramChange();
    commit_message = prompt("Please enter the message", "");
    if (commit_message == null || commit_message == "") {
        return;
    }

    var jsonObject = graph.toJSON();
    var snapshot = JSON.stringify(jsonObject);

    var fieldID = $('#select_project').val();
    if (fieldID) {
        $.ajax({
            type: 'POST',
            url: '/app/builder/save_diagram',
            contentType: 'application/json',
            data: JSON.stringify({ field_name: fieldID, diagram: jsonObject, commit_message: commit_message }),
            success: function (data) {
                markDiagramSaved(snapshot);
                setBuilderStatus(hasUnsavedDiagram() ? 'Unsaved changes' : 'Saved', hasUnsavedDiagram());
            },
            error: function (xhr) {
                alert('Could not save diagram: ' + (xhr.responseText || 'Server error'));
            }
        })
    } else {
        alert('Open a project before saving the diagram.');
    }

}

function load_diagram(confirmReplace) {

    var fieldID = $('#select_project').val();
    if (confirmReplace && hasUnsavedDiagram() &&
        !confirm('Reload the saved diagram? Unsaved changes will be lost.')) return;

    if (fieldID) {
        document.getElementById('save').disabled = true;
        setBuilderStatus('Loading diagram...', false);
        $.ajax({
            type: 'POST',
            url: '/app/builder/load_diagram',
            contentType: 'application/json',
            data: JSON.stringify({ field_name: fieldID }),
            success: function (data) {

                graph.fromJSON(data)
                resetEditorHistory(true)
                document.getElementById('save').disabled = false;

            },
            error: function (xhr) {
                document.getElementById('save').disabled = false;
                setBuilderStatus('Load failed', true);
                alert('Could not load diagram: ' + (xhr.responseText || 'Server error'));
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
                alert('Could not load project history.');
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
    load_diagram(true)
})


load_diagram()



function print_all_cells() {
    console.log(graph.getCells())
}



function load_template() {

    if (hasUnsavedDiagram() &&
        !confirm('Replace this diagram with the example? Unsaved changes will be lost.')) return;
    if (!hasUnsavedDiagram() &&
        !confirm('Replace the current diagram with the example? You can reload the saved version.')) return;

    $.ajax({
        type: 'GET',
        url: '/app/builder/load_template',
        contentType: 'application/json',
        success: function (data) {

            recordDiagramChange()
            graph.fromJSON(data)
            recordDiagramChange()
        },
        error: function () {
            alert('Could not load the example diagram.');
        }
    })
}
