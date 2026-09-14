#!/usr/bin/env bash
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
    echo "This helper supports Debian and Ubuntu. See the Manim installation guide for your OS." >&2
    exit 1
fi

sudo apt-get update
sudo apt-get install -y \
    build-essential \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    python3-dev \
    texlive-fonts-recommended \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-science
