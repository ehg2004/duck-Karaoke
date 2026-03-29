"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation"; 
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const SingContent = () => {
    const searchParams = useSearchParams();
    
    const songName = searchParams.get("song") || "Unknown Song";

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
                    
                    <div className="text-3xl text-center font-bold italic text-zinc-600">
                        "Lyrics for {songName} coming soon..."
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