from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from googleapiclient.discovery import build
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

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Initialize YouTube Data API client without failing at startup
youtube = None
if YOUTUBE_API_KEY:
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        logger.info("YouTube Data API client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize YouTube Data API client: {str(e)}")
else:
    logger.warning("YOUTUBE_API_KEY environment variable is missing. API-dependent endpoints will fail.")

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
    if not YOUTUBE_API_KEY:
        logger.error("YOUTUBE_API_KEY is missing during request.")
        raise HTTPException(status_code=500, detail="YOUTUBE_API_KEY environment variable is missing.")
    if not youtube:
        logger.error("YouTube Data API client not initialized.")
        raise HTTPException(status_code=500, detail="YouTube Data API client not initialized. Please check YOUTUBE_API_KEY validity.")

    try:
        # Extract video ID
        if "watch?v=" in link.url:
            video_id = link.url.split("v=")[1].split("&")[0] if "&" in link.url else link.url.split("v=")[1]
            video_id = video_id.split("?")[0]
        else:
            video_id = link.url.split("/")[-1].split("?")[0]

        # Fetch metadata using YouTube Data API
        request = youtube.videos().list(part="snippet,contentDetails", id=video_id)
        response = request.execute()
        if not response["items"]:
            raise HTTPException(status_code=404, detail="Video not found")
        video = response["items"][0]

        description = video["snippet"]["description"]
        album = None
        for line in description.split("\n"):
            if "Album:" in line:
                album = line.split("Album:")[1].strip()
                break

        # Parse duration (ISO 8601 format, e.g., PT3M33S)
        duration = video["contentDetails"]["duration"]
        if duration:
            duration = duration.replace("PT", "").replace("S", "")
            minutes = 0
            if "M" in duration:
                minutes = int(duration.split("M")[0])
                seconds = int(duration.split("M")[1]) if duration.split("M")[1] else 0
            else:
                seconds = int(duration)
            duration = f"{minutes}:{seconds:02d}"

        metadata = Metadata(
            title=video["snippet"]["title"],
            channel=video["snippet"]["channelTitle"],
            duration=duration,
            thumbnail=video["snippet"]["thumbnails"].get("high", {}).get("url"),
            album=album
        )

        # Check licensing using YouTube Data API
        licensed_content = video["contentDetails"]["licensedContent"]
        description_lower = video["snippet"]["description"].lower()
        is_downloadable = not licensed_content or "creative commons" in description_lower

        return ProcessResponse(metadata=metadata, download_available=is_downloadable)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error processing link: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing request: {str(e)}")

@app.post("/download")
async def download(link: MusicLink):
    if not YOUTUBE_API_KEY:
        logger.error("YOUTUBE_API_KEY is missing during download request.")
        raise HTTPException(status_code=500, detail="YOUTUBE_API_KEY environment variable is missing.")
    if not youtube:
        logger.error("YouTube Data API client not initialized during download.")
        raise HTTPException(status_code=500, detail="YouTube Data API client not initialized. Please check YOUTUBE_API_KEY validity.")

    try:
        # Extract video ID
        if "watch?v=" in link.url:
            video_id = link.url.split("v=")[1].split("&")[0] if "&" in link.url else link.url.split("v=")[1]
            video_id = video_id.split("?")[0]
        else:
            video_id = link.url.split("/")[-1].split("?")[0]

        # Verify licensing
        request = youtube.videos().list(part="contentDetails,snippet", id=video_id)
        response = request.execute()
        if not response["items"]:
            raise HTTPException(status_code=404, detail="Video not found")
        video = response["items"][0]

        licensed_content = video["contentDetails"]["licensedContent"]
        description_lower = video["snippet"]["description"].lower()
        is_downloadable = not licensed_content or "creative commons" in description_lower

        if not is_downloadable:
            raise HTTPException(status_code=403, detail="Video is not licensed for download.")

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