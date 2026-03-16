FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot.py config.py ./

# Non-root user for security
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "bot.py"]
