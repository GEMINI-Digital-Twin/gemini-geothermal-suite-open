function get_project_list() {
    $.ajax({
        type: 'GET',
        url: '/getprojectlist',
        success: function (data) {

            if (data != null) {
                var fieldselect = document.getElementById('project_name_list');
                fieldselect.options.length = 1;
                for (var i = 0; i < data.length; i++) {
                    fieldselect.options[fieldselect.options.length] = new Option(data[i], data[i]);
                }
            }
        }
    });
}

get_project_list()


function create_new_project() {
    project_name = document.getElementById("select_project").value
    if (project_name == "") {
        value = true
    } else {
        value = confirm("Do you want to create a new project? You will lose your current project.")
    }
    if (value == true) {
        project_name = window.prompt("What is the project name?", "project1");



        $.ajax({
            type: 'POST',
            url: '/createproject',
            contentType: 'application/json',
            data: JSON.stringify({ project_name: project_name }),
            success: function (data) {

                window.alert(data)

                document.getElementById("select_project").value = project_name

                window.location.reload()
            }
        })

    }
}

function save_project() {
    project_name = document.getElementById("select_project").value

    if (project_name == "") {
        project_name = window.prompt("What is the project name?", "project1");
    }


    $.ajax({
        type: 'POST',
        url: '/saveproject',
        contentType: 'application/json',
        data: JSON.stringify({ projectname: project_name, layerdata: '' }),
        success: function (data) {
            window.alert(data);

            document.getElementById("select_project").value = project_name

            window.location.reload()
        }
    })



}

function close_project() {
    project_name = document.getElementById("select_project").value

    if (project_name == "") {
        return
    }

    $.ajax({
        type: 'POST',
        url: '/closeproject',
        contentType: 'application/json',
        data: JSON.stringify({ project_name: project_name }),
        success: function (data) {
            window.alert(data);

            document.getElementById("select_project").value = ""

            window.location.reload()
        }
    })



}

function delete_project() {
    project_name = document.getElementById("select_project").value

    if (project_name == "") {
        return
    }
    value = confirm("Do you want to delete " + project_name + "? This action can't be undone.")
    if (value == true) {
        $.ajax({
            type: 'POST',
            url: '/deleteproject',
            contentType: 'application/json',
            data: JSON.stringify({ project_name: project_name }),
            success: function (data) {


                window.alert(data);

                document.getElementById("select_project").value = ""

                window.location.reload()

            }
        })
    }



}

function open_project() {
    project_name = document.getElementById('project_name_list').value;

    if (project_name) {
        document.getElementById("select_project").value = project_name


        $.ajax({
            type: 'POST',
            url: '/loadproject',
            contentType: 'application/json',
            data: JSON.stringify({ project_name: project_name }),
            success: function (data) {

                $('#myProjectModal').modal('hide');

                alert('project is loaded successfully.')

                window.location.reload()


            }
        });

    }


}

function import_project() {
    var form_data = new FormData()
    form_data.append('file', $('#project_zip')[0].files[0])

    if (form_data.entries().next().value[1] == 'undefined') {
        return
    }

    $.ajax({
        type: 'POST',
        url: '/importproject',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        success: function (data) {
            alert(data)

            window.location.reload()
        },
        error: function (request, status, error) {
            alert(request.responseText);
        }
    })
}




function export_project() {
    project_name = document.getElementById("select_project").value

    if (project_name == "") {
        return
    }

    $.ajax({
        type: 'POST',
        url: '/exportproject',
        contentType: 'application/json',
        data: JSON.stringify({ project_name: project_name }),
        xhrFields: {
            responseType: 'blob' // to avoid binary data being mangled on charset conversion
        },
        success: function (data) {
            var file = new Blob([data], { type: 'octet/stream' });

            saveBlob(file, project_name + '.zip')
        }
    })

}

var saveBlob = (function () {
    var a = document.createElement("a");
    document.body.appendChild(a);
    a.style = "display: none";
    return function (blob, fileName) {
        var url = window.URL.createObjectURL(blob);
        a.href = url;
        a.download = fileName;
        a.click();
        window.URL.revokeObjectURL(url);
    };
}());




