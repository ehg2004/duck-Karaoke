import argparse
import csv
import os
import time
import shutil

from matplotlib.pyplot import title
import numpy as np
import librosa
import soundfile as sf

import re
import subprocess
import os   
env = os.environ.copy()

SPLITTED="splitted/"


def _to_resource_relative(path):
    normalized = os.path.normpath(path)
    marker = f"resources{os.sep}"
    if marker in normalized:
        return normalized.split(marker, 1)[1].replace(os.sep, "/")
    return normalized.replace(os.sep, "/")


def save_synced_lyrics(track_dict, lyrics_match, lyrics_dir="resources/lyrics"):
    synced_lyrics = (lyrics_match or {}).get("syncedLyrics")
    if not synced_lyrics:
        return None

    os.makedirs(lyrics_dir, exist_ok=True)
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", track_dict.get("title", "unknown_track")).strip("_")
    safe_artist = re.sub(r"[^A-Za-z0-9._-]+", "_", track_dict.get("artist", "unknown_artist")).strip("_")
    lyrics_path = os.path.join(lyrics_dir, f"{safe_title}-{safe_artist}.lrc")
    with open(lyrics_path, "w", encoding="utf-8") as f:
        f.write(synced_lyrics)
    return lyrics_path


def upsert_index_row(index_csv_path, row):
    headers = [
        "song_name",
        "artist",
        "duration_seconds",
        "voice_audio_path",
        "instruments_audio_path",
        "original_audio_path",
        "lyrics_timestamp_path",
    ]

    existing_rows = []
    if os.path.exists(index_csv_path) and os.path.getsize(index_csv_path) > 0:
        with open(index_csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for item in reader:
                existing_rows.append(item)

    updated = False
    for item in existing_rows:
        if item.get("original_audio_path") == row["original_audio_path"]:
            item.update(row)
            updated = True
            break

    if not updated:
        existing_rows.append(row)

    with open(index_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(existing_rows)

def downloadResources(yt_url, prefixPath):
    os.makedirs(prefixPath, exist_ok=True)

    cmd = (
        f'bash -c "source ~/.profile && '
        f'yt-dlp_linux -t mp3  "{yt_url}" -P "{prefixPath}""'
    )

    downloaded_file = None
    destination_pattern = re.compile(r"^\[download\] Destination: (.+)$")
    already_downloaded_pattern = re.compile(
        r"^\[download\] (.+) has already been downloaded$"
    )

    # Stream output live and capture filename
    with subprocess.Popen(
        cmd,
        shell=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    ) as p:
        stdout, stderr = p.communicate()
        for line in stdout.splitlines():
            print(line)  # keep normal console output
            stripped = line.strip()

            m = destination_pattern.match(stripped)
            if m:
                downloaded_file = m.group(1)
                continue

            m = already_downloaded_pattern.match(stripped)
            if m:
                downloaded_file = m.group(1)

        rc = p.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, cmd)

    print("Download complete.")
    print(f"Downloaded file: {downloaded_file}")
    if downloaded_file is None:
        raise ValueError("Could not determine downloaded file from yt-dlp output.")
    return downloaded_file.split(".")[0] + ".mp3"  # Ensure the file has .mp3 extension

def preProcessSong(inputSongPath, outputPath, useGPU=False):
    if not os.path.isfile(inputSongPath):
        raise FileNotFoundError(f"Input song not found: {inputSongPath}")
    
    basename = os.path.splitext(os.path.basename(inputSongPath))[0]
    instrument_path = os.path.join(outputPath, f"{basename}_Instruments.wav")
    vocal_path = os.path.join(outputPath, f"{basename}_Vocals.wav")

    if os.path.isfile(instrument_path) and os.path.isfile(vocal_path):
        return vocal_path, instrument_path
    cmd = [
        "bash",
        "-c",
        "source ~/.profile && python3 vocal_remover/inference.py --input \"$1\" --output_dir \"$2\"",
        "_",
        inputSongPath,
        outputPath,
    ]
    if useGPU:
        cmd[2] += " --gpu 0"
    subprocess.run(cmd, check=True, env=env)
    print("Pre-processing complete.")
    return vocal_path, instrument_path

from ytmusicapi import YTMusic

def get_yt_music_results(song_name, artist_name, limit=3):
    ytmusic = YTMusic()

    search_query = f"{song_name} {artist_name}"
    search_results = ytmusic.search(query=search_query, filter="songs", limit=limit)

    tracks = []
    for track in search_results:
        video_id = track.get("videoId")
        if not video_id:
            continue

        artists = track.get("artists") or [{}]
        album = track.get("album") or {}
        tracks.append(
            {
                "title": track.get("title", ""),
                "artist": artists[0].get("name", artist_name),
                "url": f"https://music.youtube.com/watch?v={video_id}",
                "duration_seconds": track.get("duration_seconds", 0),
                "album": album.get("name", ""),
            }
        )

    return tracks

# # Example Usage
# result = get_yt_music_url("Blinding Lights", "The Weeknd")
# print(f"Found: {result['title']} by {result['artist']}")
# print(f"URL: {result['url']}")


import requests

# Constants
USER_AGENT = "duck-Karaoke/1.0 (ehg2004@github.com)"
DEF_DEBUG = True

import requests

def get_lyrics(track_dict):
    track = track_dict.get('title')
    artist = track_dict.get('artist')
    
    # 1. Force duration to be a float to prevent math crash (TypeError)
    try:
        target_duration = float(track_dict.get('duration_seconds', 0))
    except (TypeError, ValueError):
        target_duration = 0.0

    print(f"Searching: {track} by {artist} (Target Duration: {target_duration}s)")
    print("-" * 40)

    url = "https://lrclib.net/api/search"
    params = {
        "track_name": track,
        "artist_name": artist
    }
    
    # LRCLIB requires a User-Agent
    headers = {"User-Agent": "duck-Karaoke/1.0 (ehg2004@github.com)"}

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()

        if not results:
            print("API returned an empty list. No matches found.")
            return

        best_res = None
        fallback_res = None # We will use this if duration matching completely fails

        for result in results[:10]:  # Check only the top 10 results to save time
            res_duration = result.get('duration', 0)
            res_synced = result.get('syncedLyrics')
            res_track = result.get('trackName')
                
            # Save the very first result that has synced lyrics as a fallback
            if res_synced is not None and bool(res_synced) and fallback_res is None:
                fallback_res = result

            print(f"Checking API Result: '{res_track}' | Duration: {res_duration}s | Has Synced: {bool(res_synced)}")

            # 2. Check duration with a generous 10-second tolerance
            if abs(float(res_duration) - float(target_duration)) <= 10:
                if res_synced is not None and bool(res_synced):  # Prefer synced lyrics if available
                    best_res = result
                    print(">>> PERFECT MATCH FOUND! Breaking loop.")
                    break
                # elif not best_res:
                #     best_res = result # Save plain lyrics match if no synced available yet

        # 3. If we looped through everything and found no duration match, use the fallback
        if not best_res and fallback_res:
            print("\n>>> No duration matched perfectly, falling back to the first synced result.")
            best_res = fallback_res

        # 4. Final Output
        if best_res:
            print(f"\nFINAL SELECTION: {best_res.get('trackName')} (ID: {best_res.get('id')})")
            if best_res.get('syncedLyrics') is not None and bool(best_res.get('syncedLyrics')):
                print("--- Synced Lyrics ---")
                print(best_res.get('syncedLyrics')[:200] + "\n... [TRUNCATED FOR DISPLAY]")
            else:
                print("--- Plain Lyrics ---")
                print(best_res.get('plainLyrics')[:200] + "\n... [TRUNCATED FOR DISPLAY]")
        else:
            print("\nNo valid lyrics found at all.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")


def find_best_synced_lyrics(track_dict, duration_tolerance=10,query_limit=10):
    track = track_dict.get('title')
    artist = track_dict.get('artist')

    try:
        target_duration = float(track_dict.get('duration_seconds', 0) or 0)
    except (TypeError, ValueError):
        target_duration = 0.0

    url = "https://lrclib.net/api/search"
    params = {
        "track_name": track,
        "artist_name": artist,
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        results = response.json() or []
    except Exception as e:
        if DEF_DEBUG:
            print(f"Lyrics lookup failed for '{track}' by '{artist}': {e}")
        return None

    fallback_synced = None
    for result in results[:query_limit]:  # Limit to top results for efficiency
        synced = result.get('syncedLyrics')
        if not synced:
            continue

        if fallback_synced is None:
            fallback_synced = result

        res_duration = float(result.get('duration') or 0)
        if target_duration > 0 and abs(res_duration - target_duration) <= duration_tolerance:
            return result

    return fallback_synced

def testYTresults(yt_results):
    selected_track = None
    selected_lyrics = None
    for idx, candidate in enumerate(yt_results, start=1):
        print(f"[{idx}/3] Checking synced lyrics: {candidate['title']} - {candidate['artist']}")
        lyrics_match = find_best_synced_lyrics(candidate)
        if lyrics_match is not None:
            selected_track = candidate
            selected_lyrics = lyrics_match
            print("Synced lyrics found. Selecting this track.")
            break
    if selected_track is None:
        selected_track = yt_results[0]
        print(f"No synced lyrics in top {len(yt_results)} results. Falling back to first result.")

    return selected_lyrics, selected_track


# --- TEST DATA ---
# Using 331 as duration (matches the ID 834701 in your JSON)
# Example usage:
# track_data = {'title': 'Blinding Lights', 'artist': 'The Weeknd', 'album': 'After Hours', 'duration_seconds': 200}
# get_lyrics(track_data)    

# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description='Pre-process a song for karaoke')
#     parser.add_argument('--input', type=str, required=True, help='Path to the input song (mp3 format)')
#     parser.add_argument('--output', type=str, required=True, help='Path to save the processed song (mp3 format)')
#     parser.add_argument('--gpu', action='store_true', help='Use GPU for processing')
    
#     args = parser.parse_args()
    
#     downloaded_file = downloadResources(args.input, "resources/originals")
#     preProcessSong(downloaded_file, args.output, args.gpu)




if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Pre-process a song for karaoke')
    parser.add_argument('--artist_name', type=str, required=False, help='Name of the artist')
    parser.add_argument('--song_name', type=str, required=False, help='Name of the song')
    # parser.add_argument('--output', type=str, required=True, help='Path to save the processed song (mp3 format)',default="resources/")
    parser.add_argument('--gpu', action='store_true', help='Use GPU for processing')

    parser.add_argument('--mock', action='store_true', help='Run in mock mode with hardcoded data (for testing without API calls)')
    # python preProcessSong.py --artist_name 'Living Colour' --song_name 'Open Letter To A Landlord' --gpu
    
    args = parser.parse_args()

    if args.mock:
        args.artist_name = "Living Colour"
        args.song_name = "Open Letter To A Landlord"
        print("Running in MOCK mode with hardcoded artist and song name.")
        args.gpu = True  # Assume we want GPU for mock as well

    yt_results = get_yt_music_results(args.song_name, args.artist_name, limit=3)
    
    if not yt_results:
        raise RuntimeError("No YouTube Music song results found.")

    selected_lyrics, selected_track = testYTresults(yt_results)

    downloaded_file = downloadResources(str(selected_track['url']), "resources/originals")
    vocal_path, instrument_path = preProcessSong(downloaded_file, "resources/splitted", args.gpu)

    lyrics_path = save_synced_lyrics(selected_track, selected_lyrics, "resources/lyrics")

    upsert_index_row(
        "resources/index.csv",
        {
            "song_name": selected_track.get("title", ""),
            "artist": selected_track.get("artist", ""),
            "duration_seconds": selected_track.get("duration_seconds", 0),
            "voice_audio_path": _to_resource_relative(vocal_path),
            "instruments_audio_path": _to_resource_relative(instrument_path),
            "original_audio_path": _to_resource_relative(downloaded_file),
            "lyrics_timestamp_path": _to_resource_relative(lyrics_path) if lyrics_path else "",
        },
    )

    print("Indexed track in resources/index.csv")

    if selected_lyrics and selected_lyrics.get('syncedLyrics'):
        print("--- Synced Lyrics Preview ---")
        print(selected_lyrics.get('syncedLyrics')[:200] + "\n... [TRUNCATED FOR DISPLAY]")

    # Play vocals and display synced lyrics in real time
    lyrics_file = lyrics_path
    if lyrics_file is None:
        print("No synced lyrics file available for timed display.")
    else:

        def parse_lrc(lrc_path):
            entries = []
            with open(lrc_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith("["):
                        continue
                    # format [mm:ss.xx] text
                    parts = line.split("]")
                    for part in parts[:-1]:
                        ts = part.strip("[")
                        try:
                            mm, ss = ts.split(":")
                            sec = int(mm) * 60 + float(ss)
                            text = parts[-1].strip()
                            entries.append((sec, text))
                        except ValueError:
                            continue
            entries.sort(key=lambda x: x[0])
            return entries

        def play_audio_and_show_lyrics(audio_path, lrc_path):
            lines = parse_lrc(lrc_path)
            if not lines:
                print("No timestamped lyrics in the LRC file.")
                return

            # Start player (ffplay) asynchronously; fallback if unavailable.
            player = None
            try:
                player = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", audio_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                print("ffplay not available, audio playback skipped. Live lyric timing will still run.")

            start_time = time.time()
            for ts, text in lines:
                now = time.time() - start_time
                wait = ts - now
                if wait > 0:
                    time.sleep(wait)
                print(f"[{ts:06.2f}] {text}")

            if player:
                player.wait()

        print("Playing vocals with synced lyrics...")
        play_audio_and_show_lyrics(vocal_path, lyrics_file)


    