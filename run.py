import os
import json
import uvicorn

def main():
    input_path = "/apify/input.json"
    if os.path.exists(input_path):
        with open(input_path) as f:
            input_data = json.load(f)
        print(f"Received Apify input: {input_data}")
    else:
        print("No input.json found. Proceeding without input.")

    # Start FastAPI app
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
