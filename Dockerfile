FROM python:3.10-slim

# Install system dependencies for media processing and OCR
RUN apt-get update && \
    apt-get install -y ffmpeg tesseract-ocr curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the bot
CMD ["python", "bot.py"]
