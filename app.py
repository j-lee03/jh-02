import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
import os
import psycopg

app = Flask(__name__)
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

    # [수정] SELECT 문에 ApprovalStatus, RejectionReason 추가
    base_query = f"""
        SELECT ID, Location, Category, Title, Date, Venue, TeamSetup, Notes, Status, ApprovalStatus, RejectionReason
        FROM performances
        WHERE (Status != 'Cancelled' OR Status IS NULL OR Status = '')
    """

    if search_date:
        page_title = f"'{search_date}' 검색 결과"
        display_date = search_date
        query = base_query + f" AND Date LIKE {placeholder} ORDER BY ID"
        query_params = (f"%{search_date}%",)
    elif mode == 'all':
        page_title = "전체 공연 목록 (날짜순)"
        display_date = ""
        query = base_query + " ORDER BY Date ASC"
    else:
        page_title = f"오늘의 공연 ({today_str})"
        display_date = today_str
        query = base_query + f" AND Date LIKE {placeholder} ORDER BY ID"
        query_params = (f"%{today_str}%",)

    if query_params:
        cursor.execute(query, query_params)
    else:
        cursor.execute(query)

    performances = cursor.fetchall()
    return render_template('index.html', performances=performances, today_str=today_str, page_title=page_title, search_date_value=display_date)

# ... (add_event 함수는 기존과 동일하게 유지해도 됨, 새 열은 디폴트값 사용) ...
@app.route('/add', methods=['POST'])
def add_event():
    # (기존 코드 유지 - 생략 없이 전체 코드가 필요하면 말씀해주세요)
    # ...
    return redirect(url_for('index'))

# [수정] 업데이트 라우트 (승인/반려 처리 추가)
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
    # [추가] 승인 처리
    elif action == 'approve':
        query = f"UPDATE performances SET ApprovalStatus = '승인', RejectionReason = NULL WHERE ID = {placeholder}"
        cursor.execute(query, (id_to_update,))
    # [추가] 반려 처리
    elif action == 'reject':
        reason = request.form.get('rejection_reason', '')
        query = f"UPDATE performances SET ApprovalStatus = '반려', RejectionReason = {placeholder} WHERE ID = {placeholder}"
        cursor.execute(query, (reason, id_to_update))

    conn.commit()
    # 원래 보던 페이지로 돌아가기 위해 Referer 사용 (없으면 인덱스로)
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
