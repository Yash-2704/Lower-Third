# lower_third

The `lower_third` module is a broadcast automation component that generates animated lower-third graphics from natural language prompts. It uses Cairo and Pango for programmatic rendering, Groq (`llama-3.3-70b-versatile`) as the primary LLM and Ollama (`qwen2.5:7b`) as a local fallback, and FFmpeg to encode the final output as RGBA WebM (VP9) video — preserving the alpha channel required for broadcast compositing over live video. All rendering is CPU-based; no diffusion models or GPU are involved.

## System Dependencies

**macOS (Homebrew):**
```bash
brew install cairo pango pkg-config glib ffmpeg
```

**Linux (apt):**
```bash
sudo apt-get install -y libcairo2-dev libpango1.0-dev pkg-config libglib2.0-dev ffmpeg
```

## Python Dependencies

```bash
pip install -r lower_third/requirements.txt
```

## Required Environment Variables

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | API key for Groq cloud inference (primary LLM) |
| `OLLAMA_BASE_URL` | Base URL for local Ollama server (fallback LLM), e.g. `http://localhost:11434/v1` |

## No GPU, No Model Downloads

This module requires **no GPU**, **no HuggingFace model weights**, and **no model downloads**. All graphics are rendered programmatically via Cairo/Pango. LLM calls are made over HTTP to Groq's API or a locally running Ollama instance — both are lightweight and run on CPU.
