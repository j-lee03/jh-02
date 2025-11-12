import pandas as pd
import psycopg
import os
import warnings

warnings.filterwarnings("ignore")

# --- 설정 ---
EXCEL_FILE = 'performances.xlsx' # 깃허브에 올라간 엑셀 파일
TABLE_NAME = 'performances'
SHEET_NAME = '전체일정'
NEW_DB_URL = os.environ.get('RENDER_DB_URL') # Render 서버의 환경 변수

def migrate_data():
    if not NEW_DB_URL:
        print("❌ 오류: 'RENDER_DB_URL' 환경 변수가 없습니다.")
        return

    if not os.path.exists(EXCEL_FILE):
        print(f"❌ 오류: 엑셀 파일 '{EXCEL_FILE}'을 찾을 수 없습니다.")
        return

    conn = None
    try:
        # [수정됨] 로컬 DB 대신 엑셀 파일에서 데이터를 직접 읽습니다.
        print(f"'{EXCEL_FILE}' 파일의 '{SHEET_NAME}' 시트 읽기 시작...")
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, engine='openpyxl')
        df = df.where(pd.notnull(df), None)
        df = df.dropna(how='all')
        df = df.drop_duplicates(subset=['ID'], keep='first')
        print(f"✅ 엑셀에서 총 {len(df)}개의 데이터를 읽었습니다.")

        print("\nRender (NEW_DB)에 연결 및 데이터 복사 시작...")
        conn = psycopg.connect(NEW_DB_URL)
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
        print("-------------------------------------------")
        print(f"✅ Render DB 업데이트 완료! (승인 기능 추가됨)")

    except Exception as e:
        print(f"\n❌ DB 작업 중 오류 발생: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    migrate_data()