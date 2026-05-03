"""Tests for Ollama model configuration and integration."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.agents.ollama_config import (
    OllamaModelManager,
    create_ollama_model,
    estimate_context_usage,
    get_supported_models,
)
from src.utils.config import OllamaConfig


class TestOllamaModelCreation:
    """Test Ollama model creation and configuration."""

    @patch("src.agents.ollama_config.ChatOllama")
    def test_create_ollama_model_default(self, mock_chat_ollama):
        """Test creating model with default settings."""
        mock_instance = MagicMock()
        mock_chat_ollama.return_value = mock_instance

        model = create_ollama_model()

        mock_chat_ollama.assert_called_once()
        call_kwargs = mock_chat_ollama.call_args.kwargs
        assert call_kwargs["model"] == "qwen2.5:32b"
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["options"]["num_ctx"] == 8192

    @patch("src.agents.ollama_config.ChatOllama")
    def test_create_ollama_model_custom(self, mock_chat_ollama):
        """Test creating model with custom settings."""
        mock_instance = MagicMock()
        mock_chat_ollama.return_value = mock_instance

        model = create_ollama_model(model_name="mixtral:8x7b", temperature=0.5)

        call_kwargs = mock_chat_ollama.call_args.kwargs
        assert call_kwargs["model"] == "mixtral:8x7b"
        assert call_kwargs["temperature"] == 0.5

    @patch.dict(os.environ, {"OLLAMA_MODEL": "llama3.1:70b", "OLLAMA_BASE_URL": "http://custom:11434"})
    @patch("src.agents.ollama_config.ChatOllama")
    def test_create_ollama_model_from_env(self, mock_chat_ollama):
        """Test model creation from environment variables."""
        mock_instance = MagicMock()
        mock_chat_ollama.return_value = mock_instance

        model = create_ollama_model()

        call_kwargs = mock_chat_ollama.call_args.kwargs
        assert call_kwargs["model"] == "llama3.1:70b"
        assert call_kwargs["base_url"] == "http://custom:11434"

    @patch("src.agents.ollama_config.ChatOllama")
    def test_model_fallback_on_error(self, mock_chat_ollama):
        """Test fallback to lighter model on error."""
        # First call fails
        mock_chat_ollama.side_effect = [
            RuntimeError("Model not found"),
            MagicMock(),  # Fallback succeeds
        ]

        model = create_ollama_model(model_name="deepseek-r1:70b")

        assert mock_chat_ollama.call_count == 2
        # Second call should be with fallback model
        second_call = mock_chat_ollama.call_args_list[1]
        assert second_call.kwargs["model"] == "mixtral:8x7b"

    def test_context_window_configuration(self):
        """Test that context window is properly configured."""
        config = OllamaConfig()
        assert config.options["num_ctx"] == 8192
        assert config.options["num_predict"] == 2048

    def test_supported_models_list(self):
        """Test getting list of supported models."""
        models = get_supported_models()
        assert "qwen2.5:32b" in models
        assert "deepseek-r1:70b" in models
        assert "llama3.1:70b" in models
        assert "mixtral:8x7b" in models
        assert len(models) == 4


class TestContextUsageEstimation:
    """Test context usage estimation utilities."""

    def test_estimate_context_usage_basic(self):
        """Test basic context usage estimation."""
        prompt = "Show all devices in site NYC-DC1"  # 32 chars ≈ 8 tokens

        estimate = estimate_context_usage(prompt)

        assert estimate["prompt_tokens"] == len(prompt) // 4
        assert estimate["response_limit"] == 2048
        assert estimate["context_window"] == 8192
        assert estimate["usage_percentage"] < 100

    def test_estimate_context_usage_large_prompt(self):
        """Test estimation with large prompt."""
        # Create a large prompt (20,000 chars ≈ 5,000 tokens)
        large_prompt = "x" * 20000

        estimate = estimate_context_usage(large_prompt, response_limit=1000)

        assert estimate["prompt_tokens"] == 5000
        assert estimate["response_limit"] == 1000
        assert estimate["total_estimate"] == 6000
        assert estimate["usage_percentage"] == (6000 / 8192) * 100


class TestOllamaModelManager:
    """Test model manager for handling multiple models."""

    @patch("src.agents.ollama_config.create_ollama_model")
    def test_model_manager_initialization(self, mock_create):
        """Test model manager initialization."""
        manager = OllamaModelManager(
            primary_model="qwen2.5:32b", fallback_model="mixtral:8x7b"
        )

        assert manager.primary_model == "qwen2.5:32b"
        assert manager.fallback_model == "mixtral:8x7b"
        assert manager.current_model is None
        assert len(manager.models) == 0

    @patch("src.agents.ollama_config.create_ollama_model")
    def test_get_model_creates_if_missing(self, mock_create):
        """Test that get_model creates model if not cached."""
        mock_model = MagicMock()
        mock_create.return_value = mock_model

        manager = OllamaModelManager()
        model = manager.get_model()

        mock_create.assert_called_once_with("qwen2.5:32b")
        assert manager.models["qwen2.5:32b"] == mock_model
        assert manager.current_model == "qwen2.5:32b"

    @patch("src.agents.ollama_config.create_ollama_model")
    def test_get_model_uses_cache(self, mock_create):
        """Test that get_model uses cached model if available."""
        mock_model = MagicMock()
        manager = OllamaModelManager()
        manager.models["qwen2.5:32b"] = mock_model
        manager.current_model = "qwen2.5:32b"

        model = manager.get_model()

        mock_create.assert_not_called()
        assert model == mock_model

    @patch("src.agents.ollama_config.create_ollama_model")
    def test_switch_model(self, mock_create):
        """Test switching between models."""
        mock_model1 = MagicMock()
        mock_model2 = MagicMock()
        mock_create.side_effect = [mock_model1, mock_model2]

        manager = OllamaModelManager()

        # Get initial model
        model1 = manager.get_model()
        assert manager.current_model == "qwen2.5:32b"

        # Switch to different model
        model2 = manager.switch_model("deepseek-r1:70b")
        assert manager.current_model == "deepseek-r1:70b"
        assert model2 == mock_model2

    @patch("src.agents.ollama_config.create_ollama_model")
    def test_fallback_on_primary_failure(self, mock_create):
        """Test fallback when primary model fails."""
        mock_create.side_effect = [
            RuntimeError("Primary model failed"),
            MagicMock(),  # Fallback succeeds
        ]

        manager = OllamaModelManager(
            primary_model="deepseek-r1:70b", fallback_model="mixtral:8x7b"
        )

        model = manager.get_model()

        assert mock_create.call_count == 2
        assert manager.current_model == "mixtral:8x7b"


@pytest.mark.asyncio
async def test_ollama_model_validation():
    """Test model validation during creation."""
    with patch("src.agents.ollama_config.ChatOllama") as mock_chat:
        mock_instance = MagicMock()
        mock_instance.invoke = MagicMock(return_value="test response")
        mock_chat.return_value = mock_instance

        model = create_ollama_model(validate=True)

        # Validation should call invoke with "test"
        mock_instance.invoke.assert_called_once_with("test")


@pytest.mark.asyncio
async def test_ollama_model_validation_failure():
    """Test graceful handling of validation failure."""
    with patch("src.agents.ollama_config.ChatOllama") as mock_chat:
        mock_instance = MagicMock()
        mock_instance.invoke = MagicMock(side_effect=Exception("Connection failed"))
        mock_chat.return_value = mock_instance

        # Should not raise even if validation fails
        model = create_ollama_model(validate=True)

        assert model == mock_instance