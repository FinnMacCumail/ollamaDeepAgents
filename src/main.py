#!/usr/bin/env python3
"""Main entry point for NetBox DeepAgents with Ollama."""

import asyncio
import os
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .agents.netbox_agent import create_netbox_agent
from .utils.config import load_config, load_netbox_config
from .utils.logging import setup_logging

# Initialize Rich console for beautiful output
console = Console()


def print_welcome():
    """Print welcome message and system info."""
    welcome_text = """
# NetBox DeepAgents Query System

An intelligent NetBox infrastructure query system powered by:
- **DeepAgents** framework for advanced reasoning
- **Ollama** for local LLM inference
- **MCP** for NetBox integration

Type your NetBox queries in natural language.
Type 'help' for assistance, 'metrics' for stats, or 'exit' to quit.
    """
    console.print(Panel(Markdown(welcome_text), title="Welcome", border_style="blue"))


def print_help():
    """Print help information."""
    help_text = """
# Available Commands

## Query Examples:
- "Show all devices in site NYC-DC1"
- "List interfaces on router01"
- "Find all active circuits"
- "Show IP addresses for server-prod-01"
- "Search for devices with 'web' in the name"

## Special Commands:
- **help** - Show this help message
- **metrics** - Display performance metrics
- **clear** - Clear the screen
- **new** - Start a fresh conversation (forget previous turns)
- **exit/quit** - Exit the application

## Tips:
- The system automatically handles complex filter constraints
- Two-step queries are used for relationship filters
- Search is used for pattern matching
- Direct ID filters always work best

## Filter Constraints:
⚠️ Avoid: device__site_id, name__icontains
✅ Use: device_id, exact names, search for patterns
    """
    console.print(Panel(Markdown(help_text), title="Help", border_style="green"))


