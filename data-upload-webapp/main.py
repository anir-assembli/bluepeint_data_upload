import os
import re
import logging
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from google.cloud import storage
from google.auth import compute_engine
from google.auth.transport.requests import Request
from flask_wtf import CSRFProtect
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
csrf = CSRFProtect(app)

# Security configurations
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'xlsx', 'csv'}

# Logging configuration
logging.basicConfig(level=logging.INFO)

# Initialize Google Cloud Storage client with credentials from Compute Engine metadata
credentials = compute_engine.Credentials()
storage_client = storage.Client(credentials=credentials)

# Google Cloud Storage configurations
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GCS_PREFIX = 'public_data_upload/'  # Ensure it ends with '/'

if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME must be set as an environment variable.")

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

# Function to sign a blob using the signBlob API
def sign_blob(blob_to_sign):
    # Refresh the credentials to ensure they are valid
    credentials.refresh(Request())

    # Get the service account email from the credentials
    service_account_email = credentials.service_account_email

    # Use the signBlob API to sign the blob
    client = storage_client.iam_client
    response = client.sign_blob(
        request={
            "name": f"projects/-/serviceAccounts/{service_account_email}",
            "payload": blob_to_sign
        }
    )
    return response.signed_blob

# Function to generate signed URLs using the signed blob
def generate_signed_url(object_name, expiration=timedelta(hours=1)):
    try:
        blob = bucket.blob(object_name)
        signed_blob = sign_blob(object_name)

        # Generate the signed URL using the signed blob and required credentials
        signed_url = blob.generate_signed_url(
            expiration=expiration,
            method='PUT',
            credentials=credentials,
            service_account_email=credentials.service_account_email,
            access_token=credentials.token,
            virtual_hosted_style=True,
            version="v4",
            signer=sign_blob  # Use the sign_blob function as the signer
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

            # Generate the signed URL
            signed_url = generate_signed_url(object_name)
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
