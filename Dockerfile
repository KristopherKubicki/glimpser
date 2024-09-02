FROM python:3.8-slim

# Install runtime dependencies and networking tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libsqlite3-0 curl iputils-ping net-tools netcat-traditional \
    libsqlite3-dev libjpeg62-turbo libpng16-16 libtiff6 libfreetype6 \
    libwebp7 unzip poppler-utils xvfb ffmpeg libssl3 libffi8 libbz2-1.0 \
    libreadline8 libncurses5 libncursesw6 libxml2 libxslt1.1 \
    build-essential gcc zlib1g wget gnupg iproute2 wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
RUN CHROME_DRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE) \
    && wget -N http://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip -P ~/ \
    && unzip ~/chromedriver_linux64.zip -d ~/ \
    && rm ~/chromedriver_linux64.zip \
    && mv -f ~/chromedriver /usr/local/bin/chromedriver \
    && chown root:root /usr/local/bin/chromedriver \
    && chmod 0755 /usr/local/bin/chromedriver

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY . .

# Set environment variables
ENV FLASK_APP=main.py \
    FLASK_RUN_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8082

# Run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8082", "--workers", "4", "main:app"]
