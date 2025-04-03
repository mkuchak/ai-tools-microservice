import os
import sys
import time
import tempfile
import shutil
import schedule
import threading
import re
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import fal_client
from pydub import AudioSegment
from encryption import decrypt
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.proxies import GenericProxyConfig

# Load environment variables from .env file
load_dotenv()

# Constants
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB in bytes
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
SECRET_KEY = os.environ.get("SECRET_KEY")
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv'}
SUPPORTED_LANGUAGES = {
    'af', 'am', 'ar', 'as', 'az', 'ba', 'be', 'bg', 'bn', 'bo', 'br', 'bs', 'ca', 'cs', 'cy', 
    'da', 'de', 'el', 'en', 'es', 'et', 'eu', 'fa', 'fi', 'fo', 'fr', 'gl', 'gu', 'ha', 'haw', 
    'he', 'hi', 'hr', 'ht', 'hu', 'hy', 'id', 'is', 'it', 'ja', 'jw', 'ka', 'kk', 'km', 'kn', 
    'ko', 'la', 'lb', 'ln', 'lo', 'lt', 'lv', 'mg', 'mi', 'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 
    'my', 'ne', 'nl', 'nn', 'no', 'oc', 'pa', 'pl', 'ps', 'pt', 'ro', 'ru', 'sa', 'sd', 'si', 
    'sk', 'sl', 'sn', 'so', 'sq', 'sr', 'su', 'sv', 'sw', 'ta', 'te', 'tg', 'th', 'tk', 'tl', 
    'tr', 'tt', 'uk', 'ur', 'uz', 'vi', 'yi', 'yo', 'yue', 'zh'
}

# Create temp directory if it doesn't exist
os.makedirs(TEMP_DIR, exist_ok=True)

app = Flask(__name__)

# Force stdout to be line-buffered for Docker logs
sys.stdout.reconfigure(line_buffering=True)

