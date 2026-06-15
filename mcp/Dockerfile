# Stage 1: BUILD
# digest-refresh: skip
FROM dhi.io/debian-base:trixie-debian13-dev@sha256:41cc0e62bbb3b8cbb29deb40c987e55577cf98c4d00ede32b40159a1a4d87565 AS build-stage

COPY --from=dhi.io/uv:0.11.18-debian13@sha256:be1c2d5905075a57885f83a04f4f64eab0d4b99c4695803d9a707a7fd448152d /uv /bin/uv

RUN rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -o Acquire::Retries=5 -o Acquire::http::Timeout=30 && \
    apt-get install -y --no-install-recommends dumb-init

RUN mkdir -p /mcp && chown -R nonroot:nonroot /mcp
USER nonroot

ENV VIRTUAL_ENV=/mcp/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV UV_PYTHON_INSTALL_DIR=/mcp/python

RUN --mount=type=cache,target=/home/nonroot/.cache/uv,uid=65532,gid=65532 \
    uv python install 3.11 && \
    uv venv --python 3.11 $VIRTUAL_ENV

WORKDIR /mcp

RUN --mount=type=cache,target=/home/nonroot/.cache/uv,uid=65532,gid=65532 \
    uv pip install "mcp[cli]>=1.0" "httpx>=0.27"

COPY --chown=nonroot:nonroot server.py .


# Stage 2: RUNTIME
# digest-refresh: skip
FROM dhi.io/debian-base:trixie-debian13@sha256:436787c2d77ed1ef1cfe3ce5848f3968244d8948463a29094e1e672da9a6fa24

LABEL org.opencontainers.image.title="imgcompress-mcp" \
      org.opencontainers.image.description="MCP wrapper server for imgcompress REST API" \
      org.opencontainers.image.url="https://github.com/karimz1/imgcompress" \
      org.opencontainers.image.source="https://github.com/karimz1/imgcompress" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

COPY --from=build-stage /usr/bin/dumb-init /usr/bin/dumb-init
COPY --from=build-stage --chown=65532:65532 /mcp /mcp

ENV VIRTUAL_ENV=/mcp/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV IMGCOMPRESS_URL=http://localhost:5000
ENV MCP_TRANSPORT=stdio
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=9090

WORKDIR /mcp
USER nonroot
EXPOSE 9090

ENTRYPOINT ["/usr/bin/dumb-init", "--", "python", "/mcp/server.py"]
