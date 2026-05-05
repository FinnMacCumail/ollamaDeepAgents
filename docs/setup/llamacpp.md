# Using Llama.cpp with DeepAgents

This guide shows you how to configure ollamaDeepAgents to use local GGUF models via llama.cpp server instead of Ollama.

## Benefits of Using Llama.cpp

- **Direct GGUF model loading** - Use any GGUF model file directly
- **Lower memory overhead** - More efficient than Ollama for single models
- **Better performance** - Optimized inference with llama.cpp
- **Cleaner output** - As you've seen with your llama.cpp server

## Prerequisites

1. **Llama.cpp server running** with OpenAI-compatible API:
   ```bash
   # Your llama.cpp server should be running on port 58123
   # Check it's running:
   curl -s http://localhost:58123/v1/models
   ```

2. **GGUF model file** available (e.g., `Qwen_Qwen3-14B-Q5_K_M.gguf`)

## Configuration

### 1. Update .env File

Edit your `.env` file to use llama.cpp backend:

```bash
# LLM Backend Selection
LLM_BACKEND=llamacpp

# Llama.cpp Configuration
LLAMACPP_BASE_URL=http://localhost:58123/v1
LLAMACPP_MODEL=Qwen_Qwen3-14B-Q5_K_M.gguf
LLAMACPP_API_KEY=not-needed
```

### 2. Verify Configuration

Check that llama.cpp server is accessible:

```bash
curl -s http://localhost:58123/v1/models | python3 -m json.tool
```

You should see your model listed:
```json
{
  "data": [
    {
      "id": "Qwen_Qwen3-14B-Q5_K_M.gguf",
      "object": "model",
      "created": 1777836683,
      "owned_by": "llamacpp"
    }
  ]
}
```

### 3. Run the Agent

Start the agent as normal:

```bash
python -m src.main
```

You should see in the initialization logs:
```
DEBUG: Creating llamacpp model...
INFO: Creating llama.cpp model
INFO: NetBox DeepAgent initialized - backend: llamacpp
```

## Switching Between Backends

You can easily switch between Ollama and llama.cpp:

### Use Llama.cpp (GGUF models)
```bash
# In .env
LLM_BACKEND=llamacpp
LLAMACPP_MODEL=Qwen_Qwen3-14B-Q5_K_M.gguf
```

### Use Ollama
```bash
# In .env
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5:32b-instruct-q4_K_M
```

## Programmatic Usage

You can also specify the backend programmatically:

```python
from src.agents.netbox_agent import create_netbox_agent

# Use llama.cpp
agent = await create_netbox_agent(
    backend="llamacpp",
    model_name="Qwen_Qwen3-14B-Q5_K_M.gguf"
)

# Or use Ollama
agent = await create_netbox_agent(
    backend="ollama",
    model_name="qwen2.5:14b"
)
```

## Available Models

### Check Available Llama.cpp Models

```python
from src.agents.llamacpp_config import get_llamacpp_models

models = get_llamacpp_models()
print(models)
```

### Get Model Information

```python
from src.agents.llamacpp_config import get_model_info

info = get_model_info("Qwen_Qwen3-14B-Q5_K_M.gguf")
print(info)
```

## Troubleshooting

### Server Not Running

If you get connection errors:
```
ERROR: Failed to connect to llama.cpp server
```

Check that llama.cpp server is running:
```bash
curl http://localhost:58123/v1/models
```

### Model Not Found

If the model isn't found:
```
ERROR: Model Qwen_Qwen3-14B-Q5_K_M.gguf not found
```

Verify the exact model name:
```bash
curl -s http://localhost:58123/v1/models | jq -r '.data[].id'
```

### Performance Issues

If the model is slow:
- Check GPU usage: `nvidia-smi`
- Verify llama.cpp server is using GPU
- Consider using a smaller quantization (Q4 instead of Q5)

## Model Recommendations

For NetBox queries with DeepAgents:

| Model | Size | Performance | Memory | Recommendation |
|-------|------|------------|--------|----------------|
| Qwen3-14B-Q5_K_M | 10GB | Excellent | ~12GB VRAM | ✅ Best balance |
| Qwen3-14B-Q4_K_M | 8GB | Very Good | ~10GB VRAM | ✅ Faster |
| Qwen2.5-32B-Q4_K_M | 20GB | Excellent | ~22GB VRAM | ⚠️ Requires more VRAM |
| Qwen2.5-7B-Q5_K_M | 5GB | Good | ~6GB VRAM | ✅ For lower-end GPUs |

Based on your RTX 2080 Ti (11GB VRAM), **Qwen3-14B-Q5_K_M** is the optimal choice.

## Advanced Configuration

### Custom Stop Tokens

Edit `src/agents/llamacpp_config.py` to customize stop tokens for your model:

```python
stop=["<|im_end|>", "<|endoftext|>", "User:", "\n\n\n"]
```

### Adjust Generation Parameters

```python
llm = ChatOpenAI(
    model=model,
    temperature=0.0,      # Deterministic (0.0) or creative (0.7+)
    top_p=0.95,           # Nucleus sampling
    max_tokens=4096,      # Max response length
    # ...
)
```

## Comparison: Ollama vs Llama.cpp

| Feature | Ollama | Llama.cpp |
|---------|--------|-----------|
| Model Format | Ollama (GGUF-based) | Direct GGUF |
| Installation | Simple (`ollama pull`) | Manual model download |
| Performance | Good | Excellent |
| Memory Usage | Higher | Lower |
| Output Quality | Good | Better (cleaner) |
| Model Switching | Easy (`ollama pull`) | Manual file management |
| Multi-model | Yes | Single model at a time |

## Next Steps

After configuring llama.cpp:

1. **Test queries** - Try your NetBox queries and compare output quality
2. **Benchmark performance** - Measure response times vs Ollama
3. **Tune parameters** - Adjust temperature, top_p for your use case
4. **Try different models** - Experiment with Q4 vs Q5 quantization

For more information, see:
- [DeepAgents Documentation](https://docs.langchain.com/oss/python/deepagents/overview)
- [Llama.cpp Server Documentation](https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md)
