.. _quickstart-installation:

Quick Start (Beginners)
===========================

This page gives you the shortest path to get GEMINI Digital Twin running locally. If you want to
understand what each supporting service does, configure a custom plant, or run tests/linting, see
the full :ref:`gemini-suite-setup` and :ref:`local-development-setup` guides instead.

What you need
--------------

* Docker Desktop installed and running (https://docs.docker.com/desktop/)
* Python 3.11
* Git (https://git-scm.com/downloads)

Steps
------

1. Clone the repository:

.. code-block:: bash

   git clone https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open.git
   cd gemini-geothermal-suite-open

2. Create your environment file from the template:

.. code-block:: bash

   cp .env.template .env

Open ``.env`` in a text editor and fill in at least these values:

.. code-block::

   GEMINI_PLANT=geothermal_example
   GEMINI_FRONTEND_PORT=5101
   GEMINI_MYSQLDB_URL=localhost
   MONGODB_HOST=localhost
   INFLUXDB_URL=http://localhost:8086
   CELERY_BROKER_URL=redis://localhost:6379/0
   CHROMADB_HOST=localhost
   OLLAMA_HOST=localhost
   GEMINI_ADMIN_EMAIL=admin@example.com
   GEMINI_ADMIN_NAME=admin
   GEMINI_ADMIN_PASSWORD=change-me
   GRAFANA_URL=http://localhost:3000

3. Start the supporting services (Grafana, MySQL, InfluxDB, Redis, MongoDB, ChromaDB, Ollama):

.. code-block:: bash

   docker compose up -d

4. Install Python dependencies and run the app:

.. code-block:: bash

   pip install poetry
   poetry install
   poetry run python src/gemini_interface/app.py

5. Open the app in your browser:

.. code-block::

   http://localhost:5101

Log in with the ``GEMINI_ADMIN_EMAIL`` / ``GEMINI_ADMIN_PASSWORD`` you set in step 2.

Need more?
-----------

* Full explanation of every service, environment variable, and hostname rules: :ref:`gemini-suite-setup`
* Running the app from source with Poetry for development: :ref:`local-development-setup`
* Setting up the AI Chat Assistant models: :ref:`chat-assistant-setup`
