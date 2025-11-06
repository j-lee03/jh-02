import pandas as pd
import sqlite3
import psycopg
import os
from io import StringIO
import warnings

# 경고 메시지 무시
warnings.filterwarnings("ignore")

# --- 설정 ---
LOCAL_DB_FILE = 'events.db'
TABLE_NAME = 'performances'

# (터미널에서 설정될 변수) Render DB (데이터를 쓸 곳)
NEW_DB_URL = os.environ.get('RENDER_DB_URL')

def migrate_data():
    if not NEW_DB_URL:
        print("❌ 오류: Render DB 주소 ('RENDER_DB_URL') 환경 변수가 설정되지 않았습니다.")
        print("   'export RENDER_DB_URL=...'을 먼저 실행해야 합니다.")
        return

    if not os.path.exists(LOCAL_DB_FILE):
        print(f"❌ 오류: 로컬 데이터베이스 파일 '{LOCAL_DB_FILE}'을 찾을 수 없습니다.")
        print("   'python3 app.py'를 로컬에서 실행하여 파일이 생성되었는지 확인하세요.")
        return

    sqlite_conn = None
    new_conn = None

    try:
        # 1. 로컬 SQLite DB ('events.db')에 연결하여 데이터 읽기
        print(f"로컬 DB ('{LOCAL_DB_FILE}')에 연결하여 데이터를 읽습니다...")
        sqlite_conn = sqlite3.connect(LOCAL_DB_FILE)

        # SQL을 사용하여 모든 데이터 조회
        query = f'SELECT "ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status" FROM {TABLE_NAME}'

        # Pandas를 사용하여 데이터프레임으로 로드
        df = pd.read_sql_query(query, sqlite_conn)

        # NULL 값 처리 및 DataFrame 준비
        df = df.where(pd.notnull(df), None)
        print(f"✅ 로컬 DB에서 총 {len(df)}개의 데이터를 성공적으로 읽었습니다.")
        sqlite_conn.close()

        # 2. Render (NEW_DB)에 연결하여 데이터 쓰기
        print("\nRender (NEW_DB)에 연결하여 데이터를 복사합니다...")
        # (Render DB는 외부에서 접근하므로 sslmode=require가 필요합니다)
        new_conn = psycopg.connect(NEW_DB_URL)
        new_cursor = new_conn.cursor()

        # 3. 기존 테이블 삭제 및 새 테이블 스키마 생성
        print("기존 테이블을 삭제하고 새 테이블 스키마를 생성합니다...")
        create_table_query = f"""
        DROP TABLE IF EXISTS {TABLE_NAME};
        CREATE TABLE {TABLE_NAME} (
            "ID" TEXT, 
            "Location" TEXT, 
            "Category" TEXT, 
            "Title" TEXT, 
            "Date" TEXT, 
            "Venue" TEXT, 
            "TeamSetup" TEXT, 
            "Notes" TEXT, 
            "Status" TEXT
        );
        """
        new_cursor.execute(create_table_query)

        # 4. DataFrame 데이터를 SQL 대량 삽입
        data_tuples = [tuple(x) for x in df.to_numpy()]
        insert_query = f"""
            INSERT INTO {TABLE_NAME} ("ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status") 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        new_cursor.executemany(insert_query, data_tuples)

        new_conn.commit()
        new_cursor.close()

        print("-------------------------------------------")
        print(f"✅ Render DB로 데이터 이동 성공! Vercel 앱을 확인하세요.")

    except Exception as e:
        print(f"\n❌ 데이터베이스 작업 중 치명적인 오류 발생: {e}")
        if 'connection failed' in str(e):
            print("TIP: Render DB 주소나 비밀번호가 틀렸을 수 있습니다. Vercel 환경 변수를 확인하세요.")
        if new_conn:
            new_conn.rollback()

    finally:
        if sqlite_conn: sqlite_conn.close()
        if new_conn: new_conn.close()

# --- 스크립트 실행 ---
if __name__ == '__main__':
    migrate_data()