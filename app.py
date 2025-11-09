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

    # 기본 쿼리 (상태 조건 제외)
    base_query = """
        SELECT "ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status", "ApprovalStatus", "RejectionReason"
        FROM "performances"
    """

    if mode == 'trash':
        # [추가됨] 휴지통 모드: 취소된 공연만 보기
        page_title = "🗑️ 휴지통 (삭제된 공연)"
        query = base_query + " WHERE \"Status\" = 'Cancelled' ORDER BY \"Date\" DESC"
    elif search_date:
        page_title = f"'{search_date}' 검색 결과"
        display_date = search_date
        query = base_query + f" WHERE (\"Status\" != 'Cancelled' OR \"Status\" IS NULL OR \"Status\" = '') AND \"Date\" LIKE {placeholder} ORDER BY \"ID\""
        query_params = (f"%{search_date}%",)
    elif mode == 'all':
        page_title = "전체 공연 목록 (날짜순)"
        query = base_query + " WHERE (\"Status\" != 'Cancelled' OR \"Status\" IS NULL OR \"Status\" = '') ORDER BY \"Date\" ASC"
    else:
        page_title = f"오늘의 공연 ({today_str})"
        display_date = today_str
        query = base_query + f" WHERE (\"Status\" != 'Cancelled' OR \"Status\" IS NULL OR \"Status\" = '') AND \"Date\" LIKE {placeholder} ORDER BY \"ID\""
        query_params = (f"%{today_str}%",)

    if query_params:
        cursor.execute(query, query_params)
    else:
        cursor.execute(query)

    performances = cursor.fetchall()
    return render_template('index.html', performances=performances, today_str=today_str, page_title=page_title, search_date_value=display_date, current_mode=mode)

@app.route('/add', methods=['POST'])
def add_event():
    # (기존 코드와 동일)
    new_id = request.form['id']
    # ... (나머지 폼 데이터 받아오기)
    # ... (INSERT 쿼리 실행)
    return redirect(url_for('index'))

@app.route('/update', methods=['POST'])
def update_event():
    id_to_update = request.form['id_to_update']
    action = request.form['action']
    conn = get_db_conn()
    cursor = conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"

    if action == 'cancel':
        query = f'UPDATE "performances" SET "Status" = \'Cancelled\' WHERE "ID" = {placeholder}'
        cursor.execute(query, (id_to_update,))
    elif action == 'restore':
        # [추가됨] 복구 기능: 상태를 'Scheduled'로 변경
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
    # 휴지통에서 복구했을 때는 휴지통 페이지에 남게 리다이렉트
    if action == 'restore':
         return redirect(url_for('index', mode='trash'))
         
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
