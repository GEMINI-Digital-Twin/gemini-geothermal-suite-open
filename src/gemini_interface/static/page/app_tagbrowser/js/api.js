load_plant()
get_unitnames()
connect_database()

function load_plant() {

    var fieldID = $('#select_project').val();

    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/load_plant',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {
            if (data == 'csv') {
                document.getElementById("button_import_data").disabled = true
            } else {
                document.getElementById("button_upload_data_csv").disabled = true
                document.getElementById("data_csv").disabled = true
            }
        }
    })
}




$('#select_database').on('change', function () {
    connect_database()
});

function show_unit_selection() {
    document.getElementById("unit").style.display = "block"
}

function hide_unit_selection() {
    document.getElementById("unit").style.display = "none"
}



function connect_database() {

    clear_tagnames()

    var fieldID = $('#select_project').val();
    var database = $('#select_database').val();


    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/connect_database',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID, database_name: database }),
        success: function (data) {
            if (database == 'geminidb') {
                show_unit_selection()
            } else {
                get_tagnames()
                hide_unit_selection()
            }
        }
    })
}

function get_unitnames() {
    var fieldID = $('#select_project').val();

    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/get_unitnames',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {
            var fieldselect = document.getElementById('select_unitnames');
            fieldselect.options.length = 1;
            for (var i = 0; i < data.length; i++) {
                fieldselect.options[fieldselect.options.length] = new Option(data[i], data[i]);
            }

            var fieldselect = document.getElementById('select_unitnames_status');
            fieldselect.options.length = 1;
            for (var i = 0; i < data.length; i++) {
                fieldselect.options[fieldselect.options.length] = new Option(data[i], data[i]);
            }
        }
    })

}

function clear_tagnames() {
    fieldselect = document.getElementById('select_tagnames');
    fieldselect.options.length = 1;
}

$('#select_unitnames').on('change', function () {
    get_tagnames()
});



function get_tagnames() {
    var unitname = $('#select_unitnames').val();
    var fieldID = $('#select_project').val();

    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/get_tagnames',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID, unit_name: unitname }),
        success: function (data) {
            var fieldselect = document.getElementById('select_tagnames');
            fieldselect.options.length = 1;
            for (var i = 0; i < data.tagnames.length; i++) {
                fieldselect.options[fieldselect.options.length] = new Option(data.tagnames[i], data.tagnames[i]);
            }
        }
    })

}

function plot_tagname() {
    var layout = {
        plot_bgcolor: "#27293D",
        paper_bgcolor: "#27293D",
        font: { color: "#D2D2D5" }
    }

    Plotly.newPlot('div_plot_tagname', [], layout)

    var fieldID = $('#select_project').val();
    var tagname = $('#select_tagnames').val();
    var unitname = $('#select_unitnames').val();
    var starttime = document.getElementById("starttime").value;
    var endtime = document.getElementById("endtime").value;
    var timestep = parseFloat(document.getElementById("timestep").value)

    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/plot_tagnames',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID, tagname: tagname, unitname: unitname, starttime: starttime, endtime: endtime, timestep: timestep }),
        success: function (data) {

            trace = {
                x: data.x,
                y: data.y,
                name: tagname,
            }

            layout['title'] = { text: tagname }

            Plotly.addTraces('div_plot_tagname', trace);
        }
    })

}


var task_id

function run_offline_simulation() {

    start_date = document.getElementById("offlinesimstarttime").value;
    end_date = document.getElementById("offlinesimendtime").value;

    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/run_offline_sim',
        contentType: 'application/json',
        data: JSON.stringify({ start_date: start_date, end_date: end_date }),
        success: function (data) {

            task_id = data

            document.getElementById("offline_status_log").value = "Status Task ID " + task_id + ": " + "offline simulation is started"


        }
    })
}



function get_offline_status() {

    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/status_offline_sim',
        contentType: 'application/json',
        data: JSON.stringify({ task_id: task_id }),
        success: function (data) {

            document.getElementById("offline_status_log").value = "Status Task ID " + task_id + ": " + data.task_status + " - " + data.task_result


        }
    })


}

function import_raw_data() {

    $.ajax({
        type: 'GET',
        url: '/app/tagbrowser/manual_import_raw_data',
        contentType: 'application/json',
        success: function (data) {
            console.log(data)
            alert("manual import data process has been started.")
        }
    })
}


function upload_data_csv() {

    var fileInput = document.getElementById('data_csv');
    var fieldID = $('#select_project').val();

    // Check if a file is selected
    if (fileInput.files.length === 0) {
        return; // Exit the function if no file is selected
    }

    var form_data = new FormData()
    form_data.append('file', $('#data_csv')[0].files[0])
    form_data.append('field_name', fieldID)

    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/upload_data_csv',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: form_data,
        success: function (data) {
            alert(data)
        }
    })
}

