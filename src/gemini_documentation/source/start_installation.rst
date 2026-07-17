Installation
===========================

.. _gemini-suite-setup:

GEMINI Suite Setup
--------------------

GEMINI Digital Twin is deployed as a Docker-based stack. This makes setup,
replication, and migration straightforward for both on-premise and cloud
environments.

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
          gemini_module:
              image: ghcr.io/gemini-digital-twin/gemini-suite:MVP_V3
              env_file:
                  - .env
              environment:
                  - DOCKER_MODE=MODULE
              volumes:
                  - project-db:/opt/gemini-suite/gemini-project
              depends_on:
                  - influxdb
              restart: unless-stopped
              networks:
                  - gemini


          gemini_gui:
              image: ghcr.io/gemini-digital-twin/gemini-suite:MVP_V3
              ports:
                  - 5101:5101
              env_file:
                  - .env
              environment:
                  - DOCKER_MODE=GUI
              restart: unless-stopped
              volumes:
                  - project-db:/opt/gemini-suite/gemini-project
              depends_on:
                  - mysqldb
                  - influxdb
                  - mongodb
                  - redis
                  - chromadb
                  - ollama
              networks:
                  - gemini

          gemini_celery:
              image: ghcr.io/gemini-digital-twin/gemini-suite:MVP_V3
              env_file:
                  - .env
              environment:
                  - PYTHONUNBUFFERED=1
                  - DOCKER_MODE=CELERY
              restart: unless-stopped
              volumes:
                  - project-db:/opt/gemini-suite/gemini-project
              depends_on:
                  - redis
              networks:
                  - gemini

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
            env_file:
              - .env
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
      project-db:
      ollama_data:


Services in this ``docker-compose.yml``:

#. GEMINI Module
    Runs real-time calculation modules. Shares ``project-db`` with other GEMINI
    services and reads real-time data from InfluxDB.

#. GEMINI User interface (GUI)
    Hosts the web interface. Depends on MySQL, InfluxDB, MongoDB, Redis,
    ChromaDB, and Ollama.

#. GEMINI Celery
    Handles asynchronous/background tasks and scheduled workflows.

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






