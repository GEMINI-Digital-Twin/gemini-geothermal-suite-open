"""Command-line chat with the design agent.

Examples::

    # local Ollama (default): ollama pull qwen3:8b
    python -m gemini_agent

    # one question, then exit
    python -m gemini_agent --ask "Which design meets demand at the lowest cost?"

    # any OpenAI-compatible endpoint; key from the environment, never from a file
    set GEMINI_AGENT_API_KEY=...
    python -m gemini_agent --provider openrouter --model qwen/qwen-2.5-72b-instruct

Transcripts (JSONL + Markdown with token tables) are written to
``<workspace>/transcripts/``.
"""

import argparse
import sys

from gemini_agent.agent import DesignAgent
from gemini_agent.config import AgentConfig


def main(argv=None):
    """Run the CLI."""
    parser = argparse.ArgumentParser(prog="gemini_agent", description=__doc__.splitlines()[0])
    parser.add_argument("--config", help="JSON config file")
    parser.add_argument("--provider", help="ollama, llamacpp, vllm, openrouter")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--workspace")
    parser.add_argument("--session", help="transcript name")
    parser.add_argument("--no-native-tools", action="store_true", help="tools via prompt + JSON")
    parser.add_argument("--ask", action="append", help="question(s) to ask, then exit")
    args = parser.parse_args(argv)

    config = AgentConfig.load(
        args.config,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        workspace=args.workspace,
        native_tool_calling=False if args.no_native_tools else None,
    )
    agent = DesignAgent(config, session_name=args.session)
    print(f"GEMINI design agent - model {config.model} at {config.base_url}")
    questions = args.ask or []
    interactive = not questions
    while True:
        if questions:
            text = questions.pop(0)
            print(f"\nyou> {text}")
        elif interactive:
            try:
                text = input("\nyou> ").strip()
            except EOFError:
                break
            if text.lower() in ("exit", "quit", ""):
                break
        else:
            break
        reply = agent.ask(text)
        print(f"\nagent ({reply.kind})> {reply.text}")
        print(
            f"   [{reply.llm_calls} LLM calls, {reply.prompt_tokens} prompt + "
            f"{reply.completion_tokens} completion tokens]"
        )
    jsonl, md = agent.close()
    print(f"\nTranscript: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
