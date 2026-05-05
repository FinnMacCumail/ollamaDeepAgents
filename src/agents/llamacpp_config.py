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

    logger.info("Creating llama.cpp model", model=model, base_url=base_url)

    try:
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=base_url,
            api_key=api_key,
            max_tokens=2048,
            # Standard OpenAI parameters
            top_p=0.95,
            stop=["<|im_end|>", "<|endoftext|>"],  # Common stop tokens for Qwen
            # Note: llama.cpp server supports standard OpenAI API parameters only
            # Custom parameters like repeat_penalty must be configured on the server side
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
