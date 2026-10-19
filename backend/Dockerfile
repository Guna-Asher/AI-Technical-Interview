FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/appuser/.cache/huggingface

WORKDIR /app

# CPU-only PyTorch (the default wheels on x86 pull in multi-gigabyte CUDA libraries).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The model cache directory is created here, owned by appuser, so the hf_cache volume mounted on it is writable.
RUN useradd --create-home appuser && mkdir -p "$HF_HOME" && chown -R appuser:appuser /home/appuser/.cache
COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
