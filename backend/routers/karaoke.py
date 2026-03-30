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
    song: str

@router.post("/process")
async def process_song(request: KaraokeRequest):
    """
    This endpoint receives the song name from React.
    """
    
    song_name = request.song

    # TO-DO call function to pre process the song here

    return {
        "status": "success",
        "original_song_name": song_name,
    }

def stream_karaoke_lyrics():
    # Sample lyrics data (you would normally fetch this based on the requested song)
    lyrics_data = [
        {"time": 1.0, "phrase": "A duck walked up to a lemonade stand"},
        {"time": 4.0, "phrase": "And he said to the man, running the stand"},
        {"time": 7.5, "phrase": "Hey! (Bomp bomp bomp)"},
        {"time": 9.5, "phrase": "Got any grapes?"}
    ]
    
    start_time = time.time()
    
    for line in lyrics_data:
        target_time = line["time"]
        phrase = line["phrase"]
        
        time_to_wait = target_time - (time.time() - start_time)
        
        if time_to_wait > 0:
            time.sleep(time_to_wait)
            
        response = {
            "current_phrase": phrase,
        }
        
        # REQUIRED FOR STREAMING: Format as Server-Sent Event (SSE)
        yield f"data: {json.dumps(response)}\n\n"

@router.get("/lyrics")
async def play_lyrics():
    return StreamingResponse(stream_karaoke_lyrics(), media_type="text/event-stream")

    