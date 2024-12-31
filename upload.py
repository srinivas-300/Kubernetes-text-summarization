# upload.py
import os
import re
import time
import google.generativeai as genai
from flask import request, jsonify, render_template , session
from datetime import datetime
from flask_caching import Cache
from pymongo import MongoClient
from google.cloud import storage

# Set up Google Gemini API
os.environ["GOOGLE_API_TOKEN"] = "your_api-token"
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/var/secrets/google/key.json'
genai.configure(api_key=os.environ["GOOGLE_API_TOKEN"])
storage_client = storage.Client()

def upload_to_gemini(path, mime_type=None):
    """Uploads the file to Gemini"""
    try:
        file = genai.upload_file(path, mime_type=mime_type)
        print(f"Uploaded file '{file.display_name}' as: {file.uri}")
        return file
    except Exception as e:
        print(f"Error uploading file: {e}")
        return None

def wait_for_files_active(files):
    """Waits for files to be processed and active"""
    print("Waiting for file processing...")
    for name in (file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(10)
            file = genai.get_file(name)
        if file.state.name != "ACTIVE":
            raise Exception(f"File {file.name} failed to process")
    print("...all files ready")

def upload_to_cloud_storage(bucket_name, file_path):
    """Uploads file to Google Cloud Storage."""
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(os.path.basename(file_path))
    blob.upload_from_filename(file_path)
    return blob.public_url

def upload_file(client, cache, username):
    """Handle file upload."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    filename = file.filename
    file.save(filename)
    
    # Check if summary already exists in cache
    cached_summary = cache.get(filename)
    if cached_summary:
        print("Cache hit: Returning cached summary")
        return render_template('summary.html', summary_data=cached_summary)

    # If not found in cache, check MongoDB
    collection = client['llmdb']['llmcluster']  # Access collection from passed client
    mongo_summary = collection.find_one({"document_name": filename})
    if mongo_summary:
        print("MongoDB hit: Returning summary from MongoDB")
        summary = mongo_summary['summary']

        # Cache the summary for future requests
        cache.set(filename, summary, timeout=300)  # Cache timeout is 5 minutes
        return render_template('summary.html', summary_data=summary)

    # Set up generation configuration for Gemini
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }

    # Initialize the Gemini model
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=generation_config,
    )

    # Upload the file to Gemini for processing
    files = [upload_to_gemini(filename, mime_type="application/pdf")]
    if not files[0]:
        return jsonify({'error': 'File upload failed'}), 500

    wait_for_files_active(files)

    # Start the chat session and generate a summary
    chat_session = model.start_chat(
        history=[{
            "role": "user",
            "parts": [files[0]],
        }]
    )
    questions = [
        "What is the document about?",
        "What are the key points?",
        "What is the conclusion?",
        "what are the results?"
    ]
    answers = {}

    # Send each question and store the response
    for question in questions:
        response = chat_session.send_message(question)
        response_text = response.text
        cleaned_text = re.sub(r'\*{1,2}', '', response_text)  # Remove stars (1 or 2 asterisks)
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)  # Replace multiple spaces with a single space
        answers[question] = cleaned_text.strip()

    summary = answers

    # Push the summary to MongoDB
    summary_document = {
        "user": username,
        "document_name": filename,
        "summary": summary,
        "timestamp": datetime.utcnow(),  # Add a timestamp for when the summary was generated
        "file_uri": upload_to_cloud_storage('researchdocs', filename)  #changing to docss Storing file URI as well (optional)
    }

    try:
        collection.insert_one(summary_document)
        print(f"Summary inserted into MongoDB.")
    except Exception as e:
        print(f"Error inserting summary into MongoDB: {e}")
        return jsonify({'error': f'Database insertion failed: {str(e)}'}), 500

    # Cache the summary for future requests
    cache.set(filename, summary)
    print("Cache set: Summary stored in cache")

    return render_template('summary.html', summary_data=summary)
