FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3000

CMD ["streamlit", "run", "app.py",\
     "--server.port=3000",\
     "--server.address=0.0.0.0",\
     "--server.headless=true",\
     "--browser.gatherUsageStats=false"]