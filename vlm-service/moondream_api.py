from fastapi import FastAPI, UploadFile, File
import subprocess
import shutil
import os

app = FastAPI(title="Moondream Image Description API")

@app.post("/describe-image/")
async def describe_image(file: UploadFile = File(...)):
    # Save the uploaded image temporarily
    tmp_path = f"/tmp/{file.filename}"
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        # Call the local Moondream CLI
        result = subprocess.run(
            ["ollama", "run", "moondream", f"Describe this image: {tmp_path}"],
            capture_output=True,
            text=True
        )
        description = result.stdout.strip()
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {"description": description}