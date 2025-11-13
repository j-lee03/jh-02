import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
import os
import psycopg
import pandas as pd
import warnings

# --- 앱 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=TEMPLATE_DIR)

DATABASE = 'events.db'
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- DB 연결 및 관리 함수 (이전과 동일) ---
def get_db_conn():
    conn = getattr(g, '_database', None)
    if conn is None:
        if DATABASE_URL:
            conn = g._database = psycopg.connect(DATABASE_URL)
            conn.row_factory = psycopg.rows.dict_row
        else:
            conn = g._database = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
    return conn

@app.teardown_appcontext
def close_connection(exception):
    conn = getattr(g, '_database', None)
    if conn is not None:
        conn.close()

# --- [수정됨] DB 스키마 자동 점검 및 업데이트 함수 ---
def check_and_update_schema():
    if not DATABASE_URL:
        return "INFO: No DATABASE_URL found, skipping schema check (Local mode)."

    conn = None
    try:
        conn = psycopg.connect(DATABASE_URL)
        cursor = conn.cursor()

        # [수정됨] 1. 'approvalstatus' (소문자) 열이 DB에 존재하는지 확인
        cursor.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_name='performances' AND column_name='approvalstatus'; 
        """)

        column_exists = cursor.fetchone()

        if not column_exists:
            # 2. 열이 없다면, 테이블 구조를 변경 (ApprovalStatus 열 추가)
            print("WARNING: 'ApprovalStatus' column not found. Running migration...")
            cursor.execute("""
                ALTER TABLE "performances" 
                ADD COLUMN "ApprovalStatus" TEXT DEFAULT '미승인',
                ADD COLUMN "RejectionReason" TEXT;
            """)
            conn.commit()
            return "✅ Schema updated successfully (ApprovalStatus added)."
        else:
            return "INFO: Database schema is up-to-date."

    except Exception as e:
        if conn: conn.rollback()
        # 테이블이 아예 없는 오류는 무시하고, migrate-db-now가 처리하게 둠.
        if "relation \"performances\" does not exist" in str(e):
            return "INFO: Table 'performances' not found. Will be created by migrate script."
        return f"❌ Schema check failed: {e}"
    finally:
        if conn: conn.close()
# --------------------------------------------------

# --- [수정됨] Vercel 앱 시작 시, DB 자동 점검 1회 실행 ---
with app.app_context():
    print("INFO: App startup detected. Checking schema...")
    schema_result = check_and_update_schema()
    print(f"INFO: Schema check result: {schema_result}")
# --------------------------------------------------

# (이하 app.py의 나머지 코드는 이전과 동일)
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

    # (DB 열 이름은 PostgreSQL 대소문자 구분을 위해 큰따옴표 사용)
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
    elif mode == 'trash':
        page_title = "🗑️ 휴지통 (삭제된 공연)"
        query = base_query + " AND \"Status\" = 'Cancelled' ORDER BY \"Date\" DESC"
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

    # --- 다음 ID 계산 (숫자만 필터링) ---
    try:
        if DATABASE_URL: # PostgreSQL
            cursor.execute('SELECT MAX(CAST("ID" AS INTEGER)) AS max_id FROM "performances" WHERE "ID" ~ \'^[0-9]+$\'')
        else: # SQLite
            cursor.execute('SELECT MAX(CAST(ID AS INTEGER)) AS max_id FROM performances WHERE ID GLOB \'[0-9]*\'')

        max_id_result = cursor.fetchone()
        next_id = (max_id_result['max_id'] or 0) + 1
    except Exception as e:
        print(f"다음 ID 계산 중 오류: {e}")
        next_id = 1

    return render_template('index.html',
                           performances=performances,
                           today_str=today_str,
                           page_title=page_title,
                           search_date_value=display_date,
                           next_id=next_id,
                           current_mode=mode)

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

    query = f"""
        INSERT INTO "performances" ("ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status")
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
    """
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, (new_id, location, category, title, date_str, venue, team_setup, notes, event_type))
        conn.commit()
    except Exception as e:
        print(f"오류 발생: {e}")
        pass
    return redirect(url_for('index', search_date=date_str))

@app.route('/update', methods=['POST'])
def update_event():
    id_to_update = request.form['id_to_update']
    action = request.form['action']
    conn = get_db_conn()
    cursor = conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"

    if action == 'cancel_performance':
        query = f'UPDATE "performances" SET "Status" = \'Cancelled\' WHERE "ID" = {placeholder}'
        cursor.execute(query, (id_to_update,))
    elif action == 'reset_approval':
        query = f'UPDATE "performances" SET "ApprovalStatus" = \'미승인\', "RejectionReason" = NULL WHERE "ID" = {placeholder}'
        cursor.execute(query, (id_to_update,))
    elif action == 'restore':
        query = f'UPDATE "performances" SET "Status" = \'Scheduled\' WHERE "ID" = {placeholder}'
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
    if action == 'restore':
        return redirect(url_for('index', mode='trash'))
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