def clean_temp_directory():
    """Clean up the temporary directory by removing all files."""
    for filename in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Error cleaning temp directory: {e}")
    print(f"Temp directory cleaned at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sys.stdout.flush()

def allowed_file(filename):
    """Check if the file extension is allowed."""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in ALLOWED_AUDIO_EXTENSIONS or ext in ALLOWED_VIDEO_EXTENSIONS

def convert_to_mp3(input_file, output_file):
    """Convert audio or video file to mp3 format."""
    try:
        # For audio files, use pydub
        input_ext = input_file.rsplit('.', 1)[1].lower() if '.' in input_file else ''
        
        if input_ext in ALLOWED_AUDIO_EXTENSIONS:
            audio = AudioSegment.from_file(input_file)
            audio.export(output_file, format="mp3")
        else:
            # For video files, use ffmpeg
            os.system(f'ffmpeg -i "{input_file}" -q:a 0 -map a "{output_file}" -y')
        
        return True
    except Exception as e:
        print(f"Conversion error: {e}")
        sys.stdout.flush()
        return False

def parse_proxy_string(proxy_string):
    """Parse proxy string in format 'username:password@hostname:port'"""
    if not proxy_string:
        return None
        
    # Basic validation of proxy string format
    pattern = r'^([^:]+):([^@]+)@([^:]+):(\d+)$'
    match = re.match(pattern, proxy_string)
    if not match:
        return None
        
    username, password, host, port = match.groups()
    return {
        'username': username,
        'password': password,
        'host': host,
        'port': port
    }

def convert_transcript_to_json(transcript):
    """Convert a FetchedTranscript object to JSON-serializable format"""
    # Convert each snippet to a dictionary
    snippets = []
    for snippet in transcript.snippets:
        snippets.append({
            'text': snippet.text,
            'start': snippet.start,
            'duration': snippet.duration
        })
    return snippets

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok"})

@app.route('/transcribe/file', methods=['POST'])
def transcribe_file():
    """
    Endpoint to transcribe audio/video files.
    
    Expects:
    - file: The audio/video file
    - fal_key: Encrypted FAL API key
    
    Optional:
    - language: The language of the audio (default: 'en')
    
    Returns:
    - JSON with transcription text and chunks
    """
    # Check if file is in the request
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    
    # Check if filename is empty
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Check if the file is allowed
    if not allowed_file(file.filename):
        return jsonify({"error": "File format not accepted"}), 400
    
    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"File too large, maximum size is {MAX_FILE_SIZE / (1024 * 1024 * 1024):.1f} GB"}), 400
    
    # Get language parameter (default to English if not provided)
    language = request.form.get('language', 'en').lower()
    
    # Validate language - if not supported, use English as default
    if language not in SUPPORTED_LANGUAGES:
        print(f"Unsupported language '{language}' requested, defaulting to 'en'")
        sys.stdout.flush()
        language = 'en'
    
    # Check if fal_key is in the request
    if 'fal_key' not in request.form:
        return jsonify({"error": "No FAL API key provided"}), 400
    
    encrypted_fal_key = request.form['fal_key']
    
    try:
        # Decrypt the FAL API key
        fal_key = decrypt(encrypted_fal_key, SECRET_KEY)
        if not fal_key:
            return jsonify({"error": "Invalid FAL API key"}), 400
    except Exception as e:
        return jsonify({"error": "Failed to decrypt FAL API key"}), 400
    
    try:
        # Save file to temp directory
        filename = secure_filename(file.filename)
        original_file_path = os.path.join(TEMP_DIR, filename)
        file.save(original_file_path)
        
        # Convert to mp3
        mp3_filename = f"{os.path.splitext(filename)[0]}.mp3"
        mp3_file_path = os.path.join(TEMP_DIR, mp3_filename)
        
        if not convert_to_mp3(original_file_path, mp3_file_path):
            os.remove(original_file_path)
            return jsonify({"error": "Failed to convert file to mp3"}), 500
        
        # Create a client instance with the provided API key
        client = fal_client.client.SyncClient(key=fal_key)
        
        # Upload to fal.ai
        audio_url = client.upload_file(mp3_file_path)
        
        # Call fal.ai API to transcribe the audio
        result = client.subscribe(
            "fal-ai/wizper",
            arguments={
                "audio_url": audio_url,
                "task": "transcribe",
                "language": language,
                "chunk_level": "segment",
                "version": "3"
            }
        )
        
        # Clean up files
        os.remove(original_file_path)
        os.remove(mp3_file_path)
        
        return jsonify({
            "status": "success",
            "transcription": result.get("text", ""),
            "chunks": result.get("chunks", []),
            "language": language,
            "processing_time": f"{time.time() - request.start_time:.2f} seconds"
        })
    
    except Exception as e:
        # Clean up files in case of error
        if 'original_file_path' in locals() and os.path.exists(original_file_path):
            os.remove(original_file_path)
        if 'mp3_file_path' in locals() and os.path.exists(mp3_file_path):
            os.remove(mp3_file_path)
        
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500

