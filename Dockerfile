FROM python:3.9-slim

WORKDIR /app

# Install dependencies including FFmpeg
RUN apt-get update && \
    apt-get install -y curl ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create temp directory for file processing
RUN mkdir -p /app/temp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

EXPOSE 5000

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:5000/health || exit 1

CMD ["python", "app.py"] 