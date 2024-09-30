import os
import re
import logging
from flask import Flask, render_template, request, redirect, flash, url_for
from werkzeug.utils import secure_filename
from google.cloud import storage
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, TextAreaField, MultipleFileField, SubmitField
from wtforms.validators import DataRequired, Email
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
csrf = CSRFProtect(app)

# Security configurations
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # Replace with a secure key
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256MB file size limit
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'xlsx', 'csv'}

# Logging configuration
logging.basicConfig(level=logging.INFO)

# Initialize Google Cloud Storage client
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GCS_PREFIX = 'public_data_upload/'  # Ensure it ends with '/'


# GOOGLE_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME must be set as environment variables.")

storage_client = storage.Client()

# if GOOGLE_CREDENTIALS:
#     storage_client = storage.Client.from_service_account_json(GOOGLE_CREDENTIALS)

bucket = storage_client.bucket(GCS_BUCKET_NAME)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_input(input_string):
    # Allow only alphanumeric characters, underscores, dashes, and spaces
    print(input_string)
    if re.match(r"^[-a-zA-Z0-9_.@\ ]+$", input_string):
        return input_string.strip()
    else:
        raise ValueError("Invalid input")

def upload_to_gcs(file_storage, destination_blob_name):
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_file(file_storage)
    logging.info(f"Uploaded file to gs://{bucket.name}/{destination_blob_name}")

@app.route('/', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        try:
            # Get form data
            name = sanitize_input(request.form.get('name'))
            email = sanitize_input(request.form.get('email'))
            description = request.form.get('description', '')
            files = request.files.getlist('files')
            folders = request.files.getlist('folders')

            # Validate form data
            if not name or not email:
                flash('Name and Email are required.','warning')
                return redirect(request.url)

            # Process files
            all_files = files + folders
            for file in all_files:
                if file and allowed_file(file.filename):
                    if file.content_length > app.config['MAX_CONTENT_LENGTH']:
                        flash(f"File {file.filename} is too large.",'warning')
                        return redirect(url_for('upload'))
                    filename = secure_filename(file.filename)
                    company_dir = f"{GCS_PREFIX}{name}/"
                    destination_blob_name = f"{company_dir}{filename}"

                    upload_to_gcs(file, destination_blob_name)

                elif file.filename!='':
                    flash(f"File {file.filename} is not allowed.",'warning')
                    return redirect(request.url)

            flash('Files successfully uploaded.','success')
            return redirect(url_for('upload'))

        except Exception as e:
            logging.error(f"Error during file upload: {e}")
            flash('An error occurred during file upload.','error')
            return redirect(request.url)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=False)
