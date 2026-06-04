Time Series Viewer
===========================


Setup Database Connection
---------------------------

* Click Connection
* Click Add new connection
* Search "influxdb"
* Click Data Source InfluxDB
* Click Add New Data Source

.. image:: images/database_setup_connection_1.JPG
    :width: 100%

* Fill the database name
* Choose Query language "Flux"
* add URL http://influxdb:8086
* toggle Basic auth

.. image:: images/database_setup_connection_2.JPG
    :width: 100%

* Fill Basic Auth Details

    * Username: gemini-user
    * Password: gemini-password

* Fill InfluxDB Details

    * Organization: TNO
    * Token: <create token InfluxDB> (Follow the steps below to create a token)
    * Default Bucket: gemini-project

* Click Save & test

.. image:: images/database_setup_connection_3.JPG
    :width: 100%

* Create Token Influx DB
    * Using your browser, log in to <yourdomain>:8086, where <yourdomain> is the cloud address you use to access Gemini
    * Fill username and password (same as the Basic Auth Details)
    * Generate API token
    * Click All Access API Token
    * Fill Description, e.g. gemini-token
    * Copy the API token and put in InfluxDB Details

.. image:: images/database_setup_connection_4.JPG
    :width: 100%


Create Dashboard
---------------------------
* Click "New" button
* Click "Add visualization" button

.. image:: images/create_dashboard_1.JPG
    :width: 100%

* Select data source influxdb
* if you dont see any data source, please follow section Setup Database Connection

.. image:: images/create_dashboard_2.JPG
    :width: 100%

* Select Time Series. There are several chart style e.g. bar chart, gauge, pie chart, etc.
* Fill Title
* In box A, fill the query code. It is based on FluxQL syntax. See the example below.

.. code-block::

    from(bucket: "gemini-project")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => r["_measurement"] == "HAL")
    |> filter(fn: (r) => r["asset_name"] == "esp_e74b")
    |> filter(fn: (r) => r["_field"] == "esp_inlet_pressure.measured")
    |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
    |> yield(name: "mean")

* Parameter explanation:
    * _measurement : it is the project name
    * asset_name : it is the component name
    * _field : it is the tagname that we want to plot.


.. image:: images/create_dashboard_3.JPG
    :width: 100%


Save Dashboard
---------------------------

* Click "share" button
* Click Export tab
* Click "Save to file" button

.. image:: images/save_dashboard.JPG
    :width: 100%


Import Dashboard
---------------------------
* Click "New" dropdown button
* Click Import
* Click "Save to file" button

.. image:: images/import_dashboard.JPG
    :width: 100%

* Upload JSON file from template folder: gemini-user-interface/src/static/grafana_template
* or copy paste JSON text in the box

.. image:: images/import_dashboard_2.JPG
    :width: 100%

