# AI Assistant Setup Guide

The WarDragon Analytics AI Assistant uses [Ollama](https://ollama.ai/) to provide natural language queries over your drone detection data. This guide covers setting up Ollama for use with the AI Assistant.

## Quick Start

### 1. Install Ollama

**Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**macOS:**
```bash
brew install ollama
```

**Windows:**
Download from [ollama.ai/download](https://ollama.ai/download)

### 2. Start Ollama

```bash
ollama serve
```

Ollama runs on `http://localhost:11434` by default.

### 3. Pull a Model

The default model is `llama3.1:8b`. Pull it with:

```bash
ollama pull llama3.1:8b
```

This downloads ~4.7GB. For faster performance with a GPU, this is the recommended starting point.

### 4. Verify Setup

Test that Ollama is working:

```bash
ollama run llama3.1:8b "Hello, world!"
```

### 5. Start WarDragon Analytics

The AI Assistant will automatically detect Ollama when you start the Analytics platform:

```bash
./quickstart.sh
```

Open the web UI and click the **AI Assistant** button in the header.

---

## Model Recommendations

Choose a model based on your hardware:

| Model | VRAM/RAM | Speed | Quality | Best For |
|-------|----------|-------|---------|----------|
| `llama3.1:8b` | ~5GB | Fast | Good | Most users (recommended) |
| `mistral:7b` | ~4GB | Fast | Good | Lower memory systems |
| `llama3.1:70b` | ~40GB | Slow | Excellent | High-accuracy queries |
| `codellama:13b` | ~8GB | Medium | Very Good | Technical queries |
| `phi3:mini` | ~2GB | Very Fast | Basic | Very limited hardware |

### GPU Acceleration

Ollama automatically uses GPU acceleration if available:

- **NVIDIA:** Requires CUDA drivers (most Linux distros include these)
- **AMD:** ROCm support on Linux
- **Apple Silicon:** Metal acceleration built-in

Check GPU detection:
```bash
ollama run llama3.1:8b --verbose
# Look for "using CUDA" or "using Metal"
```

### CPU-Only Systems

For systems without a GPU, smaller models work best:

```bash
ollama pull phi3:mini       # 2GB, very fast
ollama pull llama3.2:3b     # 2GB, good balance
ollama pull mistral:7b      # 4GB, good quality
```

Update your `.env` to use the model:
```bash
OLLAMA_MODEL=phi3:mini
```

---

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Ollama server URL (default: http://localhost:11434)
OLLAMA_URL=http://localhost:11434

# Model to use (default: llama3.1:8b)
OLLAMA_MODEL=llama3.1:8b

# Request timeout in seconds (increase for slow hardware)
OLLAMA_TIMEOUT=60

# Maximum tokens in response
OLLAMA_MAX_TOKENS=2048

# Temperature (0.0 = deterministic, 1.0 = creative)
# Lower is better for data queries
OLLAMA_TEMPERATURE=0.1
```

### Remote Ollama Server

If running Ollama on a different machine (e.g., a GPU server):

1. On the Ollama server, start with host binding:
   ```bash
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   ```

2. On the Analytics server, update `.env`:
   ```bash
   OLLAMA_URL=http://gpu-server-ip:11434
   ```

**Security Note:** Only expose Ollama on trusted networks. Consider SSH tunneling for remote access:
```bash
ssh -L 11434:localhost:11434 user@gpu-server
```

---

## Docker Deployment (Optional)

If you prefer running Ollama in Docker:

### CPU Only

```bash
docker run -d \
  --name ollama \
  -p 11434:11434 \
  -v ollama-data:/root/.ollama \
  ollama/ollama

# Pull the model
docker exec ollama ollama pull llama3.1:8b
```

### With NVIDIA GPU

```bash
docker run -d \
  --name ollama \
  --gpus all \
  -p 11434:11434 \
  -v ollama-data:/root/.ollama \
  ollama/ollama

# Pull the model
docker exec ollama ollama pull llama3.1:8b
```

### Add to docker-compose.yml

You can add Ollama to your WarDragon Analytics stack:

```yaml
services:
  ollama:
    image: ollama/ollama
    container_name: wardragon-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    # Uncomment for GPU support:
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

volumes:
  ollama-data:
```

Update `.env`:
```bash
OLLAMA_URL=http://wardragon-ollama:11434
```

---

## Troubleshooting

### AI Assistant Shows "Offline"

1. **Check if Ollama is running:**
   ```bash
   curl http://localhost:11434/api/tags
   ```
   Should return a list of models.

2. **Check if model is downloaded:**
   ```bash
   ollama list
   ```
   Make sure your configured model appears.

3. **Pull the model:**
   ```bash
   ollama pull llama3.1:8b
   ```

### Slow Responses

- **Use a smaller model:** Try `phi3:mini` or `llama3.2:3b`
- **Increase timeout:** Set `OLLAMA_TIMEOUT=120` in `.env`
- **Check GPU:** Run `nvidia-smi` to verify GPU is being used
- **Reduce max tokens:** Set `OLLAMA_MAX_TOKENS=1024`

### Out of Memory

- **Use a smaller model:** `phi3:mini` uses only ~2GB
- **Close other applications:** LLMs need significant RAM
- **Add swap space:** Helps when RAM is limited (but slower)

### Model Not Found Error

The configured model isn't downloaded:

```bash
# See available models
ollama list

# Pull the missing model
ollama pull llama3.1:8b
```

### Connection Refused

1. Verify Ollama is running: `pgrep ollama`
2. Check it's listening: `netstat -tlnp | grep 11434`
3. Restart Ollama: `systemctl restart ollama` or `ollama serve`

---

## Example Queries

Once set up, try these queries in the AI Assistant:

**Basic:**
- "How many drones were detected today?"
- "Show me DJI drones from the last hour"
- "What's the average flight altitude?"

**Filtering:**
- "Drones flying above 100 meters"
- "Show fast drones with speed over 20 m/s"
- "Any drones with pilot location?"

**Analysis:**
- "Which manufacturer is most common?"
- "Busiest time of day for detections?"
- "Drones seen by multiple kits"

**Security:**
- "High altitude flights (above FAA limit)"
- "Night time activity"
- "Hovering drones near coordinates"

---

## Disabling the AI Assistant

If you don't want to use the AI Assistant, disable it in `.env`:

```bash
LLM_ENABLED=false
```

The AI button will still appear but will show as offline. This has no impact on other Analytics features.
