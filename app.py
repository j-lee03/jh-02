import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime, timedelta
import os

# --- 앱 설정 ---
app = Flask(__name__)
DATABASE = 'events.db'
app.config['DATABASE'] = DATABASE

# --- 데이터베이스 연결 관리 ---
def get_db_conn():
    conn = getattr(g, '_database', None)
    if conn is None:
        conn = g._database = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row # 결과를 딕셔너리처럼 사용
    return conn

@app.teardown_appcontext
def close_connection(exception):
    conn = getattr(g, '_database', None)
    if conn is not None:
        conn.close()

# --- 웹페이지 라우팅(Routing) ---

# 메인 페이지: '오늘 날짜', '전체 일정', '검색한 날짜' 3가지 모드 처리
@app.route('/')
def index():
    conn = get_db_conn()
    cursor = conn.cursor()

    today_str = datetime.now().date().isoformat() # '2025-10-28'

    search_date = request.args.get('search_date')
    mode = request.args.get('mode')

    page_title = ""
    query_params = ()
    display_date = None

    if search_date:
        # 1. "조회한 날짜" (search_date가 있는 경우)
        page_title = f"'{search_date}' 검색 결과"
        display_date = search_date
        query = """
            SELECT ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status 
            FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL) AND Date = ?
            ORDER BY ID
        """
        query_params = (search_date,)

    elif mode == 'all':
        # 2. "무조건적인 전체 일정" (mode=all 인 경우)
        page_title = "전체 공연 목록 (날짜순)"
        display_date = ""
        query = """
            SELECT ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status 
            FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL)
            ORDER BY Date ASC
        """
        # query_params는 비어있음

    else:
        # 3. "오늘 날짜 검색" (기본 페이지)
        page_title = f"오늘의 공연 ({today_str})"
        display_date = today_str
        query = """
            SELECT ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status 
            FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL) AND Date = ?
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

    query = """
        INSERT INTO performances (ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, (new_id, location, category, title, date_str, venue, team_setup, notes, event_type))
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"오류: ID {new_id}가 이미 존재합니다.")
        pass

        # 추가 후, 해당 날짜로 검색되도록 리다이렉트
    return redirect(url_for('index', search_date=date_str))

# 기능 2 & 3: 날짜 변경 또는 취소
@app.route('/update', methods=['POST'])
def update_event():
    id_to_update = request.form['id_to_update']
    action = request.form['action']

    conn = get_db_conn()
    cursor = conn.cursor()

    if action == 'cancel':
        query = "UPDATE performances SET Status = 'Cancelled' WHERE ID = ?"
        cursor.execute(query, (id_to_update,))

    elif action == 'change':
        new_date_str = request.form['new_date']
        if new_date_str:
            query = "UPDATE performances SET Date = ? WHERE ID = ?"
            cursor.execute(query, (new_date_str, id_to_update))

    conn.commit()
    return redirect(url_for('index'))


# --- 앱 실행 ---
if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print(f"'{DATABASE}' 파일이 없습니다.")
        print("먼저 'python migrate_to_db.py' 스크립트를 실행하여 DB를 생성해주세요.")
    else:
        print(f"'{DATABASE}' 파일을 사용하여 앱을 실행합니다.")
        app.run(debug=True, host='0.0.0.0', port=5001)