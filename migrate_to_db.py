import pandas as pd
import sqlite3
import psycopg # 새 라이브러리
import os
from urllib.parse import urlparse

# --- 설정 ---
EXCEL_FILE = 'performances.xlsx'
TABLE_NAME = 'performances'
SHEET_NAME = '전체일정'

DATABASE_URL = os.environ.get('DATABASE_URL')

def migrate_data():

    print(f"'{EXCEL_FILE}' 파일의 '{SHEET_NAME}' 시트 읽기를 시작합니다...")
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, engine='openpyxl')
        df = df.where(pd.notnull(df), None)
        df = df.dropna(how='all')
    except Exception as e:
        print(f"엑셀 파일을 읽는 중 오류 발생: {e}")
        print(f"'{EXCEL_FILE}' 파일 안에 '{SHEET_NAME}' 시트(탭)가 있는지 확인하세요.")
        return

    print(f"'{SHEET_NAME}' 시트에서 (빈 행 제외) 총 {len(df)}개의 데이터를 읽었습니다.")

    conn = None
    try:
        if DATABASE_URL:
            print(f"클라우드 PostgreSQL DB에 연결합니다...")
            conn = psycopg.connect(DATABASE_URL)
            print("연결 성공. 기존 테이블을 삭제하고 새로 생성합니다.")

            cursor = conn.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME};")

            # 1. 생성 (대문자)
            create_table_query = """
            CREATE TABLE performances (
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
            cursor.execute(create_table_query)

            data_tuples = [tuple(x) for x in df.to_numpy()]

            # 2. [수정됨] 삽입 (대문자)
            # INSERT 쿼리의 모든 열 이름에 큰따옴표(")를 추가합니다.
            insert_query = f"""
                INSERT INTO {TABLE_NAME} ("ID", "Location", "Category", "Title", "Date", "Venue", "TeamSetup", "Notes", "Status") 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(insert_query, data_tuples)

            conn.commit()
            cursor.close()

        else:
            # 2. 로컬(SQLite)로 데이터 마이그레이션
            print(f"'events.db' (로컬 SQLite)에 연결합니다...")
            conn = sqlite3.connect('events.db')
            df.to_sql(TABLE_NAME, conn, if_exists='replace', index=False)

        print("-------------------------------------------")
        print(f"✅ 데이터 이동 성공!")

    except Exception as e:
        print(f"데이터베이스 작업 중 오류 발생: {e}")
        if conn:
            conn.rollback()

    finally:
        if conn:
            conn.close()
            print("데이터베이스 연결을 닫았습니다.")

if __name__ == '__main__':
    migrate_data()