FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

USER root
COPY dist/conformdag-*.whl /tmp/
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && WHEEL="$(ls /tmp/conformdag-*.whl)" \
    && python -m pip install --no-cache-dir "${WHEEL}[platform]" \
    && rm -f /tmp/conformdag-*.whl \
    && useradd --create-home --uid 10001 conformdag

USER conformdag
WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["conformdag"]
CMD ["--help"]
