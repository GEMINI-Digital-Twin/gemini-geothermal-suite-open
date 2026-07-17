Installation
===========================

.. tip::
   New to GEMINI or just want to try it out quickly? See the :ref:`quickstart-installation` page
   for a shorter, beginner-friendly version of these instructions. Come back here for full detail
   on every service, environment variable, and the local development workflow.

.. _gemini-suite-setup:

GEMINI Suite Setup
--------------------

GEMINI Digital Twin relies on several supporting services (Grafana, MySQL, InfluxDB, Redis,
MongoDB, ChromaDB and, optionally, Ollama) that are packaged together in this repository's
``docker-compose.yml``. It is needed to have a basic knowledge of Docker to install this tool.
Several tutorial can be found in the internet (`example <https://medium.com/@sayalishewale12/docker-compose-and-essential-commands-the-ultimate-guide-to-streamlining-your-container-workflow-8018ca171300>`_)

Basic Docker knowledge is recommended. For Docker fundamentals, refer to
official Docker documentation.

Prerequisites:

* Docker Desktop: https://docs.docker.com/engine/install/
* Docker Compose: https://docs.docker.com/compose/install/

docker-compose.yml
 .. code-block::
    :linenos:

    networks:
      gemini:

    services:
          grafana:
            image: grafana/grafana:latest
            ports:
                - 3000:3000
            env_file:
                - .env
            volumes:
                - grafana-storage:/var/lib/grafana
            depends_on:
                - influxdb
            restart: unless-stopped
            networks:
                - gemini

          mysqldb:
            image: mysql:8.0
            ports:
              - 3306:3306
            env_file:
              - .env
            volumes:
              - mysqldb_data-storage:/data/db
              - mysqldb_var_lib-storage:/var/lib/mysql
            restart: unless-stopped
            networks:
              - gemini

          influxdb:
            image: influxdb:latest
            ports:
              - 8086:8086
              - 8998:8088
            env_file:
              - .env
            volumes:
              - influxdb-storage:/var/lib/influxdb
              - influxdb2-storage:/var/lib/influxdb2
              - influxdb2etc-storage:/etc/influxdb2
            restart: unless-stopped
            networks:
              - gemini

          redis:
            image: redis:6-alpine
            ports:
              - 6379:6379
            env_file:
              - .env
            restart: unless-stopped
            networks:
              - gemini

          mongodb:
            image: mongo:latest
            ports:
              - 27017:27017
            env_file:
              - .env
            volumes:
              - mongo-storage:/data/db
            restart: unless-stopped
            networks:
              - gemini

          chromadb:
            image: chromadb/chroma
            ports:
              - 8000:8000
            env_file:
              - .env
            networks:
              - gemini
            volumes:
              - chroma-data:/data
            restart: unless-stopped

          ollama:
            container_name: ollama
            image: ollama/ollama:latest
            ports:
              - 11434:11434
            environment:
               - OLLAMA_HOST=0.0.0.0:11434
            volumes:
              - ollama_data:/root/.ollama
            restart: unless-stopped
            command: serve

    volumes:
      mysqldb_data-storage:
      mysqldb_var_lib-storage:
      grafana-storage:
      influxdb-storage:
      influxdb2-storage:
      influxdb2etc-storage:
      mongo-storage:
      chroma-data:
      ollama_data:

There are several services in this docker-compose.yml file:

#. Grafana
    Visualization platform for time-series dashboards and alerts.

#. MySQLDB
    Relational database for user, configuration, and project metadata.

#. InfluxDB
    Time-series database used for geothermal operational data.

#. Redis
    In-memory broker/backend for asynchronous task queues and task results.

#. MongoDB
    Document database used for uploaded report and document storage.

#. ChromaDB
    Vector database used by RAG workflows for semantic document retrieval.

#. Ollama
    Runtime for local LLM and embedding model execution.

Starting the stack
~~~~~~~~~~~~~~~~~~

Run:

.. code-block:: bash

   docker-compose up -d

After startup, open the GEMINI GUI on the configured frontend port.

.. _local-development-setup:

Local Development Setup
------------------------

Besides running the supporting services with the ``docker-compose.yml`` described above, the
GEMINI application itself can be run directly from source for development purposes, using Poetry
for dependency management.

Prerequisites
~~~~~~~~~~~~~

Make sure the following tools are installed on your machine before you start:

* **Python 3.11** (the project pins ``python = "^3.11"`` in ``pyproject.toml``)
* **Poetry** (https://python-poetry.org/) for dependency management (installed automatically by
  the install scripts below, or install manually with ``pip install poetry``)
* **Docker** and **Docker Compose** (to run the supporting services: Grafana, MySQL, InfluxDB,
  Redis, MongoDB, ChromaDB and Ollama)
* **Git** for cloning the repository

