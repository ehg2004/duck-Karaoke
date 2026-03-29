from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import karaoke

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # This is the default port for Vite/React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(karaoke.router)

@app.get("/")
async def root():
    return {"message": "Duck Karaoke API is running!"}