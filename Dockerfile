FROM python:3.12.2

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        mediainfo libmediainfo0v5 libmediainfo-dev \
        ca-certificates && \
    ldconfig && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /DreamxBotz

# Copy dependency files first so Docker can cache this layer
COPY requirements.txt constraints.txt ./

RUN pip install --no-cache-dir --upgrade pip --root-user-action=ignore && \
    pip install --no-cache-dir --root-user-action=ignore \
        -r requirements.txt -c constraints.txt

COPY . .

CMD ["python3", "bot.py"]
