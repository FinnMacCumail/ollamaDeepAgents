"""Llama.cpp model configuration and initialization for DeepAgents."""

import os

from langchain_openai import ChatOpenAI

from ..utils.logging import get_logger

logger = get_logger(__name__)


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

    # Output budget. This is a SAFETY CEILING, not a target.
    #
    # It was 2048, and that silently produced BLANK ANSWERS. Qwen3.8-Flash-Next
    # emits reasoning_content before visible content, and reasoning counts
    # against this budget. Reproduced directly against the server: a synthesis
    # question returned finish_reason="length", completion_tokens=2048,
    # reasoning 6,533 chars and **0 chars of visible content**. Since the
    # stream filter in netbox_agent.py only yields AI messages that HAVE
    # content, the user sees an empty reply -- no error, no warning.
    #
    # It is not hypothetical: in a 10-question accumulating session, 3 of 56
    # generations stopped exactly at the cap, and the closing "summarise
    # everything" turn returned 0 characters after 24 minutes.
    #
    # 8192 leaves room for ~6k of reasoning plus a full answer. Observed
    # answers are 38-704 tokens, so the cap should rarely bind; when it does,
    # the answer survives instead of being crowded out. Note the cost if it
    # ever IS reached: at the ~1.45 tok/s decode seen at 76k context, 8192
    # tokens is ~94 minutes, so raise it further only deliberately.
    max_tokens = int(os.getenv("LLAMACPP_MAX_TOKENS", "8192"))

    logger.info("Creating llama.cpp model", model=model, base_url=base_url,
                n_ctx=n_ctx, max_tokens=max_tokens)

    try:
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            # Standard OpenAI parameters
            top_p=0.95,
            stop=["<|im_end|>", "<|endoftext|>"],  # Common stop tokens for Qwen
            # Note: llama.cpp server supports standard OpenAI API parameters only
            # Custom parameters like repeat_penalty must be configured on the server side
            profile={"max_input_tokens": n_ctx},
        )

        # Test the model if validation is requested
        if validate:
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
