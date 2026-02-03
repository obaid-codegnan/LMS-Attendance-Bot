"""
Web Interface for Teacher and Student Management
"""
import os
import pandas as pd
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from src.repositories.mongo_repository import MongoRepository
from src.services.s3_service import S3Service
from src.config.settings import Config

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY or 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'temp_uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

mongo_repo = MongoRepository()
s3_service = S3Service()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def dashboard():
    """Main dashboard showing counts and recent activity."""
    # Since we're using S3 storage, show static info
    teacher_count = "N/A (S3 Storage)"
    student_count = "N/A (S3 Storage)"
    batch_count = "N/A (S3 Storage)"
    db_connected = False  # We're not using DB
    
    return render_template('dashboard.html', 
                         teacher_count=teacher_count,
                         student_count=student_count,
                         batch_count=batch_count,
                         db_connected=db_connected)

# TEACHER MANAGEMENT
@app.route('/teachers/add', methods=['GET', 'POST'])
def add_teacher():
    """Add single teacher."""
    if request.method == 'POST':
        teacher_data = {
            'name': request.form['name'],
            'phone': request.form['phone'],
            'email': request.form.get('email', ''),
            'batches': [b.strip() for b in request.form['batches'].split(',') if b.strip()],
            'subjects': [s.strip() for s in request.form['subjects'].split(',') if s.strip()],
            'is_active': True
        }
        
        try:
            mongo_repo.create_teacher(teacher_data)
            flash('Teacher added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error adding teacher: {str(e)}', 'error')
    
    return render_template('teachers/add.html')