@app.route('/transcribe/youtube', methods=['POST'])
def transcribe_youtube():
    """
    Endpoint to get transcripts from YouTube videos.
    
    Expects:
    - videoId: The YouTube video ID
    
    Optional:
    - language: The language of the transcript (default: 'en')
    - proxy: Encrypted proxy string
    - preserveFormatting: Whether to preserve HTML formatting (default: false)
    
    Returns:
    - JSON with transcript text and metadata
    """
    # Get data from JSON body
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
        
    video_id = data.get('videoId')
    language = data.get('language', 'en')  # Default to English if not specified
    encrypted_proxy = data.get('proxy')  # Encrypted proxy string
    preserve_formatting = data.get('preserveFormatting', False)  # Whether to preserve HTML formatting
    
    if not video_id:
        return jsonify({"error": "Missing videoId in request body"}), 400
    
    try:
        # Configure proxy if provided
        proxy_config = None
        if encrypted_proxy:
            if not SECRET_KEY:
                return jsonify({"error": "Secret key not configured"}), 500
                
            # Decrypt the proxy string
            proxy_string = decrypt(encrypted_proxy, SECRET_KEY)
            if not proxy_string:
                return jsonify({"error": "Failed to decrypt proxy string"}), 400
                
            proxy_parts = parse_proxy_string(proxy_string)
            if proxy_parts:
                # Build proxy URL
                http_proxy = f"http://{proxy_parts['username']}:{proxy_parts['password']}@{proxy_parts['host']}:{proxy_parts['port']}"
                
                # Configure using http URL
                proxy_config = GenericProxyConfig(
                    http_url=http_proxy,
                )
            else:
                return jsonify({"error": "Invalid proxy string format. Expected format: username:password@hostname:port"}), 400
        
        # Create YouTubeTranscriptApi instance with proxy config
        ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)
        
        try:
            # Get all available transcripts
            transcript_list = ytt_api.list(video_id)
            
            # First priority: Try to get manual transcript in requested language
            try:
                # Check if manual transcript exists in the requested language
                manual_transcript = transcript_list.find_manually_created_transcript([language])
                if manual_transcript:
                    transcript_data = manual_transcript.fetch(preserve_formatting=preserve_formatting)
                    return jsonify({
                        "transcript": convert_transcript_to_json(transcript_data), 
                        "language": language,
                        "is_generated": False
                    })
            except Exception:
                pass
                
            # Second priority: Try to get ANY generated transcript in its original language
            try:
                # Get all available language codes
                all_languages = [t.language_code for t in transcript_list]
                
                # Try with the specific find_generated_transcript method
                try:
                    generated_transcript = transcript_list.find_generated_transcript(all_languages)
                    if generated_transcript:
                        original_language = generated_transcript.language_code
                        transcript_data = generated_transcript.fetch(preserve_formatting=preserve_formatting)
                        return jsonify({
                            "transcript": convert_transcript_to_json(transcript_data), 
                            "language": original_language, 
                            "is_generated": True
                        })
                except Exception:
                    pass
                    
                # Alternative approach - try to find ANY generated transcript
                for transcript in transcript_list:
                    if transcript.is_generated:
                        transcript_data = transcript.fetch(preserve_formatting=preserve_formatting)
                        return jsonify({
                            "transcript": convert_transcript_to_json(transcript_data), 
                            "language": transcript.language_code, 
                            "is_generated": True
                        })
            except Exception:
                pass
                
            # Third priority: Try to get ANY manual transcript and translate it to requested language
            try:
                for transcript in transcript_list:
                    if not transcript.is_generated and transcript.is_translatable:
                        translated = transcript.translate(language)
                        transcript_data = translated.fetch(preserve_formatting=preserve_formatting)
                        return jsonify({
                            "transcript": convert_transcript_to_json(transcript_data), 
                            "language": language, 
                            "original_language": transcript.language_code,
                            "translated": True,
                            "is_generated": False
                        })
            except Exception:
                pass
            
            # Fourth priority: Try an auto-generated transcript in ANY language
            try:
                # Try each transcript individually
                for transcript in transcript_list:
                    try:
                        transcript_data = transcript.fetch(preserve_formatting=preserve_formatting)
                        return jsonify({
                            "transcript": convert_transcript_to_json(transcript_data), 
                            "language": transcript.language_code,
                            "is_generated": transcript.is_generated
                        })
                    except Exception:
                        continue
            except Exception:
                pass
            
            # Last resort: Try a direct fetch with language
            try:
                transcript_data = ytt_api.fetch(video_id, languages=[language], preserve_formatting=preserve_formatting)
                return jsonify({
                    "transcript": convert_transcript_to_json(transcript_data), 
                    "language": language
                })
            except Exception:
                pass
            
            # Try direct fetch with ANY language as final attempt
            try:
                # Try each language code we know about
                for lang_code in all_languages:
                    try:
                        transcript_data = ytt_api.fetch(video_id, languages=[lang_code], preserve_formatting=preserve_formatting)
                        return jsonify({
                            "transcript": convert_transcript_to_json(transcript_data), 
                            "language": lang_code,
                            "last_resort": True
                        })
                    except Exception:
                        continue
            except Exception:
                pass
                
            # If we got this far, we've tried everything and failed
            return jsonify({"error": "No transcript found for this video after multiple attempts"}), 404
                
        except Exception as e:
            # Try a direct fetch as fallback when list fails
            try:
                transcript_data = ytt_api.fetch(video_id, languages=[language], preserve_formatting=preserve_formatting)
                return jsonify({
                    "transcript": convert_transcript_to_json(transcript_data), 
                    "language": language,
                    "fallback": True
                })
            except Exception:
                pass
                
            return jsonify({"error": f"Failed to connect to YouTube: {str(e)}. Please check your proxy configuration."}), 500
            
    except VideoUnavailable:
        return jsonify({"error": "Video is unavailable"}), 404
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.before_request
def before_request():
    """Store the start time for calculating processing time."""
    request.start_time = time.time()

def run_scheduler():
    """Run the scheduler in a separate thread."""
    schedule.every().day.at("00:00").do(clean_temp_directory)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}")
    sys.stdout.flush()
    app.run(host='0.0.0.0', port=port)
