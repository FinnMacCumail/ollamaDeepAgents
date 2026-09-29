"""Llama.cpp model configuration and initialization for DeepAgents."""

import os
from typing import Any

from langchain_openai import ChatOpenAI

from ..utils.logging import get_logger

logger = get_logger(__name__)


class LlamaCppChatOpenAI(ChatOpenAI):
    """ChatOpenAI that keeps llama.cpp's `timings` block.

    llama-server appends a non-OpenAI `timings` object (prompt_n, prompt_per_second,
    predicted_per_second, ...) to the final streamed chunk of every call, the same chunk
    that carries `usage`. The base class drops unknown fields; this override copies it into
    `response_metadata["timings"]` so callers get real prefill/decode tok/s instead of
    wall-clock guesses. Purely additive: everything else is the base behaviour.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> Any:
        gen = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen is not None and isinstance(chunk, dict) and chunk.get("timings"):
            gen.message.response_metadata["timings"] = chunk["timings"]
        return gen


def create_llamacpp_model(
    model_name: str | None = None,
    temperature: float = 0.0,
    validate: bool = True,
) -> ChatOpenAI:
    """
    Create and configure a llama.cpp model for use with DeepAgents.

    Uses ChatOpenAI pointing at llama.cpp server's OpenAI-compatible API endpoint.

    Args:
        model_name: Name of the GGUF model file (e.g., "Qwen_Qwen3-14B-Q5_K_M.gguf")
        temperature: Temperature for model generation (0.0 = deterministic)
        validate: Whether to validate the model on initialization

    Returns:
        Configured ChatOpenAI instance pointing at llama.cpp server

    Raises:
        Exception: If model creation fails
    """
    # Use environment variable with fallback
    model = model_name or os.getenv("LLAMACPP_MODEL", "Qwen_Qwen3-14B-Q5_K_M.gguf")
    base_url = os.getenv("LLAMACPP_BASE_URL", "http://localhost:58123/v1")

    # Optional API key (llama.cpp doesn't require it, but ChatOpenAI expects one)
    api_key = os.getenv("LLAMACPP_API_KEY", "not-needed")

    # Context window, declared to LangChain as a model profile.
    #
    # WHY THIS MATTERS. DeepAgents' compute_summarization_defaults() picks
    # fraction-based compaction (trigger at 0.85 of the window) ONLY when the
    # model exposes profile["max_input_tokens"]. A local GGUF name is absent
    # from langchain_openai's _MODEL_PROFILES table, so without this the
    # profile is None and the PROFILE-LESS FALLBACK applies:
    # trigger=("tokens", 170000) -- which is ~39k ABOVE the server's own
    # -c 131072 window. Summarization could therefore never fire before
    # llama.cpp itself overflowed.
    #
    # The reactive net does not cover it either: langchain_openai maps an
    # overflow to ContextOverflowError by matching "context_length_exceeded"
    # / "exceeds the context window", but llama.cpp emits "exceeds the
    # available context size" (tools/server/server-context.cpp), so the
    # string never matches and the fallback path never engages.
    #
    # KEEP IN STEP with the -c value in scripts/serve_qwen4exp.sh. If the
    # server is launched with a smaller window than this, compaction will
    # again trigger too late.
    n_ctx = int(os.getenv("LLAMACPP_N_CTX", "131072"))

    # Output budget. A harmless ceiling -- NOT the fix for blank answers.
    #
    # THE PROBLEM. Qwen3.8-Flash-Next emits reasoning_content before visible
    # content, and reasoning counts against this budget. When it consumes the
    # whole budget the response carries finish_reason="length" and ZERO visible
    # content; because netbox_agent.py only yields AI messages that HAVE
    # content, the user sees an empty reply -- no error, no warning. In a
    # 10-question accumulating session, 3 of 56 generations stopped exactly at
    # the cap and the closing "summarise everything" turn returned 0 characters
    # after 24 minutes.
    #
    # RAISING THIS DOES NOT FIX IT. An earlier commit claimed "8192 leaves room
    # for ~6k of reasoning plus a full answer". That claim is WITHDRAWN -- a
    # controlled A/B on the identical prompt disproved it:
    #
    #   adversarial prompt @ 2048 -> reasoning  6,707 chars, answer     0 chars
    #   adversarial prompt @ 8192 -> reasoning 20,304 chars, answer     0 chars
    #
    # Reasoning simply expands to fill whatever budget it is given. And on a
    # REPRESENTATIVE prompt the ceiling is irrelevant either way, because real
    # queries never approach it:
    #
    #   realistic prompt   @ 2048 -> 158 tokens used, answer produced
    #   realistic prompt   @ 8192 -> 149 tokens used, answer produced
    #
    # 8192 is kept only as a bound that cannot crowd out an answer. Cost if it
    # ever IS reached: at the ~1.45 tok/s decode measured at 76k context, 8192
    # tokens is ~94 minutes, so raise it further only deliberately.
    max_tokens = int(os.getenv("LLAMACPP_MAX_TOKENS", "8192"))

    # THE ACTUAL FIX: cap the reasoning, do not enlarge the output budget.
    #
    # Measured on the same adversarial prompt that returned 0 chars, at the
    # ORIGINAL max_tokens=2048:
    #
    #   reasoning_effort="low"            -> reasoning 1,447 chars, answer 5,527 chars
    #   chat_template_kwargs              -> reasoning     0 chars, answer 6,750 chars
    #     {"enable_thinking": false}
    #
    # Both recover a full answer where none was produced before. "low" is
    # preferred over disabling thinking outright: this agent does multi-hop
    # tool selection, where some reasoning is useful. enable_thinking=false
    # would need extra_body plumbing; reasoning_effort is a first-class
    # ChatOpenAI parameter.
    #
    # Set LLAMACPP_REASONING_EFFORT="" (or "default") to send nothing and let
    # the server/template decide. Server-side, llama-server also exposes
    # --reasoning-budget N, which applies to every client rather than just this
    # one -- see scripts/serve_qwen4exp.sh.
    _effort = os.getenv("LLAMACPP_REASONING_EFFORT", "low").strip()
    reasoning_effort = _effort if _effort and _effort != "default" else None

    # Token accounting on streamed calls. ChatOpenAI only auto-enables stream_usage for the
    # default OpenAI URL; with base_url set it sends no stream_options and llama-server sends
    # no usage, so every usage_metadata would be None. Streaming-only effect; the CLI's
    # non-streaming path already gets usage in the response body.
    stream_usage = True

    # Streaming silence watchdog. langchain-openai (>=1.2) raises after 120 s with no
    # parsed chunk on ASYNC streaming calls. llama-server sends NOTHING during prefill,
    # and after a large tool result the prefill of a 176B MoE routinely exceeds 120 s
    # (seen 2026-09-28: 7th model call of a PDU query, 0 chunks in 120 s, turn killed).
    # The server is local and the web layer has its own cancel path, so default to OFF.
    # Non-streaming calls (CLI, eval harness) are unaffected either way.
    _sct = os.getenv("LLAMACPP_STREAM_CHUNK_TIMEOUT_S", "0").strip().lower()
    stream_chunk_timeout: float | None = (
        None if _sct in ("", "0", "none", "off") else float(_sct)
    )

    logger.info("Creating llama.cpp model", model=model, base_url=base_url,
                n_ctx=n_ctx, max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                stream_chunk_timeout=stream_chunk_timeout)

    try:
        llm = LlamaCppChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            stream_usage=stream_usage,
            stream_chunk_timeout=stream_chunk_timeout,
            # Standard OpenAI parameters
            top_p=0.95,
            stop=["<|im_end|>", "<|endoftext|>"],  # Common stop tokens for Qwen
            # Note: llama.cpp server supports standard OpenAI API parameters only
            # Custom parameters like repeat_penalty must be configured on the server side
            profile={"max_input_tokens": n_ctx},
        )

        # Test the model if validation is requested. This is a SYNC invoke inside callers'
        # async initialize(); the web server disables it per-process via the env gate.
        validate_env = os.getenv("LLAMACPP_VALIDATE_ON_INIT", "true").strip().lower()
        if validate and validate_env not in ("0", "false", "no"):
            try:
                response = llm.invoke("test")
                logger.info("llama.cpp model validated successfully", model=model, response_len=len(response.content))
            except Exception as e:
                logger.warning("llama.cpp model validation failed", model=model, error=str(e))
                # Don't fail completely if validation fails
                pass

        return llm

    except Exception as e:
        logger.error("Failed to create llama.cpp model", model=model, error=str(e))
        raise RuntimeError(f"Failed to create llama.cpp model: {e}") from e


def get_llamacpp_models() -> list[str]:
    """
    Get list of available models from llama.cpp server.

    Returns:
        List of model names available on the llama.cpp server
    """
    import httpx

    base_url = os.getenv("LLAMACPP_BASE_URL", "http://localhost:58123/v1")

    try:
        response = httpx.get(f"{base_url}/models", timeout=5.0)
        response.raise_for_status()
        data = response.json()

        # Extract model names from response
        models = []
        if "data" in data:
            models = [model["id"] for model in data["data"]]
        elif "models" in data:
            models = [model["name"] for model in data["models"]]

        logger.info("Retrieved llama.cpp models", count=len(models), models=models)
        return models

    except Exception as e:
        logger.error("Failed to retrieve llama.cpp models", error=str(e))
        return []


def get_model_info(model_name: str | None = None) -> dict:
    """
    Get information about a specific model from llama.cpp server.

    Args:
        model_name: Name of the model to query (defaults to env var)

    Returns:
        Dictionary with model information
    """
    import httpx

    model = model_name or os.getenv("LLAMACPP_MODEL", "Qwen_Qwen3-14B-Q5_K_M.gguf")
    base_url = os.getenv("LLAMACPP_BASE_URL", "http://localhost:58123/v1")

    try:
        response = httpx.get(f"{base_url}/models", timeout=5.0)
        response.raise_for_status()
        data = response.json()

        # Find the specific model
        if "data" in data:
            for model_info in data["data"]:
                if model_info["id"] == model:
                    return model_info

        logger.warning("Model not found", model=model)
        return {}

    except Exception as e:
        logger.error("Failed to get model info", model=model, error=str(e))
        return {}


class LlamaCppModelManager:
    """Manages llama.cpp models with connection validation."""

    def __init__(self, model_name: str = "Qwen_Qwen3-14B-Q5_K_M.gguf"):
        self.model_name = model_name
        self.current_model = None
        self.base_url = os.getenv("LLAMACPP_BASE_URL", "http://localhost:58123/v1")

    def get_model(self, force_model: str | None = None) -> ChatOpenAI:
        """Get a model instance, creating if necessary."""
        model_name = force_model or self.model_name

        if self.current_model is None or force_model:
            try:
                self.current_model = create_llamacpp_model(model_name)
                logger.info("Created llama.cpp model instance", model=model_name)
            except Exception as e:
                logger.error(f"Failed to create llama.cpp model {model_name}: {e}")
                raise

        return self.current_model

    def validate_connection(self) -> bool:
        """Validate connection to llama.cpp server."""
        import httpx

        try:
            response = httpx.get(f"{self.base_url}/models", timeout=5.0)
            response.raise_for_status()
            logger.info("llama.cpp server connection validated", base_url=self.base_url)
            return True
        except Exception as e:
            logger.error("llama.cpp server connection failed", base_url=self.base_url, error=str(e))
            return False
