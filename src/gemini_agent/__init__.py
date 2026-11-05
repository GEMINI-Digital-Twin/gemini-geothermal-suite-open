"""Agentic geothermal heating & cooling design workflow on top of GEMINI.

Layers (see DESIGN notes in the PR description):

- ``gemini_agent.physics``: brief/site model, GEMINI-based well performance,
  daily plant dispatch and the annual (365-day) driver.
- ``gemini_agent.tools``: typed, compact tools the LLM agents call.
- ``gemini_agent.agents``: deep-agent orchestration (open-weight LLMs via Ollama).
- ``gemini_agent.ui``: CLI and web cockpit.

Guiding rule: the LLM decides, code computes, the verifier signs off. Every
engineering number originates from a tool call and is recorded in the fact ledger.
"""
