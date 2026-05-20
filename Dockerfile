# syntax=docker/dockerfile:1.7

############################################################
# 1) Stage: FRONTEND BUILD
############################################################
FROM node:26-slim AS frontend-build

WORKDIR /app/frontend

# Enable corepack with the pinned pnpm version from package.json
RUN npm install -g pnpm@11.0.9

# Copy only lockfiles first so pnpm install is cached independently of source changes
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./

RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    CI=true pnpm install --frozen-lockfile

# Copy source after install to avoid invalidating the install layer on code changes
COPY frontend/ ./

RUN pnpm run build

# The built static files are in /app/frontend/out/

############################################################
# 2) Stage: PYTHON DEPENDENCY BUILD
############################################################
FROM python:3.11-slim-bookworm AS python-deps

RUN set -eux; \
    apt-get update -o Acquire::Retries=5 -o Acquire::http::Timeout=30 && \
    apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libjpeg-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7-dev \
    libimagequant-dev libheif-dev liblcms2-dev \
    libfreetype6-dev libharfbuzz-dev libfribidi-dev \
    libxcb1-dev zlib1g-dev libgif-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt /build/
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

############################################################
# 3) Stage: REMBG MODEL DOWNLOAD
# Separate stage so a code change in backend/ does NOT trigger
# a 168 MB model re-download. Only re-runs when requirements.txt
# or rembg.json changes.
############################################################
FROM python:3.11-slim-bookworm AS rembg-model-download

COPY requirements.txt /tmp/
RUN --mount=type=bind,from=python-deps,source=/wheels,target=/wheels,readonly \
    pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.txt

ENV U2NET_HOME=/model-cache/.u2net
COPY backend/image_converter/config/rembg.json /tmp/rembg.json
RUN python - <<'PY'
import json
from rembg import new_session
with open("/tmp/rembg.json", "r", encoding="utf-8") as f:
    model_name = json.load(f).get("model_name", "u2net")
new_session(model_name)
print(f"rembg model cached: {model_name}")
PY

############################################################
# 4) Stage: FINAL PYTHON IMAGE
############################################################
FROM python:3.11-slim-bookworm

# Prevent .pyc files from being written into image layers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    U2NET_HOME=/container/.u2net

# Exclude docs, man pages and locale files from all subsequent apt-get installs
RUN echo 'path-exclude /usr/share/doc/*' > /etc/dpkg/dpkg.cfg.d/nodoc \
 && echo 'path-exclude /usr/share/man/*' >> /etc/dpkg/dpkg.cfg.d/nodoc \
 && echo 'path-exclude /usr/share/locale/*' >> /etc/dpkg/dpkg.cfg.d/nodoc \
 && echo 'path-include /usr/share/locale/en*' >> /etc/dpkg/dpkg.cfg.d/nodoc

# Install runtime system dependencies required for full Pillow image format support
#
# This layer installs libraries that enable reading/writing many image formats:
#   - libjpeg, libpng, libtiff, libwebp, libopenjp2: common raster formats (JPEG, PNG, TIFF, WebP, JPEG2000)
#   - libimagequant: high-quality PNG quantization
#   - libheif: enables HEIF / HEIC / AVIF image decoding
#   - ghostscript: enables reading vector formats like .EPS, .PS, and .PDF
#   - liblcms2, libfreetype, libharfbuzz, libfribidi: color management + advanced text rendering
#   - libxcb, zlib, libgif: core compression and GIF/X11 support
#
# Together, these libraries ensure Pillow (PIL) can handle nearly every major image type used in production.
RUN set -eux; \
    apt-get update -o Acquire::Retries=5 -o Acquire::http::Timeout=30 && \
    apt-get install -y --no-install-recommends \
    libjpeg62-turbo libpng16-16 libtiff6 libwebp7 libwebpdemux2 libwebpmux3 libopenjp2-7 \
    libimagequant0 libheif1 liblcms2-2 \
    libfreetype6 libharfbuzz0b libfribidi0 \
    libxcb1 zlib1g libgif7 ghostscript \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man

WORKDIR /container

# Install Python packages from pre-built wheels
COPY requirements.txt /container/
COPY setup.py /container/
RUN --mount=type=bind,from=python-deps,source=/wheels,target=/wheels,readonly \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# Copy backend code and entrypoint
COPY backend/ /container/backend
COPY --chmod=755 entrypoint.sh /container/entrypoint.sh

# Register the package entry point (deps already installed above, skip re-resolving)
RUN pip install --no-cache-dir --no-deps .

# Strip precompiled bytecode from site-packages
# Note: pip/setuptools must be kept — pkg_resources (part of setuptools) is used at runtime
# Note: .dist-info dirs must be kept — apscheduler uses entry_points for plugin discovery
RUN find /usr/local/lib/python3.11/site-packages -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; \
    find /usr/local/lib/python3.11/site-packages -name "*.pyc" -delete 2>/dev/null; \
    true

# Copy pre-downloaded rembg model from dedicated stage (no runtime download needed)
COPY --from=rembg-model-download /model-cache/.u2net /container/.u2net

# Create static site directory and copy built frontend
RUN mkdir -p /container/backend/image_converter/presentation/web/static_site
COPY --from=frontend-build /app/frontend/out/. /container/backend/image_converter/presentation/web/static_site

LABEL org.opencontainers.image.authors="Karim Zouine <mails.karimzouine@gmail.com>" \
      org.opencontainers.image.vendor="Karim Zouine" \
      org.opencontainers.image.title="imgcompress - High Performance Image Compression & Background Removal" \
      org.opencontainers.image.description="Self-hosted, privacy-first tool for image compression, conversion (HEIC/WebP/PDF), and background removal using local AI. Supports 70+ formats." \
      org.opencontainers.image.url="https://github.com/karimz1/imgcompress" \
      org.opencontainers.image.source="https://github.com/karimz1/imgcompress" \
      org.opencontainers.image.documentation="https://github.com/karimz1/imgcompress" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

EXPOSE 5000

ENTRYPOINT ["/container/entrypoint.sh"]
