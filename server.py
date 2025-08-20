import os
import sys
import uuid
import json
import datetime
from getpass import getpass
from flask import Flask, request, send_from_directory, render_template, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


CONFIG_FILE = 'config.json'
METADATA_FILE = 'file_metadata.json'
UPLOAD_FOLDER = 'cdn_files'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'webm'}


def load_or_create_config():
    if os.path.exists(CONFIG_FILE):
        print(f"Loading configuration from {CONFIG_FILE}...")
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)

    print("--- CDN First-Time Setup ---")
    config = {}
    password = getpass("Please create a master password: ")
    if not password or password != getpass("Confirm password: "):
        print("Passwords do not match or are empty. Exiting.")
        sys.exit(1)
    config['password_hash'] = generate_password_hash(password)
    config['secret_key'] = os.urandom(24).hex()
    config['admin_path'] = uuid.uuid4().hex
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    print(f"Configuration saved to {CONFIG_FILE}. Please do not share this file.")
    return config

def load_metadata():
    if not os.path.exists(METADATA_FILE):
        return {}
    try:
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_metadata(data):
    with open(METADATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def run_initial_setup():
    
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        print(f"Created upload folder at: ./{UPLOAD_FOLDER}")

    templates_dir = "templates"
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
        print(f"Created templates folder at: ./{templates_dir}")
    
    templates = {
        "password.html": """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Password Required</title><style>body{font-family:sans-serif;background:#f4f4f9;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;} .card{background:white;padding:40px;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.1);text-align:center;} input[type=password],input[type=submit]{width:calc(100% - 22px);padding:10px;margin:10px 0;border:1px solid #ccc;border-radius:5px;} input[type=submit]{background:#007bff;color:white;cursor:pointer;}</style></head><body><div class="card"><h2>Password Required for {{ filename }}</h2><form method="post"><input type="password" name="password" placeholder="Enter password" required autofocus><input type="submit" value="Access File"></form></div></body></html>""",
        "locked.html": """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>File Locked</title><style>body{font-family:sans-serif;background:#f4f4f9;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;} .card{background:white;padding:40px;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.1);text-align:center;color:#721c24;background-color:#f8d7da;border:1px solid #f5c6cb;}</style></head><body><div class="card"><h2>File Locked</h2><p>The file <strong>{{ filename }}</strong> has reached its visit limit and can no longer be accessed.</p></div></body></html>"""
    }
    for name, content in templates.items():
        template_path = os.path.join(templates_dir, name)
        if not os.path.exists(template_path):
            with open(template_path, "w") as f:
                f.write(content)
            print(f"Created template: {name}")


config = load_or_create_config()
ADMIN_ROUTE_PATH = config['admin_path']
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.secret_key = config['secret_key']


def get_file_info():
    files = []
    metadata = load_metadata()
    if not os.path.exists(UPLOAD_FOLDER): return files
    for filename in sorted(os.listdir(UPLOAD_FOLDER), reverse=True):
        path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(path):
            size_in_bytes = os.path.getsize(path)
            size = f"{size_in_bytes / 1024:.1f} KB" if size_in_bytes < 1024*1024 else f"{size_in_bytes / (1024*1024):.1f} MB"
            mtime = os.path.getmtime(path)
            file_meta = metadata.get(filename, {})
            files.append({
                'name': filename, 'size': size, 'modified_raw': mtime,
                'modified': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M'),
                'password': file_meta.get('password'),
                'visit_limit': file_meta.get('visit_limit'),
                'visit_count': file_meta.get('visit_count', 0)
            })
    files.sort(key=lambda x: x['modified_raw'], reverse=True)
    return files

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def root(): abort(404)

@app.route(f'/{ADMIN_ROUTE_PATH}', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        password = request.form.get('password')
        if password and check_password_hash(config['password_hash'], password):
            session['logged_in'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid password, please try again.', 'error')
    
    if not session.get('logged_in'):
        return render_template('index.html', logged_in=False)

    active_tab = request.args.get('active_tab', 'upload')
    file_list = get_file_info()
    return render_template('index.html', logged_in=True, files=file_list, active_tab=active_tab)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/files/<path:name>', methods=['GET', 'POST'])
def serve_file(name):
    if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], name)):
        abort(404)
        
    metadata = load_metadata()
    file_meta = metadata.get(name)

    if not file_meta:
        return send_from_directory(app.config['UPLOAD_FOLDER'], name)

    limit = file_meta.get('visit_limit')
    if limit is not None and file_meta.get('visit_count', 0) >= limit:
        return render_template('locked.html', filename=name), 403

    password = file_meta.get('password')
    if password:
        submitted_password = request.form.get('password') or request.args.get('password')
        if submitted_password == password:
            if limit is not None:
                file_meta['visit_count'] = file_meta.get('visit_count', 0) + 1
                save_metadata(metadata)
            return send_from_directory(app.config['UPLOAD_FOLDER'], name)
        return render_template('password.html', filename=name)

    if limit is not None:
        file_meta['visit_count'] = file_meta.get('visit_count', 0) + 1
        save_metadata(metadata)
        
    return send_from_directory(app.config['UPLOAD_FOLDER'], name)


