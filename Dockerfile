FROM python:3.9-slim

# Create non-root user with home directory
RUN groupadd -r streamlit && useradd -r -g streamlit -d /home/streamlit -m streamlit

WORKDIR /app

# Install dependencies as root
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the app with correct ownership
COPY --chown=streamlit:streamlit . .

# Switch to non-root user
USER streamlit

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
