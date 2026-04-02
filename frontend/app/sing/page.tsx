"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation"; 
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FinalResults, StreamEvent } from "@/lib/types";

const SingContent = () => {
    const searchParams = useSearchParams();
    
    const sessionId = searchParams.get("session_id") || "";
    const songName = searchParams.get("song") || "Unknown Song";

    const [currentLyric, setCurrentLyric] = useState("Waiting for the music to start... 🎵");
    const [recentTranscriptions, setRecentTranscriptions] = useState<string[]>([]);
    const [isStopping, setIsStopping] = useState(false);
    const [isSessionEnded, setIsSessionEnded] = useState(false);
    const [finalResults, setFinalResults] = useState<FinalResults | null>(null);
    
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
                setIsSessionEnded(true);
                
                // Fetch final results
                await fetchFinalResults();
            } else {
                console.error("Failed to stop session:", response.statusText);
            }
        } catch (error) {
            console.error("Error stopping session:", error);
        } finally {
            setIsStopping(false);
        }
    };
    
    const fetchFinalResults = async () => {
        try {
            const response = await fetch("http://localhost:8000/api/karaoke/FinalResults", {
                method: "GET",
            });
            
            if (response.ok) {
                const data: FinalResults = await response.json();
                console.log("Final results:", data);
                setFinalResults(data);
            } else {
                console.error("Failed to fetch final results:", response.statusText);
            }
        } catch (error) {
            console.error("Error fetching final results:", error);
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
                            const jsonData: StreamEvent = JSON.parse(line.replace('data: ', ''));
                            
                            // Update the React state with the lyric or result
                            if (isMounted) {
                                if (jsonData.type === "lyric") {
                                    setCurrentLyric(jsonData.text);
                                } else if (jsonData.type === "result") {
                                    // Only add to transcription log
                                    setRecentTranscriptions(prev => [...prev, jsonData.text].slice(-5)); // Keep last 5
                                } else if ('error' in jsonData) {
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
            try {
                abortController.abort();
            } catch (e) {
                // Ignore abort errors - stream may already be complete
            }
        };
    }, []); // Empty array - only run once on mount

    return (
        <>
            {!isSessionEnded ? (
                <Card className="w-full max-w-5xl p-20 border-4 border-yellow-400">
                    <CardHeader className="mb-8">
                        <CardTitle className="text-5xl text-center">
                            Singing: <span className="text-yellow-600">"{songName}"</span>
                        </CardTitle>
                    </CardHeader>
                    
                    <CardContent>
                        <div className="flex flex-col items-center justify-center gap-8">
                            {/* Current Lyric Display */}
                            <div 
                                key={currentLyric}
                                className="text-4xl text-center font-bold text-yellow-500 min-h-[60px] animate-in fade-in zoom-in-95 slide-in-from-bottom-2 duration-500"
                            >
                                {currentLyric}
                            </div>
                            
                            {/* Recent Transcriptions Log */}
                            {recentTranscriptions.length > 0 && (
                                <div className="w-full bg-gray-100 rounded-lg p-4 max-h-48 overflow-y-auto">
                                    <h3 className="font-bold text-lg mb-2">You Sang:</h3>
                                    <div className="space-y-2">
                                        {recentTranscriptions.map((text, idx) => (
                                            <div key={idx} className="text-sm bg-white p-2 rounded border-l-4 border-yellow-400">
                                                <span className="font-semibold">"{text}"</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

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
            ) : finalResults ? (
                <Card className="w-full max-w-5xl p-20 border-4 border-yellow-400">
                    <CardHeader className="mb-8">
                        <CardTitle className="text-5xl text-center">
                            Results: <span className="text-yellow-600">"{finalResults.song_name}"</span>
                        </CardTitle>
                    </CardHeader>
                    
                    <CardContent>
                        <div className="flex flex-col gap-6">
                            {/* Overall Summary Block */}
                            {finalResults.summary && (
                                <div className="w-full bg-gradient-to-br from-yellow-100 to-yellow-50 p-6 rounded-lg border-3 border-yellow-500 shadow-lg">
                                    <h2 className="text-2xl font-bold mb-4 text-gray-800">Your Performance</h2>
                                    <div className="grid grid-cols-2 gap-6">
                                        <div>
                                            <div className="text-sm font-semibold text-gray-700 mb-2">Original Lyrics</div>
                                            <div className="bg-white p-4 rounded-lg border border-yellow-300 text-gray-800 leading-relaxed max-h-64 overflow-y-auto">
                                                "{finalResults.summary.lyrics}"
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-gray-700 mb-2">Everything You Sang</div>
                                            <div className="bg-white p-4 rounded-lg border border-yellow-400 text-yellow-700 leading-relaxed max-h-64 overflow-y-auto font-semibold">
                                                "{finalResults.summary.you_sang || '(No transcriptions recorded)'}"
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <Button 
                                className="bg-yellow-400 text-black hover:bg-yellow-500 h-12 text-lg px-8 font-bold" 
                                onClick={() => window.location.href = "/"}
                            >
                                🦆 Back to Home
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            ) : (
                <Card className="w-full max-w-5xl p-20 border-4 border-yellow-400">
                    <CardHeader className="mb-8">
                        <CardTitle className="text-5xl text-center">Loading Results...</CardTitle>
                    </CardHeader>
                </Card>
            )}
        </>
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