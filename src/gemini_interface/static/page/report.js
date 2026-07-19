function get_report_list() {

    var project_name = document.getElementById("select_project").value;
    if (project_name) {
        $.ajax({
            type: 'POST',
            url: '/report/getreportlist',
            contentType: 'application/json',
            data: JSON.stringify({ project_name: project_name }),
            success: function (data) {
                if (data != null) {
                    var select = document.getElementById('select_report');
                    select.options.length = 1;
                    for (var i = 0; i < data.length; i++) {
                        select.options[select.options.length] = new Option(data[i], data[i]);
                    }
                }
            }
        });
    }
}

get_report_list()

$('#select_report').on('change', function () {
    clear_report_frame()

    var project_name = document.getElementById("select_project").value;
    var file_name = document.getElementById("select_report").value;

    if (file_name) {
        $.ajax({
            type: 'POST',
            url: '/report/open_document',
            contentType: 'application/json',
            data: JSON.stringify({ project_name: project_name, file_name: file_name }),
            xhrFields: {
                responseType: 'blob' // to avoid binary data being mangled on charset conversion
            },
            success: function (data) {
                var file = new Blob([data], { type: 'application/pdf' });

                var fileURL = URL.createObjectURL(file)

                document.getElementById('iFrame_report').src = fileURL
            }
        });
    }
})

function clear_report_frame() {
    document.getElementById('iFrame_report').src = "";
}

function clear_report_list() {
    var select = document.getElementById('select_report');
    select.options.length = 0;
    select.options[select.options.length] = new Option('', '');
}

function upload_report() {

    var project_name = document.getElementById("select_project").value;
    document_search = document.getElementById('checkbox_rag').checked

    var form_data = new FormData()
    files =  $('#report_pdf')[0].files
    for (let i = 0; i < files.length; i++) {
        form_data.append('file_'+i, files[i])
    }
    form_data.append('file_count', files.length)
    form_data.append('project_name', project_name)
    form_data.append('document_search', document_search)

    $.ajax({
        type: 'POST',
        url: '/report/upload_document',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        success: function (data) {
            alert(data)

            get_report_list()
        }
    })


}

function delete_report() {


    var project_name = document.getElementById("select_project").value;
    var file_name = document.getElementById("select_report").value;

    value = confirm("Do you want to delete this document: " + file_name + " ?")
    if (value == false) {
        return
    }

    if (file_name) {
        $.ajax({
            type: 'POST',
            url: '/report/delete_document',
            contentType: 'application/json',
            data: JSON.stringify({ project_name: project_name, file_name: file_name }),
            success: function (data) {
                alert(data)

                clear_report_frame()
                get_report_list()
            }
        });
    }
}