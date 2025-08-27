import json
import os
import requests

def main():
    # Load Apify input
    with open('/apify/input.json') as f:
        data = json.load(f)

    url = data.get("url")
    if not url:
        print("No URL provided.")
        return

    # Call your own API
    response = requests.post("http://localhost:8000/api/v1/crawl", json=data)
    print("Crawl response:", response.status_code, response.text)

if __name__ == "__main__":
    main()
