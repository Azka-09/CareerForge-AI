FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 APP_ENV=production DATABASE_URL=sqlite:////data/careerforge.db
WORKDIR /app
COPY requirements.txt .
# CPU-only torch keeps the image far smaller (sentence-transformers needs it)
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu torch \
 && grep -v -E "^(pytest|ruff|pip-audit)" requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt
COPY . .
RUN useradd --create-home app && mkdir /data && chown -R app /app /data
USER app
VOLUME /data
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').status==200 else 1)"
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
