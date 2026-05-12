"""Ollama model configuration and initialization for DeepAgents."""

import os

from langchain_ollama import ChatOllama

from ..utils.logging import get_logger

logger = get_logger(__name__)


def create_ollama_model(
    model_name: str | None = None, temperature: float = 0.0, validate: bool = True
) -> ChatOllama:
    """
    Create and configure an Ollama model for use with DeepAgents.

    CRITICAL: Uses ChatOllama directly, not init_chat_model which has issues with tool binding.

    Args:
        model_name: Name of the Ollama model to use (e.g., "qwen2.5:32b")
        temperature: Temperature for model generation (0.0 = deterministic)
        validate: Whether to validate the model on initialization

    Returns:
        Configured ChatOllama instance

    Raises:
        Exception: If model creation fails and no fallback is available
    """
    # Use environment variable with fallback
    model = model_name or os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    is_cloud = model.endswith(":cloud")

    logger.info("Creating Ollama model", model=model, base_url=base_url, cloud=is_cloud)

    # CRITICAL: Use ChatOllama directly, not init_chat_model
    try:
        llm = ChatOllama(
            model=model,
            temperature=temperature,
            base_url=base_url,
            # validate_model_on_init=validate,  # Note: This parameter might not exist
            options={
                "num_ctx": 32768,  # Large context window — leverage cloud capacity
                "num_predict": 4096,  # Max tokens to generate
                "top_k": 10,
                "top_p": 0.95,
            },
        )

        # Skip the warm-up probe for :cloud models — it would be a billable round-trip
        # to ollama.com on every process start. The first real query surfaces any
        # auth/quota/network issue clearly enough.
        if validate and not is_cloud:
            try:
                _ = llm.invoke("test")
                logger.info("Model validated successfully", model=model)
            except Exception as e:
                logger.warning("Model validation failed", model=model, error=str(e))
                # Don't fail completely if validation fails
                pass

        return llm

    except Exception as e:
        logger.error("Failed to create model", model=model, error=str(e))

        # For cloud models, never silently fall back to a local model — the user
        # asked for the cloud model and needs to see the real error (auth, quota, etc.).
        if is_cloud:
            raise RuntimeError(f"Failed to create Ollama cloud model {model}: {e}") from e

        # Fallback to lighter local model on error
        if model != "mixtral:8x7b":
            logger.info("Attempting fallback to mixtral:8x7b")
            return create_ollama_model("mixtral:8x7b", temperature, False)

        raise RuntimeError(f"Failed to create Ollama model: {e}") from e


def get_supported_models() -> list[str]:
    """Get list of officially supported Ollama model families for this system.

    Note: You can use any quantization variant (e.g., qwen2.5:32b-instruct-q4_K_M).
    The validator accepts model names starting with these prefixes.
    """
    return [
        "qwen2.5:32b",  # Best balance of speed and accuracy (any quantization)
        "qwen2.5:14b",  # Good performance, lighter weight
        "qwen2.5:7b",  # Fast inference, decent capability
        "deepseek-r1:32b",  # Excellent reasoning for complex queries
        "deepseek-r1:14b",  # Good reasoning, lighter weight
        "llama3.1:8b",  # Reliable and widely tested
        "llama3.1:70b",  # Best open-source model (if you have VRAM)
        "mixtral:8x7b",  # Fast with decent accuracy (fallback)
    ]


def estimate_context_usage(prompt: str, response_limit: int = 2048) -> dict:
    """
    Estimate token usage for a given prompt.

    Args:
        prompt: The input prompt
        response_limit: Expected maximum response tokens

    Returns:
        Dictionary with estimated token counts
    """
    # Rough estimation: 1 token ≈ 4 characters (for English)
    prompt_tokens = len(prompt) // 4
    total_estimate = prompt_tokens + response_limit

    return {
        "prompt_tokens": prompt_tokens,
        "response_limit": response_limit,
        "total_estimate": total_estimate,
        "context_window": 8192,
        "usage_percentage": (total_estimate / 8192) * 100,
    }


class OllamaModelManager:
    """Manages multiple Ollama models with fallback and switching capabilities."""

    def __init__(self, primary_model: str = "gpt-oss:20b", fallback_model: str = "mixtral:8x7b"):
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.current_model = None
        self.models = {}

    def get_model(self, force_model: str | None = None) -> ChatOllama:
        """Get a model instance, creating if necessary."""
        model_name = force_model or self.primary_model

        if model_name not in self.models:
            try:
                self.models[model_name] = create_ollama_model(model_name)
                self.current_model = model_name
            except Exception as e:
                logger.error(f"Failed to create model {model_name}: {e}")
                # Try fallback
                if model_name != self.fallback_model and self.fallback_model not in self.models:
                    self.models[self.fallback_model] = create_ollama_model(self.fallback_model)
                    self.current_model = self.fallback_model
                    return self.models[self.fallback_model]
                raise

        return self.models[model_name]

    def switch_model(self, new_model: str) -> ChatOllama:
        """Switch to a different model."""
        logger.info("Switching model", from_model=self.current_model, to_model=new_model)
        self.current_model = new_model
        return self.get_model(new_model)
