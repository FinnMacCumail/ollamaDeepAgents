"""Configuration management for NetBox DeepAgents with Ollama."""

import os
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OllamaConfig(BaseModel):
    """Configuration for Ollama LLM models."""

    model: str = Field(default="gpt-oss:20b")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    base_url: str = Field(default="http://localhost:11434")
    options: dict[str, Any] = Field(
        default_factory=lambda: {
            "num_ctx": 8192,
            "num_predict": 2048,
            "top_k": 10,
            "top_p": 0.95,
        }
    )

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate that the model is from a supported family.

        Accepts models like 'qwen2.5:32b' or 'qwen2.5:32b-instruct-q4_K_M'.
        """
        allowed_prefixes = [
            "gpt-oss:",
            "qwen2.5:",
            "qwen2:",
            "qwen3-coder:",
            "deepseek-r1:",
            "deepseek-r:",
            "deepseek-v3.1:",
            "deepseek-v4-pro:",
            "deepseek-v4-flash:",
            "llama3.1:",
            "llama3.2:",
            "llama3:",
            "mixtral:",
        ]

        # Check if model starts with any allowed prefix
        if any(v.startswith(prefix) for prefix in allowed_prefixes):
            return v

        # Allow any model in debug mode
        if os.getenv("DEBUG", "false").lower() == "true":
            return v

        raise ValueError(
            f"Model must start with one of: {', '.join(allowed_prefixes)}. "
            f"Got: {v}. Set DEBUG=true to bypass validation."
        )
        return v


class NetBoxConfig(BaseModel):
    """Configuration for NetBox connection."""

    url: str = Field(..., description="NetBox instance URL")
    token: str = Field(..., description="NetBox API token")
    mcp_server_path: str | None = Field(
        default="/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate and normalize the NetBox URL."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")


class QueryMetrics(BaseModel):
    """Metrics tracking for query performance."""

    total_queries: int = 0
    successful_queries: int = 0
    filter_errors: int = 0
    recovered_errors: int = 0
    token_usage: list[int] = Field(default_factory=list)
    response_times: list[float] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of queries."""
        if self.total_queries == 0:
            return 0.0
        return (self.successful_queries / self.total_queries) * 100

    @property
    def avg_tokens(self) -> float:
        """Calculate average token usage per query."""
        return sum(self.token_usage) / len(self.token_usage) if self.token_usage else 0

    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        return (
            sum(self.response_times) / len(self.response_times) if self.response_times else 0
        )

    @property
    def recovery_rate(self) -> float:
        """Calculate the rate of successful error recovery."""
        if self.filter_errors == 0:
            return 0.0
        return (self.recovered_errors / self.filter_errors) * 100

    def report(self) -> str:
        """Generate a summary report of metrics."""
        return f"""
Query Metrics Report:
- Total Queries: {self.total_queries}
- Successful: {self.successful_queries}
- Success Rate: {self.success_rate:.1f}%
- Filter Errors: {self.filter_errors}
- Recovered: {self.recovered_errors}
- Recovery Rate: {self.recovery_rate:.1f}%
- Avg Response Time: {self.avg_response_time:.2f}s
- Avg Token Usage: {self.avg_tokens:.0f}
        """.strip()


def load_netbox_config() -> NetBoxConfig:
    """Load only NetBox connection config from env.

    Use this when the caller has its own model/backend choice and only needs
    network credentials — e.g. matrix-eval runs that vary the model
    programmatically and must not trigger `OllamaConfig`'s prefix-validator
    against an `OLLAMA_MODEL` env value that doesn't match the chosen backend.
    """
    from dotenv import load_dotenv

    load_dotenv()

    netbox_url = os.getenv("NETBOX_URL")
    netbox_token = os.getenv("NETBOX_TOKEN")

    if not netbox_url or not netbox_token:
        raise ValueError(
            "NETBOX_URL and NETBOX_TOKEN must be set in environment variables or .env file"
        )

    return NetBoxConfig(
        url=netbox_url,
        token=netbox_token,
        mcp_server_path=os.getenv(
            "MCP_SERVER_PATH", "/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server"
        ),
    )


def load_config() -> tuple[OllamaConfig, NetBoxConfig]:
    """Load configuration from environment variables."""
    from dotenv import load_dotenv

    load_dotenv()

    ollama_config = OllamaConfig(
        model=os.getenv("OLLAMA_MODEL", "gpt-oss:20b"),
        temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.0")),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )

    return ollama_config, load_netbox_config()
