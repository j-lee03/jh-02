import pandas as pd
import sqlite3
import psycopg
import os
from io import StringIO
import warnings

warnings.filterwarnings("ignore")

# --- 설정 ---
LOCAL_DB_FILE = 'events.db'
TABLE_NAME = 'performances'
NEW_DB_URL = os.environ.get('RENDER_DB_URL')

def migrate_data():
    if not NEW_DB_URL:
        print("❌ 오류: 'RENDER_DB_URL' 환경 변수가 없습니다.")
        return

    if not os.path.exists(LOCAL_DB_FILE):
        print(f"❌ 오류: 로컬 DB '{LOCAL_DB_FILE}'가 없습니다.")
        return

    sqlite_conn = None
    new_conn = None

    try:
        print(f"로컬 DB ('{LOCAL_DB_FILE}') 읽기 시작...")
        sqlite_conn = sqlite3.connect(LOCAL_DB_FILE)
        query = f'SELECT "ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status" FROM {TABLE_NAME}'
        df = pd.read_sql_query(query, sqlite_conn)
        
        # 데이터 정제
        df = df.where(pd.notnull(df), None)
        df = df.dropna(how='all')
        # [중요] ID 중복 제거 (첫 번째 항목만 유지)
        df = df.drop_duplicates(subset=['ID'], keep='first')
        
        print(f"✅ 로컬 DB에서 총 {len(df)}개의 데이터를 읽었습니다. (중복 제거됨)")
        sqlite_conn.close()

        print("\nRender (NEW_DB)에 연결 및 데이터 복사 시작...")
        new_conn = psycopg.connect(NEW_DB_URL)
        new_cursor = new_conn.cursor()

        print("기존 테이블 삭제 후, '승인' 기능이 추가된 새 테이블을 생성합니다...")
        create_table_query = f"""
        DROP TABLE IF EXISTS {TABLE_NAME};
        CREATE TABLE {TABLE_NAME} (
            "ID" TEXT PRIMARY KEY,
            "Location" TEXT,
            "Category" TEXT,
            "Title" TEXT,
            "Date" TEXT,
            "Venue" TEXT,
            "TeamSetup" TEXT,
            "Notes" TEXT,
            "Status" TEXT,
            "ApprovalStatus" TEXT DEFAULT '미승인',
            "RejectionReason" TEXT
        );
        """
        new_cursor.execute(create_table_query)

        data_tuples = [tuple(x) for x in df.to_numpy()]
        insert_query = f"""
            INSERT INTO {TABLE_NAME} ("ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        new_cursor.executemany(insert_query, data_tuples)

        new_conn.commit()
        new_cursor.close()
        print("-------------------------------------------")
        print(f"✅ Render DB 업데이트 완료! (승인 기능 추가됨)")

    except Exception as e:
        print(f"\n❌ DB 작업 중 오류 발생: {e}")
        if new_conn:
            new_conn.rollback()

    finally:
        if sqlite_conn: sqlite_conn.close()
        if new_conn: new_conn.close()

if __name__ == '__main__':
    migrate_data()