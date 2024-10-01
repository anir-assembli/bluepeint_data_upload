import os
import re
import logging
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from google.cloud import storage
from flask_wtf import CSRFProtect
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from google.oauth2 import service_account  # Ensure proper credentials loading
from google.auth import default
from google.auth.exceptions import DefaultCredentialsError


# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
csrf = CSRFProtect(app)

# Security configurations
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'xlsx', 'csv'}

# Logging configuration
logging.basicConfig(level=logging.INFO)


SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
try:
    credentials, project = default()
except DefaultCredentialsError:
    # Fall back to service account file if default credentials fail
    if SERVICE_ACCOUNT_FILE:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES
        )
    else:
        raise ValueError("No valid credentials found")

# Initialize Google Cloud Storage client
storage_client = storage.Client(credentials=credentials)

# Initialize Google Cloud Storage client
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GCS_PREFIX = 'public_data_upload/'  # Ensure it ends with '/'
SERVICE_ACCOUNT_EMAIL = os.getenv('SERVICE_ACCOUNT_EMAIL')  # Email of the service account being used

if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME must be set as environment variables.")

# storage_client = storage.Client(credentials=credentials)
bucket = storage_client.bucket(GCS_BUCKET_NAME)

# Function to allow only certain file types
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Function to sanitize user input
def sanitize_input(input_string):
    if re.match(r"^[-a-zA-Z0-9_.@\ ]+$", input_string):
        return input_string.strip()
    else:
        raise ValueError("Invalid input")

# Updated function to generate signed URLs using google-cloud-storage's built-in method
def generate_signed_url(bucket_name, object_name, expiration=timedelta(hours=1)):
    try:
        blob = bucket.blob(object_name)
        signed_url = blob.generate_signed_url(
            version='v4',
            expiration=expiration,  # Ensure expiration is timedelta, datetime, or int
            method='PUT',
            content_type='application/octet-stream'
        )
        return signed_url
    except Exception as e:
        logging.error(f"Error generating signed URL: {str(e)}")
        return None

# Default route
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# Endpoint to generate signed URLs
@app.route('/generate_signed_urls', methods=['POST'])
def generate_signed_urls():
    try:
        data = request.get_json()
        name = sanitize_input(data.get('name'))
        email = sanitize_input(data.get('email'))
        files = data.get('files')  # List of file paths

        if not name or not email or not files:
            return jsonify({'error': 'Invalid input'}), 400

        signed_urls = {}

        for file_info in files:
            filename = secure_filename(file_info['name'])
            relative_path = file_info['relativePath']

            if not allowed_file(filename):
                return jsonify({'error': f'File type not allowed: {filename}'}), 400

            # Construct the destination path in GCS
            object_name = f"{GCS_PREFIX}{name}/{relative_path}"

            # Generate the signed URL using the updated function
            signed_url = generate_signed_url(GCS_BUCKET_NAME, object_name)
            if signed_url:
                signed_urls[relative_path] = signed_url
            else:
                return jsonify({'error': 'Error generating signed URL'}), 500

        return jsonify({'signedUrls': signed_urls}), 200

    except ValueError as ve:
        logging.error(f"Value error: {ve}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logging.error(f"Error generating signed URLs: {e}")
        return jsonify({'error': 'Could not generate signed URLs'}), 500

if __name__ == '__main__':
    app.run(debug=False)
