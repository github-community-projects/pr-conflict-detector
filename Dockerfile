#checkov:skip=CKV_DOCKER_2
#checkov:skip=CKV_DOCKER_3
#trivy:ignore:AVD-DS-0002
FROM python:3.14.3-slim@sha256:6a27522252aef8432841f224d9baaa6e9fce07b07584154fa0b9a96603af7456
LABEL org.opencontainers.image.source https://github.com/github-community-projects/pr-conflict-detector

COPY --from=ghcr.io/astral-sh/uv:0.10.9@sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82 /uv /uvx /bin/

WORKDIR /action/workspace
COPY pyproject.toml uv.lock *.py /action/workspace/

RUN uv sync --frozen --no-dev --no-editable \
    && apt-get -y update \
    && apt-get -y install --no-install-recommends git=1:2.47.3-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

# Add a simple healthcheck to satisfy container scanners
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python3 -c "import os,sys; sys.exit(0 if os.path.exists('/action/workspace/pr_conflict_detector.py') else 1)"

ENV PYTHONUNBUFFERED=1
CMD ["/action/workspace/pr_conflict_detector.py"]
ENTRYPOINT ["uv", "run"]
