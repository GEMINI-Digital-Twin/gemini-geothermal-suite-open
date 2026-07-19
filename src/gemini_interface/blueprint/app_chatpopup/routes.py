"""
Chat Popup Application Routes.

=============================

This module handles AI-powered chat interface with RAG (Retrieval-Augmented Generation) capabilities
including message processing and response generation.
"""

import os
import time

from celery import Celery
from flask import Blueprint, current_app, jsonify, request

from gemini_application.chatpopup.chatpopup import ChatPopup
from gemini_interface.blueprint.celerytasks import rag_generate_response

# Create the chat popup application blueprint
app_chatpopup = Blueprint("app_chatpopup", __name__)

# Initialize Celery for background task processing
celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)

# Global application instance for RAG operations
app_instance = None


@app_chatpopup.route("/app/chatpopup/load_plant", methods=["POST"])
def load_plant():
    """Load a plant/project into the chat popup application instance."""
    global app_instance

    app_instance = ChatPopup()

    app_instance.load_plant(current_app.config["GEMINI_PROJECT_FOLDER"], request.json["field_name"])

    return "OK"


def env_bool(name: str, default: bool = False) -> bool:
    """Read an environment variable and interpret it as a boolean.

    Returns `default` if the variable is not set. Truthy values are
    case-insensitive and include: "1", "true", "yes", "y", and "on".
    """
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_parameters():
    """Get configuration parameters for RAG and LLM integration."""
    # Validate app_instance and plant name
    if not app_instance or not getattr(app_instance, "plant", None):
        return jsonify({"error": "Plant not loaded. Call /load_plant first."}), 400

    parameters = dict()
    parameters["langchain_api_key"] = os.getenv("LANGCHAIN_API_KEY")
    parameters["docs_dir"] = os.path.join(
        app_instance.plant.project_path, app_instance.plant.name, "rag_data"
    )
    parameters["ollama_llm_model"] = os.getenv(
        "LLM_MODEL_VERSION", "llama3.2"
    )  # Fast-->llama3.2, Accurate-->mistral-nemo
    parameters["ollama_translation_llm"] = os.getenv(
        "TRANSLATION_LLM_MODEL", "zongwei/gemma3-translator:4b"
    )
    parameters["ollama_embeddings_model"] = os.getenv(
        "EMBED_MODEL_VERSION", "snowflake-arctic-embed"
    )
    parameters["azure_openai"] = env_bool("AZURE_OPENAI", False)
    parameters["azure_openai_key"] = os.getenv("AZURE_OPENAI_KEY")
    parameters["azure_openai_host"] = os.getenv(
        "AZURE_OPENAI_HOST", "https://geminidigitaltwinazureopenai.openai.azure.com/"
    )

    if parameters["azure_openai"] and not parameters["azure_openai_key"]:
        raise RuntimeError("AZURE_OPENAI_KEY must be set when AZURE_OPENAI=true")

    # RAG parameters
    if parameters["azure_openai"]:
        parameters["chunk_size"] = 512
        parameters["collection_name"] = "gemini_rag_collection_openai_" + app_instance.plant.name
    else:
        parameters["chunk_size"] = 200
        parameters["collection_name"] = "gemini_rag_collection_" + app_instance.plant.name

    parameters["chunk_overlap"] = 40
    parameters["retrieve_candidates"] = 60
    parameters["mmr_lambda"] = 0.75
    parameters["max_context_chunks"] = 10
    parameters["max_context_chars"] = 16000
    parameters["embedding_batch_size"] = 16
    parameters["chroma_add_batch_size"] = 512
    parameters["embedding_chunk_size"] = 140
    parameters["embedding_chunk_overlap"] = 30
    parameters["debug"] = False
    parameters["chromadb_use_http"] = True
    parameters["num_relevant_docs"] = 18
    parameters["similarity_threshold"] = 0.1

    # Connection to docker containers
    parameters["chromadb_port"] = int(os.getenv("CHROMADB_PORT"))
    parameters["chromadb_host"] = os.getenv("CHROMADB_HOST")
    parameters["chromadb_use_http"] = True
    parameters["ollama_port"] = int(os.getenv("OLLAMA_PORT"))
    parameters["ollama_host"] = os.getenv("OLLAMA_HOST")
    return parameters


@app_chatpopup.route("/app/chatpopup/initialize_rag", methods=["POST"])
def initialize_rag():
    """Initialize the RAG system for chat functionality."""
    # Initialize
    parameters = get_parameters()

    app_instance.init_parameters(parameters)

    # Load documents
    tic = time.time()
    # app_instance.initialize_model()
    toc = time.time()
    elapsed_time = toc - tic
    print(f"App: INITIALIZATION COMPLETED ({elapsed_time:.5f} s)")

    # Load documents and prepare embeddings
    tic = time.time()
    app_instance.update_data()
    toc = time.time()
    elapsed_time = toc - tic
    print(f"App: DATABASE UPDATED ({elapsed_time:.5f} s)")

    return jsonify({"message": "RAG initialization successful"}), 200


@app_chatpopup.route("/app/chatpopup/send_message", methods=["POST"])
def send_message():
    """Send a message to the RAG system for processing."""
    user_message = request.json["message"]
    parameters = get_parameters()
    # Process the message
    # response = app_instance.process_prompt(user_message)
    task = rag_generate_response.delay(parameters, user_message)

    task_id = str(task.id)
    return jsonify({"task_id": task_id}), 202


@app_chatpopup.route("/app/chatpopup/get_rag_response", methods=["POST"])
def get_rag_response():
    """Get the RAG response from the background task."""
    task_id = request.json["task_id"]

    task_result = celery.AsyncResult(task_id)
    status = task_result.status
    result_data = None  # Initialize result_data to None

    if status == "SUCCESS":
        result_data = task_result.result
    elif status == "FAILURE":
        result_data = str(task_result.result)
        print(f"ERROR: Task {task_id} failed with result: {result_data}")

    result = {"task_id": task_id, "task_status": status, "task_result": result_data}

    return result
