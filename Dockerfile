# syntax = docker/dockerfile:1.2

# Build stage - includes build dependencies
FROM python:3.12-bullseye as builder

# Install build dependencies
RUN apt-get update && apt-get -y upgrade && apt-get -y install gcc

# Install poetry
RUN pip3 install --upgrade pip
RUN pip3 install poetry

WORKDIR /app

# Configure poetry to not create virtual environments (we're in a container)
RUN poetry config virtualenvs.create false

# Copy dependency files
COPY poetry.lock pyproject.toml /app/

# Install dependencies
ARG poetryargs="--only main"
RUN poetry install -vvv ${poetryargs} --no-interaction --no-ansi --no-root

# Create app structure for editable install
RUN mkdir -p src/app
RUN touch src/app/__init__.py

# Install the app in editable mode
RUN pip install -vvv -e .

# Runtime stage - minimal image with only runtime dependencies
FROM python:3.12-slim-bullseye as runtime

ARG GID=1000
ARG UID=1000

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get -y upgrade && \
    apt-get -y install --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN addgroup --gid $GID --system app && \
    adduser --no-create-home --shell /bin/false --disabled-password --uid $UID --system --group app

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files
COPY --chown=app:app src /app/src/
COPY --chown=app:app migrations /app/migrations/
COPY --chown=app:app alembic.ini /app/alembic.ini
COPY --chown=app:app pyproject.toml /app/pyproject.toml
USER app