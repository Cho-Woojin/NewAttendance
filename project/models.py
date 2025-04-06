import unicodedata
import csv
import os
import json
from datetime import datetime, timedelta
import pytz

# 파일 경로와 작업 시간 정의
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 현재 파일의 디렉토리
LOG_FILE = os.path.join(BASE_DIR, "attendance.csv")
LAST_RESET_FILE = os.path.join(BASE_DIR, "last_reset.txt")
HOLIDAYS_FILE = os.path.join(BASE_DIR, "holidays.json")
CONFIG_FILE = os.path.join(BASE_DIR, "semester.json")
WORK_HOURS = (8, 22)

KST = pytz.timezone('Asia/Seoul')

def get_total_period_from_config():
    """
    semester.json 파일에서 학기 시작일을 불러와 누적 기간 반환
    """
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError("semester.json 파일이 존재하지 않습니다.")

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = json.load(file)

    semester_start_str = config.get("semester_start")
    if not semester_start_str:
        raise ValueError("semester.json에 'semester_start' 값이 없습니다.")

    semester_start = datetime.strptime(semester_start_str, "%Y-%m-%d").replace(tzinfo=KST)
    today = datetime.now(KST)
    return semester_start, today


# 학기 시작일 설정
def get_total_period():
    semester_start = datetime(2025, 3, 1, tzinfo=KST)  # <== 여기를 학기 시작일로 설정
    today = datetime.now(KST)
    return semester_start, today


# 날짜와 시간 포맷팅
def format_date_and_time():
    days_in_korean = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]
    now = datetime.now(KST)
    korean_day = days_in_korean[now.weekday()]
    formatted_date = now.strftime(f"%Y년 %m월 %d일 {korean_day}")
    formatted_time = now.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후")
    return formatted_date, formatted_time

# 로그 초기화
def reset_logs_with_timestamp():
    today_date = datetime.now(KST).strftime("%Y-%m-%d")
    if os.path.exists(LAST_RESET_FILE):
        with open(LAST_RESET_FILE, "r") as file:
            last_reset_date = file.read().strip()
        if last_reset_date == today_date:
            print("이미 초기화되었습니다.")
            return

    print("CSV 파일 초기화 중...")  # 디버깅 출력
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if os.stat(LOG_FILE).st_size == 0:
            writer.writerow(["학번", "날짜", "시간", "기록"])  # 헤더 추가

    with open(LAST_RESET_FILE, "w") as file:
        file.write(today_date)


# 공휴일 데이터 로드 및 저장
def load_holidays():
    if not os.path.exists(HOLIDAYS_FILE):
        with open(HOLIDAYS_FILE, "w") as file:
            json.dump([], file)
    with open(HOLIDAYS_FILE, "r") as file:
        return json.load(file)

def save_holidays(holidays):
    with open(HOLIDAYS_FILE, "w") as file:
        json.dump(holidays, file, indent=4)


def is_valid_day_and_time(action=None):
    now = datetime.now(KST)
    weekday = now.weekday()
    hour = now.hour
    today_date = now.strftime("%Y-%m-%d")
    holidays = load_holidays()

    # 평일이고 공휴일이 아니어야 함
    if not (0 <= weekday < 5) or today_date in holidays:
        return False

    # 출근은 8시~22시까지
    if action == "check_in":
        return 8 <= hour < 22

    # 퇴근은 8시~24시까지
    if action == "check_out":
        return 8 <= hour < 24

    # 기본은 출근 기준
    return 8 <= hour < 22


