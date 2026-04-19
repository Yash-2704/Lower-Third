#!/usr/bin/env zsh
# Activate the venv and set Homebrew (Apple Silicon) paths so
# cairocffi can find libcairo and ffmpeg is on PATH.

export DYLD_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_LIBRARY_PATH}"
export PATH="/opt/homebrew/bin:${PATH}"
export PYTHONPATH="/Users/yashaggarwal/Desktop/CC-Modules:${PYTHONPATH}"

source "$(dirname "$0")/.venv/bin/activate"

# Load .env if it exists
if [ -f "$(dirname "$0")/.env" ]; then
    set -a
    source "$(dirname "$0")/.env"
    set +a
fi

echo "✅ Dev environment ready (cairo + ffmpeg + GROQ_API_KEY loaded)"
