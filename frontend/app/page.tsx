"use client";

import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel, FieldGroup } from "@/components/ui/field";
import { Button } from "@/components/ui/button";

const Page = () => {
    function onSubmit(e: any) {
        e.preventDefault(); 
        console.log("Form submitted!");
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
                                    className="flex-1 h-14 text-lg px-4" 
                                    />
                                    <Button className="bg-yellow-400 text-black hover:bg-yellow-500 h-14 text-lg px-8">
                                        Play
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