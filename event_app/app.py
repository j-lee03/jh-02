import sqlite3 # migrate_to_db.py와의 호환성을 위해 남겨두지만, 실제 앱에선 사용 안 함
import psycopg # PostgreSQL을 위한 새 라이브러리
import os
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime, timedelta
from urllib.parse import urlparse # DB URL 파싱용

# --- 앱 설정 ---
app = Flask(__name__)

# [수정됨] Render에서 제공하는 DATABASE_URL 환경 변수를 읽어옵니다.
# Mac(로컬)에서 실행할 때는 'events.db'를 계속 사용합니다. (테스트용)
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- 데이터베이스 연결 관리 (PostgreSQL용으로 수정) ---
def get_db_conn():
    conn = getattr(g, '_database', None)
    if conn is None:
        if DATABASE_URL:
            # 1. 클라우드(Render) 환경일 때 (PostgreSQL)
            conn = g._database = psycopg.connect(DATABASE_URL)
        else:
            # 2. 로컬(Mac) 환경일 때 (SQLite - 기존 방식)
            print("로컬 SQLite DB로 연결합니다. (테스트용)")
            conn = g._database = sqlite3.connect('events.db')

        # [수정됨] PostgreSQL은 결과를 딕셔너리가 아닌 튜플로 반환합니다.
        # 따라서, 쿼리 결과를 딕셔너리처럼 다루기 위해 Row Factory를 설정해야 합니다.
        if DATABASE_URL:
            # PostgreSQL용 Row Factory (psycopg 3.x)
            conn.row_factory = psycopg.rows.dict_row
        else:
            # SQLite용 Row Factory
            conn.row_factory = sqlite3.Row

    return conn

@app.teardown_appcontext
def close_connection(exception):
    conn = getattr(g, '_database', None)
    if conn is not None:
        conn.close()

# --- 웹페이지 라우팅(Routing) ---

# 메인 페이지: '오늘 날짜', '전체 일정', '검색한 날짜' 3가지 모드
@app.route('/')
def index():
    conn = get_db_conn()
    cursor = conn.cursor()

    today_str = datetime.now().date().isoformat()
    search_date = request.args.get('search_date')
    mode = request.args.get('mode')

    page_title = ""
    query_params = ()
    display_date = None

    # [수정됨] SQLite의 '?' 대신 PostgreSQL의 '%s'를 사용합니다.
    placeholder = "%s" if DATABASE_URL else "?"

    if search_date:
        # 1. "조회한 날짜"
        page_title = f"'{search_date}' 검색 결과"
        display_date = search_date
        query = f"""
            SELECT * FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL) AND Date = {placeholder}
            ORDER BY ID
        """
        query_params = (search_date,)

    elif mode == 'all':
        # 2. "무조건적인 전체 일정"
        page_title = "전체 공연 목록 (날짜순)"
        display_date = ""
        query = """
            SELECT * FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL)
            ORDER BY Date ASC
        """
        # query_params는 비어있음

    else:
        # 3. "오늘 날짜 검색" (기본 페이지)
        page_title = f"오늘의 공연 ({today_str})"
        display_date = today_str
        query = f"""
            SELECT * FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL) AND Date = {placeholder}
            ORDER BY ID
        """
        query_params = (today_str,)

        # 4. 쿼리 실행
    if query_params:
        cursor.execute(query, query_params)
    else:
        cursor.execute(query)

    performances = cursor.fetchall()

    return render_template('index.html',
                           performances=performances,
                           today_str=today_str,
                           page_title=page_title,
                           search_date_value=display_date
                           )

# 기능 1: 신규 공연 추가 (9개 열)
@app.route('/add', methods=['POST'])
def add_event():
    new_id = request.form['id']
    location = request.form['location']
    category = request.form['category']
    title = request.form['title']
    date_str = request.form['date']
    venue = request.form['venue']
    team_setup = request.form['team_setup']
    notes = request.form['notes']
    event_type = request.form.get('event_type', 'Scheduled')

    placeholder = "%s" if DATABASE_URL else "?"

    # [수정됨] 9개의 플레이스홀더
    query = f"""
        INSERT INTO performances (ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status) 
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
    """

    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, (new_id, location, category, title, date_str, venue, team_setup, notes, event_type))
        conn.commit()
    except (sqlite3.IntegrityError, psycopg.errors.UniqueViolation): # [수정됨] 2가지 DB 오류 모두 처리
        print(f"오류: ID {new_id}가 이미 존재합니다.")
        pass

    return redirect(url_for('index', search_date=date_str))

# 기능 2 & 3: 날짜 변경 또는 취소
@app.route('/update', methods=['POST'])
def update_event():
    id_to_update = request.form['id_to_update']
    action = request.form['action']

    conn = get_db_conn()
    cursor = conn.cursor()

    placeholder = "%s" if DATABASE_URL else "?"

    if action == 'cancel':
        query = f"UPDATE performances SET Status = 'Cancelled' WHERE ID = {placeholder}"
        cursor.execute(query, (id_to_update,))

    elif action == 'change':
        new_date_str = request.form['new_date']
        if new_date_str:
            query = f"UPDATE performances SET Date = {placeholder} WHERE ID = {placeholder}"
            cursor.execute(query, (new_date_str, id_to_update))

    conn.commit()
    return redirect(url_for('index'))


# --- 앱 실행 (로컬 테스트용) ---
# [수정됨] 'if __name__ == '__main__':' 부분은 'gunicorn'이 사용하지 않으므로,
# 'python3 app.py'로 직접 실행할 때만 (로컬 테스트) 작동합니다.
if __name__ == '__main__':
    if not os.path.exists('events.db') and not DATABASE_URL:
        print("경고: 'events.db' 파일이 없습니다. (DATABASE_URL도 없음)")
        print("먼저 'python migrate_to_db.py' 스크립트를 실행하여 DB를 생성해주세요.")
    else:
        print("로컬 테스트 서버를 'debug' 모드로 실행합니다...")
        app.run(debug=True, host='0.0.0.0', port=5001)