# STUDENT MANAGEMENT
@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    """Add single student - Store image in students/{batch}/ and data in Excel."""
    if request.method == 'POST':
        from datetime import datetime
        
        student_data = {
            'STUDENT ID': request.form['student_id'],
            'STUDENT NAME': request.form['name'],
            'BATCH': request.form['batch'],
            'BRANCH': request.form['branch'],
            'DESIGNATION': request.form['designation'],
            'GENDER': request.form['gender'],
            'IMAGE_URL': '',
            'S3_KEY': '',
            'UPLOAD_DATE': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Handle face image upload
        if 'face_image' in request.files:
            file = request.files['face_image']
            if file and file.filename:
                try:
                    s3_url = s3_service.upload_student_face(student_data['STUDENT ID'], student_data['BATCH'], file)
                    student_data['IMAGE_URL'] = s3_url
                    student_data['S3_KEY'] = f"students/{student_data['BATCH']}/{student_data['STUDENT ID']}.jpg"
                except Exception as e:
                    flash(f'Error uploading image: {str(e)}', 'error')
                    return render_template('students/add.html')
        
        try:
            # Update master Excel file
            s3_service.update_master_excel([student_data])
            flash('Student added successfully to Excel and S3!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error storing student data: {str(e)}', 'error')
    
    return render_template('students/add.html')

@app.route('/students/bulk_upload', methods=['GET', 'POST'])
def bulk_upload_students():
    """Bulk upload students from CSV/Excel with images."""
    if request.method == 'POST':
        # Check for both data file and images
        if 'data_file' not in request.files:
            flash('No data file selected!', 'error')
            return redirect(request.url)
        
        data_file = request.files['data_file']
        if data_file.filename == '':
            flash('No data file selected!', 'error')
            return redirect(request.url)
        
        # Get image files
        image_files = request.files.getlist('image_files')
        
        if data_file and allowed_file(data_file.filename):
            filename = secure_filename(data_file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            data_file.save(filepath)
            
            try:
                # Process the file with images
                result = process_bulk_student_upload_with_images(filepath, image_files)
                
                if result['success'] > 0:
                    flash(f'Successfully processed {result["success"]} students. {result["errors"]} errors.', 'success')
                else:
                    flash(f'No students processed successfully. {result["errors"]} errors found.', 'error')
                
                # Show first few errors if any
                if result['error_details']:
                    for error in result['error_details'][:5]:  # Show first 5 errors
                        flash(f'Error: {error}', 'warning')
                
                # Clean up temp file
                os.remove(filepath)
                
                return redirect(url_for('dashboard'))
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Invalid file type. Please upload CSV or Excel files only.', 'error')
    
    return render_template('students/bulk_upload.html')

def process_bulk_student_upload_with_images(filepath, image_files):
    """Process bulk student upload - Store images in students/{batch}/ and data in Excel."""
    # Read file
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    
    # Debug: Log actual columns
    logger.info(f"CSV columns found: {list(df.columns)}")
    
    # Validate CSV structure - check for common variations
    required_columns = ['student_id', 'name', 'batch']
    actual_columns = [col.lower().strip() for col in df.columns]
    
    # Map common column variations
    column_mapping = {}
    for req_col in required_columns:
        found = False
        for actual_col in df.columns:
            clean_col = actual_col.lower().strip()
            if (req_col == 'student_id' and clean_col in ['student_id', 'studentid', 'id', 'student id']) or \
               (req_col == 'name' and clean_col in ['name', 'student_name', 'full_name', 'fullname', 'student name']) or \
               (req_col == 'batch' and clean_col in ['batch', 'batch_name', 'batchname', 'class']):
                column_mapping[req_col] = actual_col
                found = True
                break
        if not found:
            raise Exception(f"Missing required column: {req_col}. Found columns: {list(df.columns)}")
    
    # Create image filename mapping
    image_map = {}
    for img_file in image_files:
        if img_file.filename:
            # Get just the filename without path
            filename = os.path.basename(img_file.filename)
            base_name = os.path.splitext(filename)[0].lower()
            image_map[base_name] = img_file
            image_map[filename.lower()] = img_file
            logger.info(f"Mapped image: {filename} -> {base_name}")
    
    success_count = 0
    error_count = 0
    errors = []
    students_data = []
    
    for idx, row in df.iterrows():
        try:
            student_id = str(row[column_mapping['student_id']]).strip() if pd.notna(row[column_mapping['student_id']]) else ''
            name = str(row[column_mapping['name']]).strip() if pd.notna(row[column_mapping['name']]) else ''
            batch = str(row[column_mapping['batch']]).strip() if pd.notna(row[column_mapping['batch']]) else ''
            branch = str(row.get('BRANCH', '')).strip() if pd.notna(row.get('BRANCH', '')) else ''
            designation = str(row.get('DESIGNATION', '')).strip() if pd.notna(row.get('DESIGNATION', '')) else ''
            gender = str(row.get('GENDER', '')).strip() if pd.notna(row.get('GENDER', '')) else ''
            photo_filename = str(row.get('PHOTO', '')).strip() if pd.notna(row.get('PHOTO', '')) else ''
            
            from datetime import datetime
            
            student_data = {
                'STUDENT ID': student_id,
                'STUDENT NAME': name,
                'BATCH': batch,
                'BRANCH': branch,
                'DESIGNATION': designation,
                'GENDER': gender,
                'IMAGE_URL': '',
                'S3_KEY': '',
                'UPLOAD_DATE': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Validate required fields
            if not all([student_data['STUDENT ID'], student_data['STUDENT NAME'], student_data['BATCH']]):
                error_count += 1
                errors.append(f"Row {idx + 2}: Missing required fields")
                continue
            
            # Look for matching image by photo filename
            matching_image = None
            if photo_filename:
                photo_base = os.path.splitext(photo_filename)[0].lower()
                logger.info(f"Looking for image: {photo_filename} -> {photo_base}")
                if photo_base in image_map:
                    matching_image = image_map[photo_base]
                    logger.info(f"Found image by photo_base: {photo_base}")
                elif photo_filename.lower() in image_map:
                    matching_image = image_map[photo_filename.lower()]
                    logger.info(f"Found image by filename: {photo_filename}")
            
            # If no photo filename, try student_id
            if not matching_image:
                student_id_lower = str(student_data['STUDENT ID']).lower()
                logger.info(f"Trying student_id: {student_id_lower}")
                for pattern in [student_id_lower, f"{student_id_lower}.jpg", f"{student_id_lower}.png"]:
                    if pattern in image_map:
                        matching_image = image_map[pattern]
                        logger.info(f"Found image by pattern: {pattern}")
                        break
            
            # Upload image to S3 in batch folder
            if matching_image:
                try:
                    matching_image.seek(0)
                    s3_url = s3_service.upload_student_face(student_data['STUDENT ID'], student_data['BATCH'], matching_image)
                    student_data['IMAGE_URL'] = s3_url
                    student_data['S3_KEY'] = f"students/{student_data['BATCH']}/{student_data['STUDENT ID']}.jpg"
                    logger.info(f"Uploaded image for {student_data['STUDENT ID']} to {s3_url}")
                except Exception as e:
                    error_count += 1
                    errors.append(f"Row {idx + 2}: Image upload failed - {str(e)}")
                    logger.error(f"Image upload failed for {student_data['STUDENT ID']}: {e}")
                    continue
            else:
                logger.warning(f"No image found for student {student_data['STUDENT ID']} (photo: {photo_filename})")
            
            students_data.append(student_data)
            success_count += 1
            
        except Exception as e:
            error_count += 1
            errors.append(f"Row {idx + 2}: {str(e)}")
    
    # Update master Excel file
    if students_data:
        try:
            s3_service.update_master_excel(students_data)
        except Exception as e:
            errors.append(f"Failed to update master Excel: {str(e)}")
    
    return {'success': success_count, 'errors': error_count, 'error_details': errors[:10]}

@app.route('/api/batches')
def get_batches():
    """API endpoint to get all batches."""
    batches = mongo_repo.get_all_batches()
    return jsonify(batches)

@app.route('/api/subjects')
def get_subjects():
    """API endpoint to get all subjects."""
    subjects = mongo_repo.get_all_subjects()
    return jsonify(subjects)

if __name__ == '__main__':
    app.run(debug=True, port=5001)