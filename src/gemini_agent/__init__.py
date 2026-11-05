"""Agentic design assistant for the GEMINI GeoHackathon heating + cooling challenge.

The language model plans and talks; every number it reports must come
from a ``gemini_design`` / ``gemini_simulator`` run that passed the
physics gate (:mod:`gemini_agent.physics_gate`). The LLM backend is any
OpenAI-compatible chat endpoint (Ollama, vLLM, llama.cpp server,
OpenRouter, ...), so open-weight models are the default.

Entry points: :class:`gemini_agent.agent.DesignAgent` and the CLI
``python -m gemini_agent``.
"""
