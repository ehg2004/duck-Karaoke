# backend/routers/karaoke.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import time
import json
import threading
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from queue import Queue, Empty

# Import preprocessing functions
from backend.core.preProcessSong import (
    preProcessSong, 
    downloadResources, 
    get_yt_music_results, 
    testYTresults, 
    save_synced_lyrics,
    upsert_index_row,
    _to_resource_relative
)

# Import ASR module (handle dash in filename)
import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "asr_duck_module",
    "/home/ehg2004/karaoke_ws/duck-Karaoke/backend/core/ASR-duck.py"
)
asr_module = importlib.util.module_from_spec(spec)
sys.modules["asr_duck_module"] = asr_module
spec.loader.exec_module(asr_module)
AudioTranscriber = asr_module.AudioTranscriber

# The prefix means every endpoint here will start with /api/karaoke
router = APIRouter(
    prefix="/api/karaoke",
    tags=["Karaoke Processing"]
)

# Define request bodies
class KaraokeRequest(BaseModel):
    song: str
    artist: Optional[str] = None

class PlaySongRequest(BaseModel):
    session_id: str

# Global state for karaoke session
class KaraokeSession:
    """Manages a single karaoke session"""
    def __init__(self, song_name: str, lyrics: List[Dict], instrumental_url: str):
        self.song_name = song_name
        self.lyrics = lyrics  # List of {"time": float, "phrase": str}
        self.instrumental_url = instrumental_url
        self.transcription_buffer = []  # {"timestamp": float, "text": str, "score": float}
        self.session_start_time = None
        self.is_active = False
        self.asr_thread: Optional[AudioTranscriber] = None
        self.final_results = []
        self.audio_player = None  # Subprocess for audio playback
        self.stream_connected = False  # Flag to prevent multiple concurrent streams

# Global sessions dictionary
_sessions: Dict[str, KaraokeSession] = {}
_current_session_id: Optional[str] = None
_sessions_lock = threading.Lock()

def _parse_lrc_lyrics(lrc_path: str) -> List[Dict]:
    """Parse .lrc lyrics file into structured format"""
    lyrics = []
    if not os.path.exists(lrc_path):
        return lyrics
    
    try:
        with open(lrc_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Parse LRC format: [mm:ss.xx]lyrics text
                if line.startswith('[') and ']' in line:
                    time_str = line[1:line.index(']')]
                    text = line[line.index(']') + 1:].strip()
                    
                    try:
                        # Convert mm:ss.xx to seconds
                        parts = time_str.split(':')
                        minutes = int(parts[0])
                        seconds = float(parts[1])
                        timestamp = minutes * 60 + seconds
                        
                        if text:
                            lyrics.append({
                                "time": timestamp,
                                "phrase": text
                            })
                    except (ValueError, IndexError):
                        continue
    except Exception as e:
        print(f"Error parsing LRC file: {e}")
    
    return lyrics

def _play_audio(audio_path: str):
    """
    Play an audio file using ffplay (CLI).
    Returns the Popen object so it can be stopped later.
    """
    try:
        import subprocess
        player = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", audio_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Started playing audio: {audio_path}")
        return player
    except FileNotFoundError:
        print("Warning: ffplay not found. Make sure ffmpeg is installed.")
        print("Install with: sudo apt-get install ffmpeg (Ubuntu/Debian) or brew install ffmpeg (Mac)")
        return None
    except Exception as e:
        print(f"Error starting audio playback: {e}")
        return None

