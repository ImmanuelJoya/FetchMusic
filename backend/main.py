from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from googleapiclient.discovery import build
import requests
import yt_dlp
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Initialize YouTube Data API client (or None if key is missing)
youtube = None
if YOUTUBE_API_KEY:
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    except Exception as e:
        print(f"Failed to initialize YouTube Data API client: {str(e)}")

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
    download_url: str | None

@app.get("/")
async def root():
    return {"message": "Welcome to the YouTube Music Downloader API"}

@app.get("/favicon.ico")
async def favicon():
    return None

@app.post("/process-link", response_model=ProcessResponse)
async def process_link(link: MusicLink):
    try:
        # Extract video ID
        video_id = link.url.split("v=")[1].split("&")[0] if "watch?v=" in link.url else link.url.split("/")[-1]

        # Fetch metadata using the YouTube RapidAPI endpoint
        metadata_url = "https://youtube138.p.rapidapi.com/video/details"
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "youtube138.p.rapidapi.com",
        }
        params = {"id": video_id}
        response = requests.get(metadata_url, headers=headers, params=params)
        print(f"RapidAPI Metadata Response Status: {response.status_code}")
        print(f"RapidAPI Metadata Response Body: {response.text}")
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

        duration = result.get("lengthSeconds") or result.get("duration")
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

        # Check licensing using YouTube Data API (if available)
        download_url = None
        is_downloadable = False  # Default to false if YouTube Data API is unavailable
        if youtube:
            try:
                request = youtube.videos().list(part="contentDetails,snippet", id=video_id)
                response = request.execute()
                if not response["items"]:
                    raise HTTPException(status_code=404, detail="Video not found")
                video = response["items"][0]
                licensed_content = video["contentDetails"]["licensedContent"]
                description_lower = video["snippet"]["description"].lower()
                is_downloadable = not licensed_content or "creative commons" in description_lower
            except Exception as yt_e:
                print(f"YouTube Data API Error: {str(yt_e)}")

        if is_downloadable:
            # Try to fetch download URL using the YouTube RapidAPI endpoint
            try:
                download_api_url = "https://youtube138.p.rapidapi.com/video/download"
                response = requests.get(download_api_url, headers=headers, params=params)
                print(f"RapidAPI Download Response Status: {response.status_code}")
                print(f"RapidAPI Download Response Body: {response.text}")
                response.raise_for_status()
                download_result = response.json()
                download_url = download_result.get("download_url")
            except Exception as e:
                print(f"RapidAPI Download Error: {str(e)}")
                # Fallback to yt-dlp
                try:
                    ydl_opts = {
                        "format": "bestaudio",
                        "extract_audio": True,
                        "audio_format": "mp3",
                        "outtmpl": f"downloads/{video_id}.mp3",
                        "quiet": True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([link.url])
                    download_url = f"http://localhost:8000/downloads/{video_id}.mp3"
                except Exception as dl_e:
                    print(f"yt-dlp Error: {str(dl_e)}")

        return ProcessResponse(metadata=metadata, download_url=download_url)
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    