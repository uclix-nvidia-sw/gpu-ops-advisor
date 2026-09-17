# Repository-root build context. Same dependencies/build/runtime pattern as runaiRCA.
FROM python:3.12-slim AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN python -m venv /opt/venv
COPY agents/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt setuptools
FROM dependencies AS build
COPY shared/python /app/shared/python
COPY ops-agent /app/ops-agent
RUN pip install --no-cache-dir --no-deps --no-build-isolation ./shared/python ./ops-agent
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY ops-agent/configs /app/ops-agent/configs
COPY agents/config.example.json /app/agents/config.example.json
RUN useradd --create-home --uid 10001 appuser && mkdir /app/artifacts && chown appuser /app/artifacts
USER appuser
CMD ["ops-agent"]