@router.post("/process")
async def process_song(request: KaraokeRequest):
    """
    Process a song: search YouTube Music, download, perform vocal separation, extract lyrics.
    Returns instrumental URL and lyrics data.
    """
    try:
        song_name = request.song
        artist_name = request.artist or song_name  # Use song name as fallback if no artist
        
        print(f"Searching for song: {song_name} by {artist_name}")
        
        # Search YouTube Music for the song
        yt_results = get_yt_music_results(song_name, artist_name, limit=3)
        
        if not yt_results:
            raise HTTPException(status_code=404, detail="No YouTube Music results found for this song")
        
        # Test results and select the best one with synced lyrics
        selected_lyrics, selected_track = testYTresults(yt_results)
        print(f"Selected track: {selected_track['title']} by {selected_track['artist']}")
        
        # Create output directories
        output_dir = "resources/splitted"
        os.makedirs(output_dir, exist_ok=True)
        
        # Download song from YouTube
        print(f"Downloading song from: {selected_track['url']}")
        downloaded_path = downloadResources(str(selected_track['url']), "resources/originals")
        
        # Perform vocal separation
        print(f"Processing song for vocal separation: {downloaded_path}")
        vocal_path, instrumental_path = preProcessSong(
            downloaded_path, 
            output_dir,
            useGPU=False
        )
        
        # Save synced lyrics if found
        lyrics_path = save_synced_lyrics(selected_track, selected_lyrics, "resources/lyrics")
        
        # Parse lyrics into structured format
        lyrics_data = []
        if lyrics_path:
            lyrics_data = _parse_lrc_lyrics(lyrics_path)
        
        if not lyrics_data:
            print(f"Warning: No synced lyrics found for {song_name}")
            lyrics_data = []

        print("Lyrics data parsed:", lyrics_data)
        
        # Update the index CSV
        upsert_index_row(
            "resources/index.csv",
            {
                "song_name": selected_track.get("title", ""),
                "artist": selected_track.get("artist", ""),
                "duration_seconds": selected_track.get("duration_seconds", 0),
                "voice_audio_path": _to_resource_relative(vocal_path),
                "instruments_audio_path": _to_resource_relative(instrumental_path),
                "original_audio_path": _to_resource_relative(downloaded_path),
                "lyrics_timestamp_path": _to_resource_relative(lyrics_path) if lyrics_path else "",
            },
        )
        
        # Create session
        session_id = f"session_{int(time.time() * 1000)}"
        session = KaraokeSession(
            song_name=selected_track.get("title", song_name),
            lyrics=lyrics_data,
            instrumental_url=instrumental_path
        )
        
        with _sessions_lock:
            _sessions[session_id] = session
        
        return {
            "status": "success",
            "session_id": session_id,
            "song_name": selected_track.get("title", ""),
            "artist": selected_track.get("artist", ""),
            "instrumental_url": instrumental_path,
            "lyrics": lyrics_data,
            "lyrics_count": len(lyrics_data),
            "message": f"Successfully processed {selected_track['title']} - synced lyrics available" if lyrics_data else "Processed but no synced lyrics found"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing song: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing song: {str(e)}")

@router.post("/play_song")
async def play_song(request: PlaySongRequest):
    """
    Start a karaoke session: initialize ASR thread and KaraokeRun.
    """
    global _current_session_id
    
    try:
        session_id = request.session_id
        
        # Find session by ID
        with _sessions_lock:
            if session_id not in _sessions:
                raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found. Please process a song first.")
            
            session = _sessions[session_id]
            _current_session_id = session_id
            
            # Initialize ASR thread
            print(f"Starting ASR thread for session: {session_id}")
            session.asr_thread = AudioTranscriber(
                sample_rate=48000,
                channels=1,
                # vad_timeout_ms=3000,
                # vad_threshold=0.65,
                verbose=False,
                disable_denoiser=False,
                device="cuda",
                save_audio=True,
                audio_save_dir=f"resources/debug_audio/{session_id}"
            )
            
            session.is_active = True
            session.session_start_time = time.time()
            
            # Start playing the instrumental audio
            print(f"Starting audio playback: {session.instrumental_url}")
            session.audio_player = _play_audio(session.instrumental_url)
        
        
        return {
            "status": "success",
            "message": f"Karaoke session started",
            "session_id": session_id,
            "song_name": session.song_name
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error starting karaoke session: {e}")
        raise HTTPException(status_code=500, detail=f"Error starting session: {str(e)}")

def _stream_karaoke_data(session_id: str):
    """
    Core streaming generator that yields lyrics and ASR results in real-time.
    Implements the loop from the sequence diagram.
    """

    print(f"Client attempting to connect to karaoke stream for session {session_id}")
    
    with _sessions_lock:
        if session_id not in _sessions:
            yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
            return
        
        session = _sessions[session_id]
        
        # Prevent multiple concurrent streams
        if session.stream_connected:
            print(f"Stream already connected for session {session_id}. Rejecting new connection.")
            yield f"data: {json.dumps({'error': 'Stream already active for this session'})}\n\n"
            return
        
        session.stream_connected = True
        print(f"Client connected to karaoke stream for session {session_id}")
    
    if not session.is_active:
        yield f"data: {json.dumps({'error': 'Session not active'})}\n\n"
        with _sessions_lock:
            session.stream_connected = False
        return
    
    # Track which lyrics line we've already sent
    lyrics_index = 0
    session_start = session.session_start_time
    
    try:
        while session.is_active:
            elapsed_time = time.time() - session_start
            
            # Check for new lyrics to display
            while lyrics_index < len(session.lyrics):
                lyric = session.lyrics[lyrics_index]
                
                if lyric["time"] <= elapsed_time:
                    response = {
                        "type": "lyric",
                        "new": True,
                        "text": lyric["phrase"],
                        "timestamp": lyric["time"],
                        "index": lyrics_index
                    }
                    lyrics_index += 1
                    yield f"data: {json.dumps(response)}\n\n"
                    time.sleep(0.01)  # Small delay to avoid overwhelming client
                else:
                    break
            
            # Check for new ASR results from transcription buffer
            if session.transcription_buffer:
                # Get the most recent transcription
                transcription = session.transcription_buffer.pop(0)
                
                # Find matching lyrics based on timestamp
                matched_lyric_index = None
                for i, lyric in enumerate(session.lyrics):
                    if abs(lyric["time"] - transcription["timestamp"]) < 2.0:  # 2 second tolerance
                        matched_lyric_index = i
                        break
                
                response = {
                    "type": "result",
                    "text": transcription["text"],
                    "timestamp": transcription["timestamp"],
                    "score": transcription.get("score", 0.0),
                    "matched_lyric_index": matched_lyric_index
                }
                yield f"data: {json.dumps(response)}\n\n"
            
            # Update ASR thread (process audio queue)
            if session.asr_thread:
                session.asr_thread.process_audio_from_queue()
            
            time.sleep(0.05)  # Poll rate: 20Hz
    
    except GeneratorExit:
        print(f"Client disconnected from stream for session {session_id}")
    finally:
        with _sessions_lock:
            session.stream_connected = False

@router.get("/stream_karaoke")
async def stream_karaoke(session_id: str):
    """
    Streaming endpoint for real-time karaoke data (lyrics + ASR results).
    Uses Server-Sent Events (SSE) format.
    """
    return StreamingResponse(
        _stream_karaoke_data(session_id),
        media_type="text/event-stream"
    )

@router.get("/stop_session")
async def stop_session(session_id: str):
    """
    Stop a karaoke session: terminate ASR thread, stop audio playback, and clean up.
    """
    try:
        with _sessions_lock:
            if session_id not in _sessions:
                raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
            
            session = _sessions[session_id]
            
            # Mark session as inactive to stop streaming
            session.is_active = False
            session.stream_connected = False
            
            # Stop audio playback
            if session.audio_player:
                try:
                    session.audio_player.terminate()
                    session.audio_player.wait(timeout=2)
                    print(f"[{datetime.now()}] Stopped audio playback for {session_id}")
                except Exception as e:
                    print(f"[{datetime.now()}] Error stopping audio player: {e}")
            
            # Stop ASR thread
            if session.asr_thread:
                try:
                    session.asr_thread.stop()
                    print(f"[{datetime.now()}] Stopped ASR thread for {session_id}")
                except Exception as e:
                    print(f"[{datetime.now()}] Error stopping ASR thread: {e}")
        
        return {
            "status": "success",
            "message": f"Session {session_id} stopped",
            "session_id": session_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error stopping session: {e}")
        raise HTTPException(status_code=500, detail=f"Error stopping session: {str(e)}")

@router.get("/FinalResults")
async def get_final_results():
    """
    Retrieve final karaoke results after session ends.
    """
    global _current_session_id
    
    try:
        with _sessions_lock:
            if not _current_session_id or _current_session_id not in _sessions:
                raise HTTPException(status_code=404, detail="No active session")
            
            session = _sessions[_current_session_id]
            
            # Mark session as inactive
            session.is_active = False
            
            # Stop audio playback
            if session.audio_player:
                session.audio_player.terminate()
                print(f"Stopped audio playback")
            
            # Stop ASR thread
            if session.asr_thread:
                session.asr_thread.stop()
            
            # Compile final results
            final_results = {
                "song_name": session.song_name,
                "session_duration": time.time() - session.session_start_time if session.session_start_time else 0,
                "transcriptions": session.transcription_buffer,
                "total_transcriptions": len(session.transcription_buffer),
                "lyrics_count": len(session.lyrics),
                "completed_at": datetime.now().isoformat()
            }
            
            session.final_results = final_results
        
        return final_results
    
    except Exception as e:
        print(f"Error retrieving final results: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving results: {str(e)}")

    