import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime, timedelta
import os

# --- 앱 설정 ---
app = Flask(__name__)
DATABASE = 'events.db'

# --- 데이터베이스 연결 관리 (SQLite용) ---
def get_db_conn():
    conn = getattr(g, '_database', None)
    if conn is None:
        conn = g._database = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
    return conn

@app.teardown_appcontext
def close_connection(exception):
    conn = getattr(g, '_database', None)
    if conn is not None:
        conn.close()

# --- 웹페이지 라우팅(Routing) ---
@app.route('/')
def index():
    conn = get_db_conn()
    cursor = conn.cursor()

    # 현재 날짜 기준
    today_str = datetime.now().date().isoformat()

    search_date = request.args.get('search_date')
    mode = request.args.get('mode')

    page_title = ""
    query_params = ()
    display_date = None
    placeholder = "?"

    if search_date:
        # 1. 특정 날짜 검색
        page_title = f"'{search_date}' 검색 결과"
        display_date = search_date
        query = f"""
            SELECT ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status 
            FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL OR Status = '') 
            AND Date LIKE {placeholder}
            ORDER BY ID
        """
        # LIKE 검색: '2025-11-06' 뿐만 아니라 '2025-11-06(수)' 등도 검색됨
        query_params = (f"%{search_date}%",)

    elif mode == 'all':
        # 2. 전체 일정 보기
        page_title = "전체 공연 목록 (날짜순)"
        display_date = ""
        query = """
            SELECT ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status 
            FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL OR Status = '')
            ORDER BY Date ASC
        """

    else:
        # 3. 기본 페이지 (오늘 날짜 검색)
        page_title = f"오늘의 공연 ({today_str})"
        display_date = today_str
        query = f"""
            SELECT ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status 
            FROM performances
            WHERE (Status != 'Cancelled' OR Status IS NULL OR Status = '') 
            AND Date LIKE {placeholder}
            ORDER BY ID
        """
        query_params = (f"%{today_str}%",)

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

# 기능 1: 신규 공연 추가
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

    placeholder = "?"

    query = f"""
        INSERT INTO performances (ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status) 
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
    """

    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, (new_id, location, category, title, date_str, venue, team_setup, notes, event_type))
        conn.commit()
    except sqlite3.IntegrityError:
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

    placeholder = "?"

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


# --- 앱 실행 ---
if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print(f"경고: 'events.db' 파일이 없습니다. 마이그레이션이 필요합니다.")
    else:
        print("로컬 테스트 서버를 실행합니다.")
    app.run(debug=True, host='0.0.0.0', port=5001)