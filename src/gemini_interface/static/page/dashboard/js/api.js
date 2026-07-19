function loadURL() {
    var fieldID = $('#select_project').val();

    $.ajax({
        type: 'POST',
        url: '/dashboard/get_url',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {
            if (!data == '') {
                if (window.location.protocol == "http:") {
                    port = ":3000"
                } else {
                    port = ":3001"
                }

                custom_url = window.location.protocol + "//" + window.location.hostname + port + "/" + data

                document.getElementById('iFrame_dashboard').src = custom_url
            }
        }
    })

}

loadURL()