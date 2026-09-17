# Student .py+.pth isolate image. Runtime must not pip.
FROM python:3.11-slim-bookworm

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin labrun \
    && mkdir -p /opt/lab /in /out \
    && chown -R labrun:labrun /opt/lab /out

WORKDIR /opt/lab

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir numpy

COPY packages/admit /opt/lab/admit

ENV PYTHONPATH=/opt/lab \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER labrun
WORKDIR /work
ENTRYPOINT ["python", "-m", "admit"]