Optionally, **Ollama** (https://ollama.com/) can be used to run the LLM/embedding models locally
instead of Azure OpenAI. The ``ollama`` service is included in ``docker-compose.yml`` and started
by default along with the other supporting services.

1. Clone the repository
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open.git
   cd gemini-geothermal-suite-open

2. Configure environment variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This repo uses a single ``.env`` file in the repo root, read both by Docker Compose (via
``env_file:`` in ``docker-compose.yml``) and automatically, via ``python-dotenv``, by every local
Python entry point (``src/gemini_interface/app.py``, ``src/gemini_framework/app.py``, and the
Celery worker). You do not need to manually export variables into your shell before running
``poetry run python src/gemini_interface/app.py`` -- ``.env`` is loaded automatically as soon as
the process starts.

Create it from the template:

.. code-block:: bash

   cp .env.template .env

On Windows (PowerShell):

.. code-block:: powershell

   Copy-Item .env.template .env

.. warning::
   Hostnames depend on how you run the app. How you set hostnames like ``GEMINI_MYSQLDB_URL``,
   ``MONGODB_HOST``, ``INFLUXDB_URL``, ``CELERY_BROKER_URL``, ``CHROMADB_HOST`` and ``OLLAMA_HOST``
   depends on where the Flask app / Celery worker process runs, not on where the supporting
   services run:

   * **Running the app locally with** ``poetry run`` (the default/recommended workflow for
     development) -- your Python process runs outside Docker's network, so these variables must
     point at ``localhost`` plus the host-published port from ``docker-compose.yml`` (e.g.
     ``GEMINI_MYSQLDB_URL=localhost``, ``MONGODB_HOST=localhost``,
     ``INFLUXDB_URL=http://localhost:8086``, ``CELERY_BROKER_URL=redis://localhost:6379/0``,
     ``CHROMADB_HOST=localhost``, ``OLLAMA_HOST=localhost``).
   * **Running everything inside Docker** (the ``gemini_gui``/``gemini_module``/``gemini_celery``
     images described above) -- the app process runs inside the same ``gemini`` Docker network as
     the other services, so these variables must use the Docker Compose service names instead
     (e.g. ``GEMINI_MYSQLDB_URL=mysqldb``, ``MONGODB_HOST=mongodb``,
     ``INFLUXDB_URL=http://influxdb:8086``, ``CELERY_BROKER_URL=redis://redis:6379/0``).

   Mixing these up is the most common setup error -- trying to resolve a Docker service name
   (e.g. ``mysqldb``) from a locally-run process fails with ``getaddrinfo failed`` (``Can't
   connect to MySQL server on 'mysqldb'``), since that name doesn't exist in your host's DNS.

Also make sure to set:

.. code-block:: bash

   GRAFANA_URL=http://localhost:3000

This is required for the in-app Timeseries Viewer tab (which embeds Grafana in an iframe) to work
at all -- without it, that tab shows a "Not Found" page.

Then edit ``.env`` and fill in the required values, including ``GEMINI_PLANT``, the InfluxDB
connection settings, ``GEMINI_FRONTEND_PORT``, the MySQL/MongoDB/Redis connection settings, the
default admin credentials (``GEMINI_ADMIN_EMAIL``, ``GEMINI_ADMIN_NAME``, ``GEMINI_ADMIN_PASSWORD``),
the LLM/embedding model names, the ChromaDB and Ollama connection settings, the Grafana
configuration, and the MySQL/InfluxDB/MongoDB container initialization variables.

.. warning::
   Never commit your ``.env`` file. It contains credentials and secrets and is already excluded
   via ``.gitignore``. If you use an LLM provider such as Azure OpenAI, also set the corresponding
   ``AZURE_OPENAI_HOST``/``AZURE_OPENAI_KEY``/``AZURE_OPENAI`` variables in ``.env``.

3. Install Python dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The project uses Poetry for dependency management. Convenience scripts are provided under
``ci/windows`` and ``ci/linux``.

**Windows:**

.. code-block:: powershell

   ci\windows\run_installation.bat        # runtime dependencies only
   ci\windows\run_installation_dev.bat    # runtime + development dependencies (tests, linters, docs)

**Linux/macOS:**

.. code-block:: bash

   bash ci/linux/run_installation.sh

These scripts run the equivalent of:

.. code-block:: bash

   python -m pip install --upgrade pip
   pip install poetry
   poetry lock
   poetry install            # add "--only main" to skip dev dependencies

4. Start the supporting services (Docker)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The suite depends on several backing services (Grafana, MySQL, InfluxDB, Redis, MongoDB,
ChromaDB, and optionally Ollama), defined in ``docker-compose.yml``. Start them with:

.. code-block:: bash

   docker compose up -d

or, using the provided script on Windows:

.. code-block:: powershell

   ci\windows\run_docker.bat

This will start Grafana (port 3000, dashboards), MySQL (port 3306, relational data), InfluxDB
(ports 8086/8088, time-series process data), Redis (port 6379, Celery broker/result backend),
MongoDB (port 27017, document storage) and ChromaDB (port 8000, vector store for the AI chat
assistant).

5. Run the application
~~~~~~~~~~~~~~~~~~~~~~

Start the Flask web interface (entry point is ``src/gemini_interface/app.py``):

.. code-block:: bash

   poetry run python src/gemini_interface/app.py

``.env`` is loaded automatically (via ``python-dotenv``) as soon as the process starts, so no
manual env export is required -- just make sure ``.env`` exists in the repo root and the Docker
Compose services from step 4 are already running.

The app reads ``GEMINI_FRONTEND_PORT`` from ``.env`` (defaults are only applied if the variable
is set) and listens on ``0.0.0.0``. Once running, open your browser at:

.. code-block::

   http://localhost:<GEMINI_FRONTEND_PORT>

.. warning::
   Always use ``http://localhost:<port>``, not ``http://127.0.0.1:<port>``. Even though they
   point at the same machine, browsers treat ``localhost`` and ``127.0.0.1`` as different
   origins. Since ``GRAFANA_URL`` is set to ``http://localhost:3000``, accessing the app via
   ``127.0.0.1`` will break the embedded Grafana session in the Timeseries Viewer tab (it keeps
   looping back to the login screen).

Log in using the ``GEMINI_ADMIN_EMAIL`` / ``GEMINI_ADMIN_PASSWORD`` configured in your ``.env``
file.

Accessing Grafana from the Timeseries Viewer
++++++++++++++++++++++++++++++++++++++++++++

The Timeseries Viewer tab embeds Grafana in an iframe pointing at ``GRAFANA_URL``. Two things
are required for this to work correctly:

1. **Use consistent hostnames.** Access the whole app via
   ``http://localhost:<GEMINI_FRONTEND_PORT>`` (not ``http://127.0.0.1:...``), matching the
   hostname used in ``GRAFANA_URL=http://localhost:3000``. Mismatched hostnames are treated as
   different origins by the browser, so Grafana's login session won't be visible inside the
   iframe and it will keep bouncing back to the login form.
2. **Configure Grafana's own InfluxDB data source using the Docker service name**, not
   ``localhost``. Grafana runs inside the ``gemini`` Docker network, so from inside the Grafana
   container, ``localhost`` refers to the Grafana container itself, not your host machine. When
   adding the InfluxDB data source in Grafana's UI (``Connections`` -> ``Data sources``), use
   ``http://influxdb:8086/`` as the URL.

Configuring a plant
~~~~~~~~~~~~~~~~~~~~

Plant-specific configuration lives under ``gemini-project/``. Each plant is a folder containing a
``plant.conf`` file and ``.param`` files describing individual assets (reservoir, wells, pumps,
heat exchangers, filters, degassers, etc.), plus a ``diagram.json`` describing the plant topology.
A ``_template`` folder is provided with blank templates for each asset type to help you set up a
new plant. Set ``GEMINI_PLANT`` in your ``.env`` to the name of the folder you want to load (e.g.
``geothermal_example``).

Running tests, linting and formatting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Tests** (pytest with coverage):

.. code-block:: bash

   poetry run pytest -v --cov -p no:faulthandler
   # or
   ci\windows\run_test.bat        # Windows
   bash ci/linux/run_test.sh      # Linux

**Linting** (flake8, black, isort in check mode):

.. code-block:: powershell

   ci\windows\run_linter.bat

.. code-block:: bash

   bash ci/linux/run_linter.sh

**Auto-formatting** (black + isort, Windows only script provided):

.. code-block:: powershell

   ci\windows\run_formatting.bat

Background workers (Celery/Flower)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Some features (e.g. asynchronous reports, translations) run as Celery tasks against the Redis
broker started via Docker Compose.

Start a Celery worker:

.. code-block:: powershell

   ci\windows\run_celery.bat

.. code-block:: bash

   celery --app src.gemini_interface.blueprint.celerytasks.celery worker --loglevel=info

Start the Flower monitoring dashboard:

.. code-block:: powershell

   ci\windows\run_flower.bat

.. code-block:: bash

   poetry run celery -A src.gemini_interface.blueprint.celerytasks.celery flower

.. _chat-assistant-setup:

Chat Assistant Setup
--------------------

The Chat Assistant setup is mostly automatic.

The application uses Ollama to host LLM and embedding models. Ollama starts in
its own container when you run:

.. code-block:: bash

   docker-compose up

The provided compose file starts Ollama together with the other required GEMINI
services.

After all containers are up, install required models by running
``pull_ollama_models.bat``. Do this only after ``docker-compose up`` completes.

Model configuration
~~~~~~~~~~~~~~~~~~~

The Chat Assistant supports model switching via environment variables in the
``gemini_gui`` service:

.. code-block:: bash

   LLM_MODEL_VERSION=llama3.2
   EMBED_MODEL_VERSION=snowflake-arctic-embed

Only Ollama-supported models can be used.

If you choose non-default models, make sure they are pulled into the Ollama
container.

Example (pull ``mistral-nemo``):

.. code-block:: bash

   docker exec -it ollama ollama pull mistral-nemo

Recommended Models
~~~~~~~~~~~~~~~~~~

The following models were validated during development and are recommended:

**Response Generation Models (LLM_MODEL_VERSION)**

- llama3.2
  A lightweight and fast model that provides good performance with low latency.

- mistral-nemo
  A larger and more accurate model that returns responses more slowly.

**Embedding Model (EMBED_MODEL_VERSION)**

- snowflake-arctic-embed
  The recommended model for generating embeddings used by the RAG pipeline.

These defaults provide a practical balance between latency and response quality.






