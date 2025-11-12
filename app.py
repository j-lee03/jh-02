import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
import os
import psycopg
import pandas as pd # [추가됨]
import warnings # [추가됨]

app = Flask(__name__, template_folder='templates')
DATABASE = 'events.db'
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- [추가됨] DB 업데이트(마이그레이션) 함수 ---
# migrate_to_db.py의 코드를 app.py 안으로 가져옴
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

# --- [추가됨] DB 업데이트를 실행할 비밀 주소 ---
@app.route('/migrate-db-now')
def run_migration():
    result = migrate_data()
    return f"<pre>{result}</pre>" # 결과를 웹페이지에 표시

# --- (이하 기존 코드) ---

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
    return render_template('index.html', performances=performances, today_str=today_str, page_title=page_title, search_date_value=display_date)

@app.route('/add', methods=['POST'])
def add_event():
    # (신규 추가 폼 로직 ...)
    return redirect(url_for('index'))

@app.route('/update', methods=['POST'])
def update_event():
    # (승인/반려/수정 로직 ...)
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)