# 기록 여부 확인
def has_record(student_id, record_type):
    try:
        with open(LOG_FILE, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # 헤더 건너뜀
            today_date = datetime.now(KST).strftime("%Y-%m-%d")
            for row in reader:
                if len(row) >= 4 and row[0] == student_id and row[1] == today_date and row[3] == record_type:
                    return True
    except FileNotFoundError:
        pass
    return False

# 시간 반올림 함수 (0.0, 0.5 단위로만 반올림)
def round_time_to_half_hour(start_time=None, end_time=None):
    if start_time and end_time:
        total_minutes = (end_time - start_time).seconds // 60
    elif start_time:
        total_minutes = start_time.hour * 60 + start_time.minute
    else:
        raise ValueError("start_time 또는 end_time 중 하나는 반드시 제공되어야 합니다.")

    hours = total_minutes // 60
    minutes = total_minutes % 60

    # 0~15분은 0으로, 15~45분은 30으로, 45~59분은 다음 시의 0으로 반올림
    if minutes < 15:
        minutes = 0
    elif minutes < 45:
        minutes = 30
    else:
        minutes = 0
        hours += 1

    return f"{hours + (minutes / 60):.1f}".rstrip('0').rstrip('.')


# CSV 기록
def write_to_csv(student_id, action_type):
    now = datetime.now(KST)
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([student_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), action_type])


def sort_names(names):
    """
    한글이 먼저, 영어가 나중에 오도록 정렬합니다.
    """
    def sorting_key(name):
        first_char = name[0]
        if "\uAC00" <= first_char <= "\uD7AF":  # 한글 범위
            return (0, name)  # 한글은 우선순위 0
        else:
            return (1, name)  # 영어는 우선순위 1

    return sorted(names, key=sorting_key)


# 주간 데이터 계산
def calculate_weekly_data(week_start, week_end, student_data):
    """
    주간 데이터를 계산하여 각 학생의 근무 시간과 출퇴근 기록 반환.
    """
    week_start = week_start.astimezone(KST)
    week_end = week_end.astimezone(KST)

    if not os.path.exists(LOG_FILE):
        return {}

    week_data = {}
    with open(LOG_FILE, mode="r", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader)  # 헤더 건너뜀
        for row in reader:
            if len(row) < 4:
                continue
            student_id, date, time, record_type = row
            record_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=KST)

            if week_start <= record_date <= week_end:
                if student_id not in week_data:
                    week_data[student_id] = {day: {"출근": None, "퇴근": None, "근무시간": "0.0"} for day in range(5)}
                day_of_week = record_date.weekday()
                if 0 <= day_of_week < 5:
                    time_obj = datetime.strptime(time, "%H:%M:%S").time()

                    if record_type == "퇴근" and time_obj.hour >= 22:
                        rounded_time = "22"
                    else:
                        adjusted_time = datetime.combine(datetime.today(), time_obj)
                        rounded_time = round_time_to_half_hour(adjusted_time)

                    week_data[student_id][day_of_week][record_type] = rounded_time


    # 근무 시간 계산
    for student_id, days in week_data.items():
        for day, records in days.items():
            if records["출근"] and records["퇴근"]:
                try:
                    start_time = max(8.0, float(records["출근"]))
                    end_time = min(22.0, float(records["퇴근"]))
                    work_time = max(0.0, end_time - start_time)
                    records["근무시간"] = f"{work_time:.1f}"
                except ValueError:
                    records["근무시간"] = "0.0"

    # 학생 이름 기준으로 정렬
    sorted_week_data = {}
    sorted_names = sort_names([student_data[student_id] for student_id in week_data if student_id in student_data])
    for name in sorted_names:
        student_id = [key for key, value in student_data.items() if value == name][0]
        sorted_week_data[name] = week_data.get(student_id, {})

    return sorted_week_data


def calculate_total_hours(start_date, end_date, student_data):
    start, end = get_total_period_from_config()

    total_data = {}
    current = start
 
    while current <= end:
        week_start = current - timedelta(days=current.weekday())
        week_end = week_start + timedelta(days=4)

        week_data = calculate_weekly_data(week_start, week_end, student_data)

        for student_name, days in week_data.items():
            if student_name not in total_data:
                total_data[student_name] = 0.0
            for day in days.values():
                total_data[student_name] += float(day["근무시간"])

        current += timedelta(weeks=1)

    ranked_total = sorted(total_data.items(), key=lambda x: (-x[1], x[0]))
    return ranked_total