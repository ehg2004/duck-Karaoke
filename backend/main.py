from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import karaoke
import signal
import sys

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # This is the default port for Vite/React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(karaoke.router)

def cleanup_sessions():
    """Clean up all active karaoke sessions on shutdown."""
    from datetime import datetime
    print(f"\n[{datetime.now()}] Cleaning up active sessions...")
    
    with karaoke._sessions_lock:
        for session_id, session in karaoke._sessions.items():
            print(f"[{datetime.now()}] Cleaning up session: {session_id}")
            
            # Stop ASR thread
            if session.asr_thread:
                try:
                    session.asr_thread.stop()
                    print(f"[{datetime.now()}] Stopped ASR thread for {session_id}")
                except Exception as e:
                    print(f"[{datetime.now()}] Error stopping ASR thread: {e}")
            
            # Stop audio player
            if session.audio_player:
                try:
                    session.audio_player.terminate()
                    session.audio_player.wait(timeout=2)
                    print(f"[{datetime.now()}] Stopped audio player for {session_id}")
                except Exception as e:
                    print(f"[{datetime.now()}] Error stopping audio player: {e}")
    
    print(f"[{datetime.now()}] Cleanup complete")

def signal_handler(sig, frame):
    """Handle Ctrl+C by cleaning up resources."""
    cleanup_sessions()
    print("Exiting gracefully...")
    sys.exit(0)

# Register signal handler for Ctrl+C
signal.signal(signal.SIGINT, signal_handler)

@app.on_event("shutdown")
async def shutdown_event():
    """Handle FastAPI shutdown event."""
    cleanup_sessions()

@app.get("/")
async def root():
    return {"message": "Duck Karaoke API is running!"}