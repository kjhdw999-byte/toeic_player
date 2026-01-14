# -*- coding: utf-8 -*-
# 파일명: flask_app_v0r2_clean.py
# 버전: v0r2 CLEAN (Render 배포용)
# 최종 수정: 2026-01-14

from flask import Flask, render_template, request, jsonify, session, redirect
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'local-development-secret-key-2026')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MARKERS_FOLDER'] = 'static/markers'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MARKERS_FOLDER'], exist_ok=True)

USERS_FILE = 'users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_marker_file(filename, username):
    """마커 파일 경로 생성 - 사용자별로 구분"""
    safe_file = filename.replace('/', '_').replace('\\', '_')
    safe_file = secure_filename(safe_file)
    safe_user = secure_filename(username)
    marker_filename = f'{safe_file}__USER__{safe_user}.json'
    return os.path.join(app.config['MARKERS_FOLDER'], marker_filename)

def get_folder_structure():
    """폴더 구조 분석"""
    upload_folder = app.config['UPLOAD_FOLDER']
    structure = defaultdict(list)

    if not os.path.exists(upload_folder):
        return {}

    for root, dirs, files in os.walk(upload_folder):
        for file in files:
            if file.endswith(('.mp3', '.wav', '.m4a', '.ogg')):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, upload_folder)
                rel_path = rel_path.replace('\\', '/')

                if '/' in rel_path:
                    folder = rel_path.rsplit('/', 1)[0]
                else:
                    folder = '📁 루트'

                structure[folder].append(rel_path)

    for folder in structure:
        structure[folder].sort()

    return dict(structure)

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()

    if not username:
        return jsonify({'error': '이름을 입력하세요'}), 400

    users = load_users()
    if username not in users:
        users.append(username)
        save_users(users)

    session['username'] = username
    print(f"[로그인] {username} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    username = session.get('username', 'Unknown')
    session.pop('username', None)
    print(f"[로그아웃] {username} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return redirect('/')

@app.route('/users')
def get_users():
    return jsonify(load_users())

@app.route('/player')
def player():
    username = session.get('username')
    if not username:
        return redirect('/')

    structure = get_folder_structure()

    print(f"[플레이어] {username} - 폴더 {len(structure)}개")
    return render_template('player.html', username=username, folder_structure=structure)

@app.route('/api/folders')
def api_folders():
    """폴더 구조 API"""
    if 'username' not in session:
        return jsonify({'error': '로그인 필요'}), 401

    structure = get_folder_structure()
    return jsonify(structure)

@app.route('/markers/<path:filename>')
def get_markers(filename):
    """특정 파일의 모든 사용자 마커 가져오기"""
    if 'username' not in session:
        return jsonify({'error': '로그인 필요'}), 401

    users = load_users()
    all_markers = {}

    for user in users:
        marker_file = get_marker_file(filename, user)
        if os.path.exists(marker_file):
            try:
                with open(marker_file, 'r', encoding='utf-8') as f:
                    markers = json.load(f)
                    all_markers[user] = markers
            except:
                all_markers[user] = []
        else:
            all_markers[user] = []

    return jsonify(all_markers)

@app.route('/markers/<path:filename>/<username>', methods=['POST'])
def save_markers(filename, username):
    """특정 사용자의 마커 저장"""
    current_user = session.get('username')

    if not current_user:
        return jsonify({'error': '로그인 필요'}), 401

    if current_user != username:
        return jsonify({'error': '권한 없음'}), 403

    markers = request.json
    marker_file = get_marker_file(filename, username)

    try:
        with open(marker_file, 'w', encoding='utf-8') as f:
            json.dump(markers, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    structure = get_folder_structure()
    total_files = sum(len(files) for files in structure.values())

    return jsonify({
        'status': 'OK',
        'version': 'v0r2-clean-render',
        'features': ['subfolder_support', 'folder_navigation', 'marker_system'],
        'folders': len(structure),
        'total_files': total_files,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    print("="*60)
    print(f"🎧 TOEIC LC Player v0r2 CLEAN")
    print("="*60)
    print(f"서버 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # Render 환경 지원 (PORT 환경 변수)
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'

    app.run(debug=debug, host='0.0.0.0', port=port)