def print_metrics(agent):
    """Print metrics report."""
    if not agent.metrics:
        console.print("[yellow]Metrics tracking is disabled[/yellow]")
        return

    metrics = agent.metrics

    # Create a table for metrics
    table = Table(title="Query Metrics", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Queries", str(metrics.total_queries))
    table.add_row("Successful Queries", str(metrics.successful_queries))
    table.add_row("Success Rate", f"{metrics.success_rate:.1f}%")
    table.add_row("Filter Errors", str(metrics.filter_errors))
    table.add_row("Recovered Errors", str(metrics.recovered_errors))
    table.add_row("Recovery Rate", f"{metrics.recovery_rate:.1f}%")

    if metrics.response_times:
        table.add_row("Avg Response Time", f"{metrics.avg_response_time:.2f}s")

    if metrics.token_usage:
        table.add_row("Avg Token Usage", f"{metrics.avg_tokens:.0f}")

    console.print(table)


async def interactive_mode(agent):
    """Run the agent in interactive mode."""
    print_welcome()

    while True:
        try:
            # Get user input
            query = Prompt.ask("\n[bold blue]NetBox Query[/bold blue]")

            # Handle special commands
            if query.lower() in ["exit", "quit", "q"]:
                console.print("[yellow]Goodbye![/yellow]")
                break

            elif query.lower() == "help":
                print_help()
                continue

            elif query.lower() == "metrics":
                print_metrics(agent)
                continue

            elif query.lower() == "clear":
                console.clear()
                print_welcome()
                continue

            elif query.lower() == "new":
                tid = agent.new_conversation()
                console.print(f"[green]Started a new conversation (thread: {tid[:8]}...)[/green]")
                continue

            # Process the NetBox query
            console.print("[cyan]Processing query...[/cyan]")

            response_parts = []
            async for chunk in agent.query(query):
                response_parts.append(chunk)

            response = "".join(response_parts)

            # Display response in a nice panel
            console.print(
                Panel(
                    Markdown(response),
                    title="Response",
                    border_style="green",
                )
            )

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
            continue

        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            console.print("[yellow]Try rephrasing your query or type 'help' for assistance.[/yellow]")


async def batch_mode(agent, queries):
    """Run the agent in batch mode with provided queries."""
    console.print(f"[cyan]Processing {len(queries)} queries...[/cyan]\n")

    for i, query in enumerate(queries, 1):
        console.print(f"[bold]Query {i}/{len(queries)}:[/bold] {query}")

        try:
            response = await agent.query_sync(query)
            console.print(Panel(Markdown(response), border_style="green"))

        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")

        console.print("-" * 80)

    # Print final metrics
    print_metrics(agent)


async def main(args: list | None = None):
    """Main entry point."""
    # Setup logging
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    # Parse command line arguments
    import argparse

    parser = argparse.ArgumentParser(description="NetBox DeepAgents Query System")
    parser.add_argument(
        "--model",
        type=str,
        help="Ollama model to use (default: from env or qwen2.5:32b)",
    )
    parser.add_argument(
        "--batch",
        type=str,
        nargs="+",
        help="Run in batch mode with specified queries",
    )
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        help="Disable metrics tracking",
    )
    parser.add_argument(
        "--skills-path",
        type=str,
        default="src/skills",
        help="Path to skills directory",
    )

    parsed_args = parser.parse_args(args if args is not None else sys.argv[1:])

    try:
        # Load configuration.
        #
        # Model selection is BACKEND-AWARE. This previously read
        # `ollama_config.model` unconditionally, so with LLM_BACKEND=llamacpp
        # the run was still LABELLED with OLLAMA_MODEL: traces recorded
        # `deepseek-v4-flash:cloud` while llama.cpp actually served the loaded
        # GGUF. Answers were correct -- llama.cpp ignores the request's `model`
        # field and serves whatever is loaded -- but every trace on the
        # llamacpp backend carried the wrong model name, which would silently
        # corrupt any comparison against real Ollama runs.
        #
        # The llamacpp branch uses load_netbox_config() rather than
        # load_config(): OllamaConfig validates OLLAMA_MODEL against a prefix
        # allowlist containing no GGUF pattern, so routing a llama.cpp model
        # name through it would raise. That helper exists for exactly this
        # case -- see its docstring in utils/config.py.
        console.print("[cyan]Loading configuration...[/cyan]")

        # Load .env BEFORE reading LLM_BACKEND. Until this call, os.getenv sees
        # nothing from .env: load_dotenv() previously ran only as a side effect
        # INSIDE load_config()/load_netbox_config() (utils/config.py), i.e.
        # after this point. Reading LLM_BACKEND first therefore silently fell
        # through to the "ollama" default and picked the wrong model even with
        # LLM_BACKEND=llamacpp set. load_dotenv() is idempotent, so the calls
        # inside those helpers remain harmless.
        from dotenv import load_dotenv

        load_dotenv()

        backend = os.getenv("LLM_BACKEND", "ollama")

        if backend == "llamacpp":
            netbox_config = load_netbox_config()
            default_model = os.getenv("LLAMACPP_MODEL", "Qwen_Qwen3-14B-Q5_K_M.gguf")
        else:
            ollama_config, netbox_config = load_config()
            default_model = ollama_config.model

        # An explicit --model always wins, on either backend.
        model_name = parsed_args.model or default_model

        # Create and initialize agent. `backend` is passed explicitly rather
        # than left to NetBoxDeepAgent's env fallback: that implicit path is
        # what let the model name and the backend disagree in the first place.
        console.print(
            f"[cyan]Initializing NetBox agent with model {model_name} "
            f"(backend: {backend})...[/cyan]"
        )
        agent = await create_netbox_agent(
            netbox_config=netbox_config,
            model_name=model_name,
            backend=backend,
            skills_path=parsed_args.skills_path,
            enable_metrics=not parsed_args.no_metrics,
        )

        # Run in appropriate mode
        if parsed_args.batch:
            await batch_mode(agent, parsed_args.batch)
        else:
            await interactive_mode(agent)

    except ValueError as e:
        console.print(f"[red]Configuration Error: {str(e)}[/red]")
        console.print("[yellow]Please check your .env file and ensure NETBOX_URL and NETBOX_TOKEN are set.[/yellow]")
        sys.exit(1)

    except Exception as e:
        console.print(f"[red]Fatal Error: {str(e)}[/red]")
        import traceback

        if os.getenv("DEBUG", "false").lower() == "true":
            traceback.print_exc()
        sys.exit(1)

    finally:
        # Clean up
        if "agent" in locals():
            await agent.cleanup()


def run():
    """Run the application."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
