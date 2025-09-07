import os
import uuid
import subprocess
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from gtts import gTTS

OUTPUT_DIR = "generated_movies"
UPLOAD_DIR = "uploads"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ML STUB ---
def interpret_script(script_text: str):
    """
    Simple interpretation:
    - Detects keywords to set background
    - In future: Replace with GPT/Stable Diffusion integration
    """
    script_lower = script_text.lower()
    if "battle" in script_lower:
        return "red"
    elif "love" in script_lower:
        return "pink"
    elif "space" in script_lower:
        return "black"
    return "blue"


def synthesize_speech(script_text: str, audio_file: str):
    """Generate narration audio from script using gTTS."""
    tts = gTTS(script_text)
    tts.save(audio_file)


def stitch_assets(script_text: str, uploads: list, output_file: str):
    """
    Combines uploaded images/videos + narration into one movie.
    If no uploads, generate a solid background with text overlay.
    """
    # Create narration
    narration_file = os.path.join(OUTPUT_DIR, "narration.mp3")
    synthesize_speech(script_text, narration_file)

    # If uploads exist, concatenate
    if uploads:
        file_list_path = os.path.join(OUTPUT_DIR, "inputs.txt")
        with open(file_list_path, "w") as f:
            for up in uploads:
                f.write(f"file '{up}'\n")

        # concat video files or images
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", file_list_path,
            "-i", narration_file, "-c:v", "libx264", "-c:a", "aac",
            "-shortest", "-y", output_file
        ], check=True)
    else:
        # fallback: colored background video
        bg_color = interpret_script(script_text)
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", f"color=c={bg_color}:s=1280x720:d=10",
            "-vf", f"drawtext=text='{script_text[:40]}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
            "-i", narration_file, "-c:v", "libx264", "-c:a", "aac",
            "-shortest", "-y", output_file
        ], check=True)


def preview_movie(job_id: str):
    preview_file = os.path.join(OUTPUT_DIR, f"{job_id}_preview.jpg")
    movie_file = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    if not os.path.exists(movie_file):
        return None
    subprocess.run([
        "ffmpeg", "-i", movie_file, "-ss", "00:00:02.000", "-vframes", "1", preview_file, "-y"
    ], check=True)
    return preview_file


@app.post("/generate")
async def generate(
    script: str = Form(...),
    files: list[UploadFile] = File(None)
):
    job_id = str(uuid.uuid4())
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")

    # Save uploads
    saved_files = []
    if files:
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())
            saved_files.append(file_path)

    # Build final movie
    stitch_assets(script, saved_files, output_file)

    return {"job_id": job_id, "status": "done"}


@app.get("/preview/{job_id}")
async def preview(job_id: str):
    preview_path = preview_movie(job_id)
    if preview_path:
        return FileResponse(preview_path, media_type="image/jpeg")
    return {"error": "Preview not available"}


@app.get("/download/{job_id}")
async def download(job_id: str):
    movie_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    if os.path.exists(movie_path):
        return FileResponse(movie_path, media_type="video/mp4", filename=f"{job_id}.mp4")
    return {"error": "Movie not found"}


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html", "r") as f:
        return f.read()
