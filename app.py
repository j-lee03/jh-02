import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
import os
import psycopg

app = Flask(__name__, template_folder='templates')
DATABASE = 'events.db'
DATABASE_URL = os.environ.get('DATABASE_URL')

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

    # --- [추가됨] 다음 ID 계산 ---
    try:
        # ID 열(TEXT)을 정수(INTEGER)로 변환하여 최대값+1을 찾습니다.
        if DATABASE_URL: # PostgreSQL
            cursor.execute('SELECT MAX(CAST("ID" AS INTEGER)) AS max_id FROM "performances"')
        else: # SQLite
            cursor.execute('SELECT MAX(CAST(ID AS INTEGER)) AS max_id FROM performances')

        max_id_result = cursor.fetchone()

        # max_id_result['max_id']가 None (DB가 비었을 경우) 이면 0으로 처리
        next_id = (max_id_result['max_id'] or 0) + 1

    except Exception as e:
        print(f"다음 ID 계산 중 오류: {e}")
        next_id = 1 # 오류 발생 시 1번으로 지정
    # ---------------------------------

    return render_template('index.html',
                           performances=performances,
                           today_str=today_str,
                           page_title=page_title,
                           search_date_value=display_date,
                           next_id=next_id) # <-- next_id 값을 HTML로 전달

@app.route('/add', methods=['POST'])
def add_event():
    # (폼에서 ID를 받아오는 로직은 이전과 동일)
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
    # (업데이트/승인/반려 로직은 이전과 동일)
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
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)