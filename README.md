# AI Transcription Microservice

A Flask-based microservice that provides transcription services for audio/video files and YouTube videos using both fal.ai's transcription API and YouTube's transcript API.

## Features

- **Audio/Video File Transcription:**
  - Accepts multiple audio and video formats
  - Converts files to MP3 format
  - Uses fal.ai for high-quality speech transcription
  - Supports multiple languages
  
- **YouTube Video Transcription:**
  - Retrieves transcripts directly from YouTube
  - Supports both manual and auto-generated transcripts
  - Handles transcript translation
  - Optional proxy support for accessing region-restricted content
  
- **General Features:**
  - Automatic temporary file cleanup
  - Simple JSON response format
  - API key encryption for security

## API Endpoints

### Health Check
```
GET /health
```
Returns a simple health check response.

### Transcribe Audio/Video Files
```
POST /transcribe/file
```

**Request Parameters:**
- `file`: Audio or video file (multipart/form-data)
- `fal_key`: Encrypted fal.ai API key (form field)
- `language`: (Optional) Language code of the audio (default: 'en'). If an unsupported language is provided, the API will default to English.

**Supported Audio Formats:** mp3, wav, ogg, flac, m4a, aac
**Supported Video Formats:** mp4, avi, mov, mkv, webm, flv, wmv

**Supported Languages:** af, am, ar, as, az, ba, be, bg, bn, bo, br, bs, ca, cs, cy, da, de, el, en, es, et, eu, fa, fi, fo, fr, gl, gu, ha, haw, he, hi, hr, ht, hu, hy, id, is, it, ja, jw, ka, kk, km, kn, ko, la, lb, ln, lo, lt, lv, mg, mi, mk, ml, mn, mr, ms, mt, my, ne, nl, nn, no, oc, pa, pl, ps, pt, ro, ru, sa, sd, si, sk, sl, sn, so, sq, sr, su, sv, sw, ta, te, tg, th, tk, tl, tr, tt, uk, ur, uz, vi, yi, yo, yue, zh

**Response Example:**
```json
{
  "status": "success",
  "transcription": "Full transcription text here...",
  "chunks": [
    {
      "text": "First segment text",
      "timestamp": [0, 10.5]
    },
    {
      "text": "Second segment text",
      "timestamp": [10.5, 15.2]
    }
  ],
  "language": "en",
  "processing_time": "5.23 seconds"
}
```

### Transcribe YouTube Videos
```
POST /transcribe/youtube
```

**Request Parameters (JSON body):**
- `videoId`: The YouTube video ID (required)
- `language`: Language code for transcript (default: 'en')
- `proxy`: (Optional) Encrypted proxy string in format 'username:password@hostname:port'
- `preserveFormatting`: (Optional) Whether to preserve HTML formatting (default: false)

**Response Example:**
```json
{
  "transcript": [
    {
      "text": "First segment text",
      "start": 0.5,
      "duration": 10.0
    },
    {
      "text": "Second segment text",
      "start": 10.5,
      "duration": 4.7
    }
  ],
  "language": "en",
  "is_generated": false
}
```

## Setup

1. Copy `.env.example` to `.env` and configure your SECRET_KEY
2. Install required packages:
```
pip install -r requirements.txt
```
3. Build and run with Docker:
```
docker-compose up -d

# To do an entire rebuild
docker-compose up -d --build --force-recreate --no-deps
```

## Encryption

The fal.ai API key and proxy strings should be encrypted before sending to the API. Use the encryption functions provided in the `encryption.py` file with your SECRET_KEY.

## Example Usage

### Transcribing Audio/Video Files:
```bash
# With default English language
curl -X POST -F "file=@/path/to/your/audio.mp3" -F "fal_key=your_encrypted_key" http://localhost:6391/transcribe/file

# With specific language (e.g., Spanish)
curl -X POST -F "file=@/path/to/your/audio.mp3" -F "fal_key=your_encrypted_key" -F "language=es" http://localhost:6391/transcribe/file
```

### Transcribing YouTube Videos:
```bash
# Basic YouTube transcript request
curl -X POST -H "Content-Type: application/json" \
  -d '{"videoId": "dQw4w9WgXcQ", "language": "en"}' \
  http://localhost:6391/transcribe/youtube

# With proxy and preserve formatting
curl -X POST -H "Content-Type: application/json" \
  -d '{"videoId": "dQw4w9WgXcQ", "language": "es", "proxy": "your_encrypted_proxy", "preserveFormatting": true}' \
  http://localhost:6391/transcribe/youtube
``` 