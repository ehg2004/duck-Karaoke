"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation"; 
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const SingContent = () => {
    const searchParams = useSearchParams();
    
    const sessionId = searchParams.get("session_id") || "";
    const songName = searchParams.get("song") || "Unknown Song";

    const [currentLyric, setCurrentLyric] = useState("Waiting for the music to start... 🎵");
    const [isStopping, setIsStopping] = useState(false);
    
    const stopSession = async () => {
        if (isStopping || !sessionId) return;
        
        setIsStopping(true);
        try {
            console.log(`Stopping session: ${sessionId}`);
            const response = await fetch(
                `http://localhost:8000/api/karaoke/stop_session?session_id=${sessionId}`,
                { method: "GET" }
            );
            
            if (response.ok) {
                const data = await response.json();
                console.log("Session stopped:", data);
            } else {
                console.error("Failed to stop session:", response.statusText);
            }
        } catch (error) {
            console.error("Error stopping session:", error);
        } finally {
            // Navigate away regardless of success/failure
            window.location.href = "/";
        }
    };
    
    useEffect(() => {
        let isMounted = true;
        let abortController = new AbortController();

        const startKaraokeStream = async () => {
            try {
                if (!sessionId) {
                    throw new Error("No session ID found. Please process a song first.");
                }

                // Step 1: Start the karaoke session by calling POST /play_song
                console.log(`Starting karaoke session with ID: ${sessionId}`);
                const playResponse = await fetch("http://localhost:8000/api/karaoke/play_song", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        session_id: sessionId,
                    }),
                    signal: abortController.signal,
                });

                if (!playResponse.ok) {
                    throw new Error(`Failed to start karaoke session: ${playResponse.statusText}`);
                }

                const playData = await playResponse.json();
                console.log("Karaoke session started:", playData);

                // Step 2: Now connect to the streaming endpoint with session_id parameter
                const streamUrl = new URL("http://localhost:8000/api/karaoke/stream_karaoke");
                streamUrl.searchParams.append("session_id", sessionId);
                
                const response = await fetch(streamUrl.toString(), {
                    signal: abortController.signal,
                });
                
                if (!response.body) {
                    throw new Error("No response body from stream endpoint");
                }

                // Create a reader to read the incoming chunks of data
                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");

                // Loop continuously, waiting for the next chunk from Python
                while (true) {
                    const { done, value } = await reader.read();
                    
                    // If the backend finishes sending data, exit the loop
                    if (done) break; 

                    // Decode the raw bytes into text
                    const chunk = decoder.decode(value);
                    
                    // Parse the Server-Sent Event format we made in Python
                    const lines = chunk.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const jsonData = JSON.parse(line.replace('data: ', ''));
                            
                            // Update the React state with the lyric or result
                            if (isMounted) {
                                if (jsonData.type === "lyric") {
                                    setCurrentLyric(jsonData.text);
                                } else if (jsonData.type === "result") {
                                    // Show both lyric and user's transcription
                                    setCurrentLyric(`You sang: "${jsonData.text}" (${Math.round(jsonData.score * 100)}%)`);
                                } else if (jsonData.error) {
                                    setCurrentLyric(`Error: ${jsonData.error}`);
                                }
                            }
                        }
                    }
                }
            } catch (error) {
                console.error("Stream failed:", error);
                if (isMounted) setCurrentLyric("Oops! Something went wrong. 😅");
            }
        };

        startKaraokeStream();

        // Cleanup function if the user navigates away early
        return () => {
            isMounted = false;
            abortController.abort();
        };
    }, []); // Empty array - only run once on mount

    return (
        <Card className="w-full max-w-5xl p-20 border-4 border-yellow-400">
            <CardHeader className="mb-8">
                {/* 4. Display the song name dynamically! */}
                <CardTitle className="text-5xl text-center">
                    Singing: <span className="text-yellow-600">"{songName}"</span>
                </CardTitle>
            </CardHeader>
            
            <CardContent>
                <div className="flex flex-col items-center justify-center gap-8">

                    <div 
                        key={currentLyric}
                        className="text-4xl text-center font-bold text-yellow-500 min-h-[60px] animate-in fade-in zoom-in-95 slide-in-from-bottom-2 duration-500"
                    >
                        {currentLyric}
                    </div>

                    <Button 
                        variant="outline" 
                        className="mt-8 h-10 text-xl px-7" 
                        onClick={stopSession}
                        disabled={isStopping}
                    >
                        {isStopping ? "Stopping..." : "⏹ Stop Session"}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
};

// The main page component
const SingPage = () => {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center p-8">
            <Suspense fallback={<div>Loading the stage...</div>}>
                <SingContent />
            </Suspense>
        </main>
    );
}
 
export default SingPage;