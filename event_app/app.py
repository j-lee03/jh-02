import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
import os
import psycopg
import pandas as pd
import warnings

# --- [수정됨] Flask 앱 설정 ---
# Vercel이 'templates' 폴더를 찾을 수 있도록 절대 경로를 지정합니다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=TEMPLATE_DIR)
# ------------------------------

DATABASE = 'events.db'
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- [추가됨] DB 업데이트(마이그레이션) 함수 ---
# (이하 app.py의 나머지 코드는 이전과 동일합니다)
def migrate_data():
    warnings.filterwarnings("ignore")
    EXCEL_FILE = 'performances.xlsx'
    TABLE_NAME = 'performances'
    SHEET_NAME = '전체일정'

    if not DATABASE_URL:
        return "❌ 오류: DATABASE_URL 환경 변수가 없습니다."

    if not os.path.exists(EXCEL_FILE):
        return f"❌ 오류: 엑셀 파일 '{EXCEL_FILE}'을 찾을 수 없습니다."

    conn = None
    try:
        print(f"'{EXCEL_FILE}' 파일의 '{SHEET_NAME}' 시트 읽기 시작...")
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, engine='openpyxl')
        df = df.where(pd.notnull(df), None)
        df = df.dropna(how='all')
        df = df.drop_duplicates(subset=['ID'], keep='first')
        print(f"✅ 엑셀에서 총 {len(df)}개의 데이터를 읽었습니다.")

        print("\nRender (NEW_DB)에 연결 및 데이터 복사 시작...")
        conn = psycopg.connect(DATABASE_URL)
        cursor = conn.cursor()

        print("기존 테이블 삭제 후, 새 테이블(승인 기능 포함)을 생성합니다...")
        create_table_query = f"""
        DROP TABLE IF EXISTS {TABLE_NAME};
        CREATE TABLE {TABLE_NAME} (
            "ID" TEXT PRIMARY KEY, "Location" TEXT, "Category" TEXT, "Title" TEXT, "Date" TEXT,
            "Venue" TEXT, "TeamSetup" TEXT, "Notes" TEXT, "Status" TEXT,
            "ApprovalStatus" TEXT DEFAULT '미승인', "RejectionReason" TEXT
        );
        """
        cursor.execute(create_table_query)

        data_tuples = [tuple(x) for x in df.to_numpy()]
        insert_query = f"""
            INSERT INTO {TABLE_NAME} ("ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(insert_query, data_tuples)

        conn.commit()
        cursor.close()
        return "✅ Render DB 업데이트 완료! (승인 기능 추가됨)"

    except Exception as e:
        if conn: conn.rollback()
        return f"❌ DB 작업 중 오류 발생: {e}"
    finally:
        if conn: conn.close()

@app.route('/migrate-db-now')
def run_migration():
    result = migrate_data()
    return f"<pre>{result}</pre>"

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

    try:
        if DATABASE_URL:
            cursor.execute('SELECT MAX(CAST("ID" AS INTEGER)) AS max_id FROM "performances" WHERE "ID" ~ \'^[0-9]+$\'')
        else:
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