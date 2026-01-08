# hunyuan/Dockerfile

FROM vllm/vllm-openai:v0.10.1.1

# 替换源加速
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装混元必需的 transformers 版本
RUN pip install git+https://github.com/huggingface/transformers@4970b23cedaf745f963779b4eae68da281e8c6ca

# 设置入口点
ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]