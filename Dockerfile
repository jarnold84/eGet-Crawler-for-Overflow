FROM apify/actor-node-playwright-chrome:beta

WORKDIR /app

# ⬇️ Switch to root so we can install system packages
USER root

# ⬇️ Install Python and pip
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ⬇️ Switch back to the default non-root user (good security practice)
USER myuser

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --upgrade pip && pip3 install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "run.py"]
