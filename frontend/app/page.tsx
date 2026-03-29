"use client";

import { useState } from "react";
import { useRouter } from "next/navigation"; 
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel, FieldGroup } from "@/components/ui/field";
import { Button } from "@/components/ui/button";

const Page = () => {
    const [song, setSong] = useState("");
    const [isLoading, setIsLoading] = useState(false);

    const router = useRouter(); 

    async function onSubmit(e: any) {
        e.preventDefault(); 
        if (!song) { alert("Please enter a song name."); return; }

        setIsLoading(true);

        try {
            const response = await fetch("http://localhost:8000/api/karaoke/process", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ song: song }), 
            });

            if (response.ok) {
                const data = await response.json();
                console.log("Success! Backend says:", data);
                
                router.push(`/sing?song=${encodeURIComponent(song)}`);
            } else {
                console.error("Backend returned an error.");
                alert("Uh oh, something went wrong.");
            }
        } catch (error) {
            console.error("Network error:", error);
            alert("Could not connect to the backend. Is FastAPI running?");
        } finally {
            setIsLoading(false);
        }
    }
    
    return (
        <main className="flex min-h-screen flex-col items-center justify-center p-8">
            <Card className="w-full max-w-5xl p-20 border-4 border-yellow-400">
                <CardHeader className="mb-8">
                    <CardTitle className="text-5xl text-center">Duck Karaoke</CardTitle>
                    <CardDescription className="text-3xl text-center">
                        Enter a YouTube URL to start singing!
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={onSubmit}>
                        <FieldGroup className="gap-y-4">
                            <Field>
                                <FieldLabel className="text-xl">Song and Artist Name</FieldLabel>
                                <div className="flex w-full items-center gap-2">
                                    <Input 
                                      className="flex-1 h-14 !text-xl px-4" 
                                      value={song}
                                      onChange={(e) => setSong(e.target.value)}
                                      placeholder="Ex: The Duck Song"
                                    />
                                    <Button 
                                        disabled={isLoading} 
                                        className="bg-yellow-400 text-black hover:bg-yellow-500 h-14 text-xl px-8"
                                    >
                                        {isLoading ? "Loading..." : "Play"}
                                    </Button>
                                </div>
                            </Field>
                        </FieldGroup>
                    </form>
                </CardContent>
            </Card>
        </main>
    );
}
 
export default Page;