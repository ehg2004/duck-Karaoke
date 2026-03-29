# backend/routers/youtube.py
from fastapi import APIRouter
from pydantic import BaseModel

# The prefix means every endpoint here will start with /api/karaoke
router = APIRouter(
    prefix="/api/karaoke",
    tags=["Karaoke Processing"]
)

# Define what the incoming data from React should look like
class KaraokeRequest(BaseModel):
    url: str

@router.post("/process")
async def process_song(request: KaraokeRequest):
    """
    This endpoint receives the YouTube URL from React.
    Eventually, your logic to download the song and fetch lyrics will go here.
    """
    
    youtube_url = request.url
    
    # --- FUTURE LOGIC GOES HERE ---
    # 1. Use a tool like yt-dlp to extract the audio stream from youtube_url
    # 2. Fetch lyrics from an API (like Musixmatch or Genius)
    # 3. Figure out the timestamps for the lyrics
    # ------------------------------

    # For now, we return mock data so you can build your React frontend
    return {
        "status": "success",
        "original_url": youtube_url,
        "audio_stream_url": "https://example.com/mock_audio.mp3", # You'll eventually serve real audio
        "lyrics": [
            {"time_seconds": 0.5, "text": "Somebody once told me"},
            {"time_seconds": 3.0, "text": "The world is gonna roll me"}
        ]
    }