FROM python:3.11-slim

WORKDIR /app

# System deps for PDF extraction (poppler for pdf2image, tesseract for OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY decision_engine/ ./decision_engine/
COPY config/ ./config/
COPY prompts/ ./prompts/
COPY Data/ ./Data/
COPY Database/ ./Database/
COPY docker_startup.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8000

CMD ["./entrypoint.sh"]
