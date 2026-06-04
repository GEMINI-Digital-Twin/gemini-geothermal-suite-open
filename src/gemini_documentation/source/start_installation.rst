Installation
===========================

.. _gemini-suite-setup:

GEMINI Suite Setup
--------------------

GEMINI Digital Twin is compiled as docker container, thus it will be easy to setup and replicate to
a server (on premises or cloud). It is needed to have a basic knowledge of Docker to install this tool.
Several tutorial can be found in the internet (`example <https://medium.com/@sayalishewale12/docker-compose-and-essential-commands-the-ultimate-guide-to-streamlining-your-container-workflow-8018ca171300>`_)

The pre-requisite software of this installation are:

* Docker Desktop (https://docs.docker.com/engine/install/)
* Docker Compose (https://docs.docker.com/compose/install/)

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


There are several services in this docker-compose.yml file:

#. GEMINI Module
    This container runs the real-time modules when is called. The container shares volume of
    project-db with other container to have a common project data. The project name should be
    given in GEMINI_PLANT environment variable. This container depends on InfluxDB container to
    access the real-time data.

#. GEMINI User interface (GUI)
    This container provides the web user interface of GEMINI. This container depends on MySQLDB container
    to access user authentication and project. The port number can be defined in GEMINI_FRONTEND_PORT
    environment variable. The container shares volume of project-db with other container to have a
    common project data and volume of doc-db to access the documentation.

#. GEMINI Celery
    This container provides python celery that enables asynchronous, background execution of time-consuming task.
    It prevents long-running processes from blocking web application user interfaces. It also provides
    task scheduling and horizontal scaling, supporting brokers like RabbitMQ or Redis.

#. Grafana
    This is a multi-platform open source analytics and interactive visualization web application.
    It can produce charts, graphs, and alerts for the web when connected to supported data sources.
    It is used to visualize the time series data.

#. MySQLDB
    It is an open-source relational database management system. To handle several data structured of
    GEMINI.

#. InfluxDB
    It is an open-source time series database. It is used for storage and retrieval of time series
    data in fields such as operations monitoring, application metrics, Internet of Things sensor
    data, and real-time analytics. We use this database to store time series data from Geothermal
    assets.

#. Redis
    Redis acts primarily as a high-performance message broker and result backend. It enables
    asynchronous task processing by storing task queues, facilitating communication between GEMINI app
    and workers, and storing task execution results. Redis provides rapid, in-memory storage, allowing
    workers to pick up tasks instantly and enhancing system scalability.

#. mongodb
    MongoDB is a document-oriented NoSQL database designed for high-volume storage, flexibility,
    and scalability. It stores data in JSON-like documents (BSON) rather than tables, allowing for
    rapid development, easy handling of unstructured/semi-structured data, and horizontal scaling
    through sharding. We use this database to store the document uploaded by user.

#. chromadb
    ChromaDB is an open-source vector database designed to store, manage, and query high-dimensional
    vector embeddings, making it a critical component in AI applications, particularly those utilizing
    Retrieval-Augmented Generation (RAG). It serves as a specialized, efficient repository for semantic
    data (text, images, etc.) to enhance the performance of Large Language Models (LLMs).

#. Ollama
    An open-source framework for installing and running Llama or other open-source LLMs.

.. _chat-assistant-setup:

Chat Assistant Setup
--------------------

The Chat Assistant setup process is designed to be simple and mostly automated.

The application uses Ollama to run Large Language Models (LLMs).
Ollama is started automatically inside a separate Docker container when the following command is executed:

.. code-block:: bash

   docker-compose up

The provided docker-compose.yml file creates and starts the Ollama container, among other necessary containers for the GEMINI digital twin.
This container hosts the LLM and embedding models used by the Retrieval-Augmented Generation (RAG) application.

After the containers are running, the required Ollama models can be installed by double-clicking the pull_ollama_models.bat file.
This step must be performed only after the docker-compose up command has completed successfully.

Model configuration
~~~~~~~~~~~~~~~~~~~

The Chat Assistant supports switching between different LLMs using environment variables defined for the gemini_gui container. To change the models, update the following variables:

.. code-block:: bash

   LLM_MODEL_VERSION=llama3.2
   EMBED_MODEL_VERSION=snowflake-arctic-embed

Only Ollama-supported models are allowed, as the Ollama client is integrated with the RAG application.

When selecting models other than the recommended defaults, it is important to ensure that the chosen models are also downloaded into the Ollama container.

For example, if you want to use ``mistral-nemo`` instead of ``llama3.2``, you can install it while the container is running by executing the following command in a command prompt window:

.. code-block:: bash

   docker exec -it ollama ollama pull mistral-nemo

Recommended Models
~~~~~~~~~~~~~~~~~~

The following models were tested during development and are recommended defaults.

**Response Generation Models (LLM_MODEL_VERSION)**

- llama3.2
  A lightweight and fast model that provides good performance with low latency.

- mistral-nemo
  A larger and more accurate model that returns responses more slowly.

**Embedding Model (EMBED_MODEL_VERSION)**

- snowflake-arctic-embed
  The recommended model for generating embeddings used by the RAG pipeline.

These models provide a balanced trade-off between speed and accuracy and are the recommended defaults in this documentation.







