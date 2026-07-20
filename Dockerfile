FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml uv.lock /tmp/build/

RUN uv venv /venv --python 3.12 \
    && cd /tmp/build && uv pip install --python /venv/bin/python ".[dev]" \
    && rm -rf /tmp/build

ENV PATH="/venv/bin:$PATH"
ENV VIRTUAL_ENV="/venv"

WORKDIR /app

CMD ["bash"]
