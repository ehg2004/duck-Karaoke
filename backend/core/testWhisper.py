# Import the official OpenAI Python SDK (FastFlowLM mirrors the OpenAI API schema)
from openai import OpenAI

# Initialize the client to point at your local FastFlowLM server
# - base_url: FastFlowLM's local OpenAI-compatible REST endpoint
# - api_key: Dummy token; FastFlowLM typically doesn't enforce auth, but the client requires a string
client = OpenAI(
    base_url="http://127.0.0.1:52625/v1",  # FastFlowLM local API endpoint
    api_key="flm",                         # Placeholder key
)

# Open the audio file in binary mode and create a transcription request
# - model: name of the speech-to-text model exposed by FLM (e.g., "whisper-v3")
# - file: file-like object pointing to your audio
with open("resources/splitted/Open Letter To A Landlord [CnFJzpN_odQ]_Vocals.wav", "rb") as f:
    resp = client.audio.transcriptions.create(
        model="whisper-v3",
        file=f,
    )

# Print the transcribed text returned by the server
print(resp.text)