$('#select_unitnames_status').on('change', function () {
    get_tagnames_status()
});


function get_tagnames_status() {

    unitname = document.getElementById("select_unitnames_status").value

    console.log(unitname)
    $.ajax({
        type: 'POST',
        url: '/app/tagbrowser/status_unit_tagnames',
        contentType: 'application/json',
        data: JSON.stringify({ unitname: unitname }),
        success: function (data) {

            tagnames = Object.keys(data.status)

            var layout = {
                plot_bgcolor: "#27293D",
                paper_bgcolor: "#27293D",
                font: {
                    color: "#D2D2D5"

                },
                yaxis: {
                    title: {
                        text: '',
                    },
                    tickvals: Array.from({ length: tagnames.length }, (_, i) => i + 1),
                    ticktext: tagnames
                },
                xaxis: {
                    title: {
                        text: 'Time',
                    },
                },
                showlegend: false,
                margin: {
                    l: 300
                }
            }

            traceall = []



            for (var i = 0; i < tagnames.length; i++) {
                var trace0 = {
                    x: [data.start_time, data.status[tagnames[i]]],
                    y: [i + 1, i + 1],
                    mode: 'lines',
                    line: {
                        color: 'rgba(0, 255, 0, 0.3)',
                        width: 10,
                        opacity: 0.5
                    },
                    name: 'available'

                };
                var trace1 = {
                    x: [data.status[tagnames[i]], data.current_time],
                    y: [i + 1, i + 1],
                    mode: 'lines',
                    line: {
                        color: 'rgba(255, 0, 0, 0.3)',
                        width: 10,
                        opacity: 0.5
                    },
                    name: 'not available'
                };

                traceall.push(trace0)
                traceall.push(trace1)

            }



            Plotly.newPlot('div_plot_tagname_status', traceall, layout)

        }
    })


}

var editor;
$(document).ready(function () {
    editor = new $.fn.dataTable.Editor({
        table: "#data-table-esp",
        fields: [{
            label: "Manufacturer:",
            name: "manufacturer"
        }, {
            label: "Pump Type:",
            name: "pumptype"
        }, {
            label: "Min. Rate:",
            name: "minrate"
        }, {
            label: "BEP Rate:",
            name: "beprate"
        }, {
            label: "Max. Rate:",
            name: "maxrate"
        }, {
            label: "Head C0:",
            name: "hC0"
        }, {
            label: "Head C1:",
            name: "hC1"
        }, {
            label: "Head C2:",
            name: "hC2"
        }, {
            label: "Head C3:",
            name: "hC3"
        }, {
            label: "Head C4:",
            name: "hC4"
        }, {
            label: "Head C5:",
            name: "hC5"
        }, {
            label: "Head C6:",
            name: "hC6"
        }, {
            label: "Head C7:",
            name: "hC7"
        }, {
            label: "BHP C0:",
            name: "bC0"
        }, {
            label: "BHP C1:",
            name: "bC1"
        }, {
            label: "BHP C2:",
            name: "bC2"
        }, {
            label: "BHP C3:",
            name: "bC3"
        }, {
            label: "BHP C4:",
            name: "bC4"
        }, {
            label: "BHP C5:",
            name: "bC5"
        }, {
            label: "BHP C6:",
            name: "bC6"
        }, {
            label: "BHP C7:",
            name: "bC7"
        },

        ]
    });

    $('#data-table-esp').DataTable({

        ajax: '../static/database/pumpdatabase.json',
        columns: [
            { data: "manufacturer" },
            { data: "pumptype" },
            { data: "minrate" },
            { data: "beprate" },
            { data: "maxrate" },
            { data: "hC0" },
            { data: "hC1" },
            { data: "hC2" },
            { data: "hC3" },
            { data: "hC4" },
            { data: "hC5" },
            { data: "hC6" },
            { data: "hC7" },
            { data: "bC0" },
            { data: "bC1" },
            { data: "bC2" },
            { data: "bC3" },
            { data: "bC4" },
            { data: "bC5" },
            { data: "bC6" },
            { data: "bC7" },
        ],
        scrollX: true,
        bSort: false,
        select: true,
        dom: "Bfrtip",
        buttons: [
            { extend: "create", editor: editor },
            { extend: "edit", editor: editor },
            { extend: "remove", editor: editor }
        ]
    });

});


$('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
    if (e.target.hash == '#espdatabase') {
        $('#data-table-esp').DataTable().columns.adjust().draw()
    }
})




function save_esp_database() {

    var table = $('#data-table-esp').DataTable();
    var tabledata = table.data().toArray();
    var objjson = { data: tabledata };

    $.ajax({

        type: 'POST',
        url: '/app/tagbrowser/save_esp_database',
        contentType: 'application/json',
        data: JSON.stringify({ tabledata: objjson}),
        success: function (data) {
            alert(data);
        }
    });

}