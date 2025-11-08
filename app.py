import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime, timedelta
import os
import psycopg # PostgreSQL
from urllib.parse import urlparse # DB URL 파싱용

# --- 앱 설정 ---
# template_folder는 Vercel 환경에 따라 필요 없을 수도 있지만, 로컬 테스트를 위해 유지합니다.
app = Flask(__name__, template_folder='templates') 

DATABASE = 'events.db' # 로컬 테스트용
DATABASE_URL = os.environ.get('DATABASE_URL') # Vercel용

# --- 데이터베이스 연결 관리 (PostgreSQL용) ---
def get_db_conn():
    conn = getattr(g, '_database', None)
    if conn is None:
        if DATABASE_URL:
            # 1. 클라우드(Vercel) 환경일 때 (PostgreSQL)
            conn = g._database = psycopg.connect(DATABASE_URL)
            conn.row_factory = psycopg.rows.dict_row # 딕셔너리 결과
        else:
            # 2. 로컬(Mac) 환경일 때 (SQLite - 테스트용)
            print("로컬 SQLite DB로 연결합니다. (테스트용)")
            conn = g._database = sqlite3.connect('events.db')
            conn.row_factory = sqlite3.Row
            
    return conn

@app.teardown_appcontext
def close_connection(exception):
    conn = getattr(g, '_database', None)
    if conn is not None:
        conn.close()

# --- 웹페이지 라우팅(Routing) ---

# 메인 페이지: 'Date' 검색을 'LIKE'로 변경 (더 유연하게)
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
    
    placeholder = "%s" if DATABASE_URL else "?"

    # [수정됨] 모든 열 이름에 큰따옴표(") 추가
    base_query = f"""
        SELECT "ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status", "ApprovalStatus", "RejectionReason"
        FROM "performances"
        WHERE ("Status" != 'Cancelled' OR "Status" IS NULL OR "Status" = '')
    """

    if search_date:
        page_title = f"'{search_date}' 검색 결과"
        display_date = search_date
        query = base_query + f' AND "Date" LIKE {placeholder} ORDER BY "ID"'
        query_params = (f"%{search_date}%",)
    
    elif mode == 'all':
        page_title = "전체 공연 목록 (날짜순)"
        display_date = "" 
        query = base_query + ' ORDER BY "Date" ASC'
    
    else:
        page_title = f"오늘의 공연 ({today_str})"
        display_date = today_str 
        query = base_query + f' AND "Date" LIKE {placeholder} ORDER BY "ID"'
        query_params = (f"%{today_str}%",)

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
    
    placeholder = "%s" if DATABASE_URL else "?"
    
    # [수정됨] INSERT 쿼리에도 큰따옴표 추가
    query = f"""
        INSERT INTO "performances" ("ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status") 
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
    """
    
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, (new_id, location, category, title, date_str, venue, team_setup, notes, event_type))
        conn.commit()
    except (sqlite3.IntegrityError, psycopg.errors.UniqueViolation): 
        print(f"오류: ID {new_id}가 이미 존재합니다.")
        pass 
    
    return redirect(url_for('index', search_date=date_str))

# 기능 2 & 3: 업데이트 (취소, 변경, 승인, 반려)
@app.route('/update', methods=['POST'])
def update_event():
    id_to_update = request.form['id_to_update'] 
    action = request.form['action']
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    placeholder = "%s" if DATABASE_URL else "?"
    
    # [수정됨] UPDATE 쿼리에도 큰따옴표 추가
    if action == 'cancel':
        query = f'UPDATE "performances" SET "Status" = \'Cancelled\' WHERE "ID" = {placeholder}'
        cursor.execute(query, (id_to_update,))
        
    elif action == 'change':
        new_date_str = request.form['new_date']
        if new_date_str:
            query = f'UPDATE "performances" SET "Date" = {placeholder} WHERE "ID" = {placeholder}'
            cursor.execute(query, (new_date_str, id_to_update))

    elif action == 'approve':
        query = f'UPDATE "performances" SET "ApprovalStatus" = \'승인\', "RejectionReason" = NULL WHERE "ID" = {placeholder}'
        cursor.execute(query, (id_to_update,))

    elif action == 'reject':
        reason = request.form.get('rejection_reason', '')
        query = f'UPDATE "performances" SET "ApprovalStatus" = \'반려\', "RejectionReason" = {placeholder} WHERE "ID" = {placeholder}'
        cursor.execute(query, (reason, id_to_update))

    conn.commit()
    return redirect(request.referrer or url_for('index'))


# --- 앱 실행 ---
if __name__ == '__main__':
    # 로컬 실행 시 안내 메시지
    if not os.path.exists('events.db') and not DATABASE_URL:
        print("경고: 'events.db' 파일이 없습니다. (DATABASE_URL도 없음)")
        print("먼저 'python migrate_to_db.py' 스크립트를 실행하여 DB를 생성해주세요.")
    else:
        print("로컬 테스트 서버를 'debug' 모드로 실행합니다...")
        app.run(debug=True, host='0.0.0.0', port=5001)
