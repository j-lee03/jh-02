import pandas as pd
import sqlite3
import os

# --- 설정 ---
EXCEL_FILE = 'performances.xlsx' # 1. 읽어올 원본 엑셀 파일
DB_FILE = 'events.db'           # 2. 새로 생성할 데이터베이스 파일
TABLE_NAME = 'performances'     # 3. DB 파일 안에 만들 '표(테이블)'의 이름

# (중요!) 엑셀 파일에서 읽어올 시트(탭)의 이름
SHEET_NAME = '전체일정'
# -------------

def migrate_data():
    """
    엑셀 파일의 '기본표' 시트에서 데이터를 읽어 SQLite DB 파일로 옮기는 함수
    """

    # 1. 엑셀 파일이 있는지 확인
    if not os.path.exists(EXCEL_FILE):
        print(f"오류: '{EXCEL_FILE}'을 찾을 수 없습니다.")
        print(f"스크립트와 같은 폴더({os.getcwd()})에 엑셀 파일이 있는지 확인하세요.")
        return

    print(f"'{EXCEL_FILE}' 파일 읽기를 시작합니다...")

    # 2. Pandas를 사용해 엑셀 파일의 '기본표' 시트만 읽어옵니다.
    try:
        df = pd.read_excel(EXCEL_FILE,
                         sheet_name=SHEET_NAME, # <-- 이 부분이 핵심입니다!
                         engine='openpyxl')
    except Exception as e:
        print(f"엑셀 파일을 읽는 중 오류 발생: {e}")
        print(f"'{EXCEL_FILE}' 파일 안에 '{SHEET_NAME}' 시트(탭)가 있는지 확인하세요.")
        return

    if df.empty:
        print(f"'{SHEET_NAME}' 시트에 데이터가 없습니다.")

    print(f"'{SHEET_NAME}' 시트에서 총 {len(df)}개의 데이터를 읽었습니다.")

    # 3. SQLite 데이터베이스에 연결합니다.
    print(f"'{DB_FILE}' 데이터베이스에 연결합니다...")
    conn = sqlite3.connect(DB_FILE)

    try:
        # 4. (가장 중요) Pandas(df)에 저장된 데이터를 SQL 테이블로 저장합니다.
        print(f"'{TABLE_NAME}' 테이블에 데이터 저장을 시작합니다...")
        df.to_sql(TABLE_NAME, conn, if_exists='replace', index=False)

        print("-------------------------------------------")
        print(f"✅ 데이터 이동 성공!")
        print(f"'{EXCEL_FILE}'의 '{SHEET_NAME}' 시트 데이터가")
        print(f"'{DB_FILE}' 파일 안의 '{TABLE_NAME}' 테이블로 복사되었습니다.")

    except Exception as e:
        print(f"데이터베이스에 저장하는 중 오류 발생: {e}")

    finally:
        # 5. 작업이 끝나면 데이터베이스 연결을 닫습니다.
        conn.close()
        print("데이터베이스 연결을 닫았습니다.")


# --- 이 스크립트를 실행하면 migrate_data 함수가 호출됩니다 ---
if __name__ == '__main__':
    migrate_data()