@app.route('/upload', methods=['POST'])
def upload():
    if not session.get('logged_in'): abort(401)
    active_tab = request.form.get('active_tab', 'upload')

    files = request.files.getlist('file')
    if not files or not files[0].filename:
        flash('No files selected.', 'error')
        return redirect(url_for('index', active_tab=active_tab))

    custom_names = request.form.getlist('custom_name')
    passwords = request.form.getlist('password')
    visit_limits = request.form.getlist('visit_limit')
    
    uploaded_filenames = []
    error_filenames = []
    
    metadata = load_metadata()

    for i, file in enumerate(files):
        if not (file and allowed_file(file.filename)):
            error_filenames.append(secure_filename(file.filename) or f"file_{i}")
            continue

        original_filename = secure_filename(file.filename)
        custom_name = custom_names[i] if i < len(custom_names) else ''
        file_ext = os.path.splitext(original_filename)[1]
        new_filename = f"{secure_filename(custom_name) or uuid.uuid4().hex}{file_ext}"

        file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
        uploaded_filenames.append(new_filename)

        metadata[new_filename] = {'visit_count': 0}
        
        password = passwords[i] if i < len(passwords) else ''
        if password:
            metadata[new_filename]['password'] = password
            
        limit = visit_limits[i] if i < len(visit_limits) else ''
        if limit and limit.isdigit() and int(limit) > 0:
            metadata[new_filename]['visit_limit'] = int(limit)
    
    save_metadata(metadata)
    
    if uploaded_filenames:
        flash(f'{len(uploaded_filenames)} file(s) uploaded successfully.', 'success')
    if error_filenames:
        flash(f'Failed to upload {len(error_filenames)} file(s) due to disallowed file type.', 'error')
        
    return redirect(url_for('index', active_tab=active_tab))

@app.route('/rename/<path:filename>', methods=['POST'])
def rename_file(filename):
    if not session.get('logged_in'): abort(401)
    active_tab = request.form.get('active_tab', 'manage')
    old_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(old_path):
        flash(f'Error: Original file "{filename}" not found.', 'error')
    else:
        new_name_base = secure_filename(request.form.get('new_name'))
        if not new_name_base:
            flash('Error: New name is invalid.', 'error')
        else:
            new_filename = f"{new_name_base}{os.path.splitext(filename)[1]}"
            new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            if os.path.exists(new_path):
                flash(f'Error: A file named "{new_filename}" already exists.', 'error')
            else:
                os.rename(old_path, new_path)
                metadata = load_metadata()
                if filename in metadata:
                    metadata[new_filename] = metadata.pop(filename)
                    save_metadata(metadata)
                flash(f'Renamed "{filename}" to "{new_filename}".', 'success')
    return redirect(url_for('index', active_tab=active_tab))

@app.route('/delete/<path:filename>', methods=['POST'])
def delete_file(filename):
    if not session.get('logged_in'): abort(401)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(path):
        os.remove(path)
        metadata = load_metadata()
        if filename in metadata:
            del metadata[filename]
            save_metadata(metadata)
        flash(f'File "{filename}" has been deleted.', 'success')
    else:
        flash('File not found.', 'error')
    return redirect(url_for('index', active_tab=request.form.get('active_tab', 'manage')))


@app.route('/api/file/<path:filename>/password', methods=['POST'])
def update_password(filename):
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    metadata = load_metadata()
    if filename not in metadata: metadata[filename] = {}
    
    new_password = request.json.get('password')
    if new_password:
        metadata[filename]['password'] = new_password
    elif 'password' in metadata[filename]:
        del metadata[filename]['password']
        
    save_metadata(metadata)
    return jsonify({'success': True, 'message': 'Password updated.'})

@app.route('/api/file/<path:filename>/lock', methods=['POST'])
def update_lock(filename):
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    metadata = load_metadata()
    if filename not in metadata: metadata[filename] = {}

    limit = request.json.get('limit')
    if limit and str(limit).isdigit() and int(limit) > 0:
        metadata[filename]['visit_limit'] = int(limit)
        if 'visit_count' not in metadata[filename]: metadata[filename]['visit_count'] = 0
    else:
        if 'visit_limit' in metadata[filename]: del metadata[filename]['visit_limit']
        if 'visit_count' in metadata[filename]: del metadata[filename]['visit_count']
        
    save_metadata(metadata)
    return jsonify({'success': True, 'message': 'Lock settings updated.'})


   
run_initial_setup()
print("\nStarting server...")
print(f"Your permanent admin panel is available at: http://127.0.0.1:5000/{ADMIN_ROUTE_PATH}")
app.run(host='0.0.0.0', port=5000, debug=False)