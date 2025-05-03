from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests
import yt_dlp
import os
from dotenv import load_dotenv
from mangum import Mangum
import io
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update to your frontend domain for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

class MusicLink(BaseModel):
    url: str

class Metadata(BaseModel):
    title: str
    channel: str
    duration: str | None
    thumbnail: str | None
    album: str | None

class ProcessResponse(BaseModel):
    metadata: Metadata
    download_available: bool

@app.get("/")
async def root():
    return {"message": "Welcome to the YouTube Music Downloader API"}

@app.get("/favicon.ico")
async def favicon():
    return None

@app.post("/process-link", response_model=ProcessResponse)
async def process_link(link: MusicLink):
    if not RAPIDAPI_KEY:
        logger.error("RAPIDAPI_KEY is missing during request.")
        raise HTTPException(status_code=500, detail="RAPIDAPI_KEY environment variable is missing.")

    try:
        # Extract video ID
        if "watch?v=" in link.url:
            video_id = link.url.split("v=")[1].split("&")[0] if "&" in link.url else link.url.split("v=")[1]
            video_id = video_id.split("?")[0]
        else:
            video_id = link.url.split("/")[-1].split("?")[0]

        # Fetch metadata using RapidAPI
        metadata_url = "https://youtube138.p.rapidapi.com/video/details"
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "youtube138.p.rapidapi.com",
        }
        params = {"id": video_id}
        response = requests.get(metadata_url, headers=headers, params=params)
        logger.info(f"RapidAPI Metadata Response Status: {response.status_code}")
        response.raise_for_status()
        result = response.json()

        # Extract metadata
        author = result.get("author", {})
        channel_name = author.get("title", "Unknown Channel") if isinstance(author, dict) else "Unknown Channel"

        description = result.get("description", "")
        album = None
        for line in description.split("\n"):
            if "Album:" in line:
                album = line.split("Album:")[1].strip()
                break

        thumbnails = result.get("thumbnails", [])
        thumbnail_url = None
        if thumbnails:
            if isinstance(thumbnails, list):
                thumbnail_url = thumbnails[0].get("url") if thumbnails else None
            elif isinstance(thumbnails, dict):
                thumbnail_url = thumbnails.get("high", {}).get("url")

        duration = result.get("lengthSeconds")
        if duration:
            duration = int(duration)
            minutes = duration // 60
            seconds = duration % 60
            duration = f"{minutes}:{seconds:02d}"

        metadata = Metadata(
            title=result.get("title", "Unknown Title"),
            channel=channel_name,
            duration=duration,
            thumbnail=thumbnail_url,
            album=album
        )

        # Assume download availability (RapidAPI doesn't provide licensing info)
        # We'll rely on yt-dlp for actual download checks
        download_available = True  # Placeholder; refine based on needs

        return ProcessResponse(metadata=metadata, download_available=download_available)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error processing link: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing request: {str(e)}")

@app.post("/download")
async def download(link: MusicLink):
    if not RAPIDAPI_KEY:
        logger.error("RAPIDAPI_KEY is missing during download request.")
        raise HTTPException(status_code=500, detail="RAPIDAPI_KEY environment variable is missing.")

    try:
        # Extract video ID
        if "watch?v=" in link.url:
            video_id = link.url.split("v=")[1].split("&")[0] if "&" in link.url else link.url.split("v=")[1]
            video_id = video_id.split("?")[0]
        else:
            video_id = link.url.split("/")[-1].split("?")[0]

        # Download with yt-dlp
        os.makedirs("downloads", exist_ok=True)
        file_path = f"downloads/{video_id}.mp3"
        ydl_opts = {
            "format": "bestaudio[filesize<10M]",
            "extract_audio": True,
            "audio_format": "mp3",
            "outtmpl": file_path,
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([link.url])

        # Stream the file
        def iterfile():
            with open(file_path, "rb") as file:
                yield from file
            os.remove(file_path)  # Clean up after streaming

        return StreamingResponse(
            iterfile(),
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={video_id}.mp3"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error downloading file: {str(e)}")

# Vercel serverless handler
handler = Mangum(app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)