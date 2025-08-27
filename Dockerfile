FROM apify/actor-node-playwright-chrome:16.0.0

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
