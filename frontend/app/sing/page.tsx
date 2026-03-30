"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation"; 
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const SingContent = () => {
    const searchParams = useSearchParams();
    
    const songName = searchParams.get("song") || "Unknown Song";

    const [currentLyric, setCurrentLyric] = useState("Waiting for the music to start... 🎵");
    
    useEffect(() => {
        let isMounted = true;

        const startKaraokeStream = async () => {
            try {
                // Call streaming endpoint
                const response = await fetch("http://localhost:8000/api/karaoke/lyrics");
                
                if (!response.body) return;

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
                            
                            // Update the React state! This changes the text on screen.
                            if (isMounted) {
                                setCurrentLyric(jsonData.current_phrase);
                            }
                        }
                    }
                }
            } catch (error) {
                console.error("Stream failed:", error);
                if (isMounted) setCurrentLyric("Oops! The microphone disconnected.");
            }
        };

        startKaraokeStream();

        // Cleanup function if the user navigates away early
        return () => {
            isMounted = false; 
        };
    }, []); // Empty dependency array means this only runs once when the page loads

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
                        onClick={() => window.location.href = "/"}
                    >
                        ← Pick a different song
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