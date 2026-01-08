# FROM vllm/vllm-openai:v0.10.1.1

# Use the official vllm image for gpu with Volta、Turing、Blackwell architecture (7.0 < Compute Capability < 8.0 or Compute Capability >= 10.0)
# support x86_64 architecture and ARM(AArch64) architecture
FROM vllm/vllm-openai:v0.11.0

# Install libgl for opencv support & Noto fonts for Chinese characters
RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install mineru latest
RUN python3 -m pip install -U 'mineru[core]>=2.7.0' --break-system-packages && \
    python3 -m pip cache purge

# Set environment variable to use local models
ENV MINERU_MODEL_SOURCE=local

# Set the entry point
ENTRYPOINT ["mineru-api"]