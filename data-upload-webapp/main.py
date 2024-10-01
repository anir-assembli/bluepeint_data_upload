import os
import re
import logging
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from google.cloud import storage
from google.oauth2 import service_account
from flask_wtf import CSRFProtect
from dotenv import load_dotenv
from datetime import timedelta
from google.cloud import secretmanager
import json

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'xlsx', 'csv'}
logging.basicConfig(level=logging.INFO)

# Function to access the secret manager
def access_secret_version(secret_id, version_id="latest"):
    project_id = os.getenv('GCP_PROJECT_ID')
    if not project_id:
        raise ValueError("GCP_PROJECT_ID is not set. Ensure it's set as an environment variable.")
        
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Initialize Google Cloud Storage client
def get_credentials():
    try:
        secret_content = access_secret_version("sme-webapp-service-account-key")
        service_account_info = json.loads(secret_content)
        return service_account.Credentials.from_service_account_info(service_account_info)
    except Exception as e:
        app.logger.error(f"Error accessing secret: {str(e)}")
        return None

credentials = get_credentials()
if credentials is None:
    raise ValueError("Failed to retrieve valid credentials.")

storage_client = storage.Client(credentials=credentials)

# Google Cloud Storage configurations
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GCS_PREFIX = 'public_data_upload/'  # Ensure it ends with '/'

if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME must be set as an environment variable.")

bucket = storage_client.bucket(GCS_BUCKET_NAME)

# Function to allow only certain file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Function to sanitize user input
def sanitize_input(input_string):
    if re.match(r"^[-a-zA-Z0-9_.@ ]+$", input_string):
        return input_string.strip()
    else:
        raise ValueError("Invalid input")

# Function to generate signed URLs directly using Google Cloud Storage
def generate_signed_url(object_name, expiration=timedelta(hours=1)):
    try:
        blob = bucket.blob(object_name)
        
        # Generate the signed URL directly without manual blob signing
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="PUT",
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
        if not data:
            raise ValueError("No data provided in the request")

        name = sanitize_input(data.get('name'))
        email = sanitize_input(data.get('email'))
        files = data.get('files')  # List of file paths

        if not name or not email or not files:
            return jsonify({'error': 'Invalid input: name, email, or files are missing'}), 400

        signed_urls = {}

        for file_info in files:
            filename = secure_filename(file_info['name'])
            relative_path = file_info['relativePath']

            if not allowed_file(filename):
                return jsonify({'error': f'File type not allowed: {filename}'}), 400

            # Construct the destination path in GCS
            object_name = f"{GCS_PREFIX}{name}/{relative_path}"

            # Generate the signed URL
            signed_url = generate_signed_url(object_name)
            if signed_url:
                signed_urls[relative_path] = signed_url
            else:
                return jsonify({'error': f'Error generating signed URL for {relative_path}'}), 500

        return jsonify({'signedUrls': signed_urls}), 200

    except ValueError as ve:
        logging.error(f"Value error: {ve}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logging.error(f"Error generating signed URLs: {e}")
        return jsonify({'error': 'Could not generate signed URLs'}), 500

if __name__ == '__main__':
    app.run(debug=False)
