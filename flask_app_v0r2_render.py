# -*- coding: utf-8 -*-

# 파일명: flask_app_v0r2_render_postgresql.py
# 버전: v0r2 PostgreSQL (Render 배포용)
# 최종 수정: 2026-01-15
# 변경사항: JSON 파일 → PostgreSQL 마커 저장

from flask import Flask, render_template, request, jsonify, session, redirect
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
from collections import defaultdict

# ============= PostgreSQL 추가 =============
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'local-development-secret-key-2026')
app.config['UPLOAD_FOLDER'] = 'static/uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

USERS_FILE = 'users.json'


# ============= PostgreSQL 연결 함수 =============

def get_db_connection():
    """Render PostgreSQL 연결"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception('DATABASE_URL 환경변수가 설정되지 않았습니다!')

    # Render PostgreSQL은 SSL 필수
    if '?' not in database_url:
        database_url += '?sslmode=require'
    elif 'sslmode' not in database_url:
        database_url += '&sslmode=require'

    return psycopg2.connect(database_url)


def init_db():
    """데이터베이스 테이블 초기화"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 마커 테이블 생성
        cur.execute("""
            CREATE TABLE IF NOT EXISTS markers (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                audio_path TEXT NOT NULL,
                time_sec REAL NOT NULL,
                label TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(username, audio_path, time_sec)
            )
        """)

        # 인덱스 생성 (성능 향상)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_markers_lookup 
            ON markers(username, audio_path)
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("✅ PostgreSQL 테이블 초기화 완료!")
        return True
    except Exception as e:
        print(f"⚠️ DB 초기화 실패: {e}")
        return False


def save_markers_to_db(username, audio_path, markers):
    """마커를 PostgreSQL에 저장 (덮어쓰기)"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. 기존 마커 삭제
        cur.execute(
            'DELETE FROM markers WHERE username=%s AND audio_path=%s',
            (username, audio_path)
        )

        # 2. 새 마커 저장
        for marker in markers:
            if isinstance(marker, dict):
                time_sec = marker.get('time', marker.get('t', 0))
                label = marker.get('label', '')
            else:
                time_sec = float(marker)
                label = ''

            cur.execute("""
                INSERT INTO markers (username, audio_path, time_sec, label)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username, audio_path, time_sec) DO NOTHING
            """, (username, audio_path, time_sec, label))

        conn.commit()
        print(f"✅ 마커 저장: {username} - {audio_path} ({len(markers)}개)")

    except Exception as e:
        conn.rollback()
        print(f"❌ 마커 저장 실패: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def load_markers_from_db(username, audio_path):
    """PostgreSQL에서 마커 불러오기"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT time_sec, label FROM markers 
            WHERE username=%s AND audio_path=%s 
            ORDER BY time_sec
        """, (username, audio_path))

        rows = cur.fetchall()
        markers = [{'time': row[0], 'label': row[1]} for row in rows]

        print(f"📖 마커 불러오기: {username} - {audio_path} ({len(markers)}개)")
        return markers

    except Exception as e:
        print(f"❌ 마커 불러오기 실패: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def load_all_users_markers(audio_path):
    """특정 오디오의 모든 사용자 마커 불러오기"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT username, time_sec, label FROM markers 
            WHERE audio_path=%s 
            ORDER BY username, time_sec
        """, (audio_path,))

        rows = cur.fetchall()

        # 사용자별로 그룹화
        all_markers = defaultdict(list)
        for username, time_sec, label in rows:
            all_markers[username].append({'time': time_sec, 'label': label})

        return dict(all_markers)

    except Exception as e:
        print(f"❌ 전체 마커 불러오기 실패: {e}")
        return {}
    finally:
        cur.close()
        conn.close()


# ============= 사용자 관리 (JSON - 간단해서 그대로 유지) =============

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


# ============= 폴더 구조 분석 =============

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


# ============= 라우트 =============

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
    """특정 파일의 모든 사용자 마커 가져오기 (PostgreSQL)"""
    if 'username' not in session:
        return jsonify({'error': '로그인 필요'}), 401

    try:
        all_markers = load_all_users_markers(filename)

        # 등록된 모든 사용자 목록 가져오기
        users = load_users()

        # 마커 없는 사용자도 빈 배열로 표시
        for user in users:
            if user not in all_markers:
                all_markers[user] = []

        return jsonify(all_markers)

    except Exception as e:
        print(f"❌ 마커 조회 실패: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/markers/<path:filename>/<username>', methods=['POST'])
def save_markers(filename, username):
    """특정 사용자의 마커 저장 (PostgreSQL)"""
    current_user = session.get('username')

    if not current_user:
        return jsonify({'error': '로그인 필요'}), 401

    if current_user != username:
        return jsonify({'error': '권한 없음'}), 403

    markers = request.json

    try:
        save_markers_to_db(username, filename, markers)
        return jsonify({'success': True})

    except Exception as e:
        print(f"❌ 마커 저장 실패: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    structure = get_folder_structure()
    total_files = sum(len(files) for files in structure.values())

    # DB 연결 상태 체크
    db_status = 'OK'
    try:
        conn = get_db_connection()
        conn.close()
    except:
        db_status = 'ERROR'

    return jsonify({
        'status': 'OK',
        'version': 'v0r2-postgresql-render',
        'features': ['subfolder_support', 'folder_navigation', 'postgresql_markers'],
        'database': db_status,
        'folders': len(structure),
        'total_files': total_files,
        'timestamp': datetime.now().isoformat()
    })


# ============= 앱 시작 =============

if __name__ == '__main__':
    print("="*60)
    print(f"🎧 TOEIC LC Player v0r2 PostgreSQL")
    print("="*60)
    print(f"서버 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # DB 초기화
    if init_db():
        print("✅ 데이터베이스 준비 완료")
    else:
        print("⚠️ 데이터베이스 연결 실패 - 환경변수 확인 필요")

    print("="*60)

    # Render 환경 지원 (PORT 환경 변수)
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'

    app.run(debug=debug, host='0.0.0.0', port=port)
