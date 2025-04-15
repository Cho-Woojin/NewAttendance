import os
import csv
import json
from datetime import datetime, timedelta
from flask import render_template, request
from models import (
    write_to_csv,
    reset_logs_with_timestamp,
    load_holidays,
    save_holidays,
    is_valid_day_and_time,
    has_record,
    calculate_weekly_data,
    calculate_total_hours,
)
import pytz

# CSV 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = "attendance.csv"
BACKUP_DIR = "backups"
STUDENT_FILE = os.path.join(BASE_DIR, "students.json")

KST = pytz.timezone('Asia/Seoul')

# 백업 생성 함수
def backup_csv():
    """
    매일 백업 디렉토리에 현재 CSV 파일을 백업합니다.
    """
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    today = datetime.now().strftime("%Y-%m-%d")
    backup_file = os.path.join(BACKUP_DIR, f"attendance_backup_{today}.csv")
    if not os.path.exists(backup_file):  # 이미 백업된 경우 건너뜀
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as file:
                with open(backup_file, "w", encoding="utf-8") as backup:
                    backup.write(file.read())


# 시간 반올림 함수
def round_time_to_decimal(time_obj):
    """
    시간(datetime 객체)을 소수점 형식으로 반올림하여 반환.
    """
    hour = time_obj.hour
    minute = time_obj.minute
    if minute < 15:
        minute_decimal = 0.0
    elif minute < 45:
        minute_decimal = 0.5
    else:
        minute_decimal = 1.0
    return f"{hour + minute_decimal:.1f}"


def load_student_data():
    """
    학생 정보(학번-이름)를 JSON 파일에서 불러옴.
    """
    try:
        with open(STUDENT_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"students.json 파일을 찾을 수 없습니다. 경로를 확인하세요: {STUDENT_FILE}")

def init_routes(app):
    # 홈페이지
    @app.route("/")
    def home():
        backup_csv()  # 매일 백업 실행
        formatted_date = get_current_date()
        current_time = get_current_time()
        return render_template(
            "home.html", date=formatted_date, time=current_time, message=None
        )

    # 출근/퇴근 기록
    @app.route("/record", methods=["POST"])
    def record():
        student_id = request.form.get("student_id", "").strip()
        action = request.form.get("action", "").strip()
        current_time = datetime.now(KST).strftime('%H시 %M분')

        # 학번 및 액션 누락 확인
        if not student_id or not action:
            print("Student ID or action missing.")  # 디버깅 출력
            return render_home("학번과 액션 값을 입력하세요.")

         # 출근/퇴근 시간 확인
        if not is_valid_day_and_time(action):
            return render_home("출퇴근 가능 시간이 아닙니다. 평일 08:00 ~ 22:00")


        # 학생 이름 확인
        student_name = load_student_data().get(student_id)
        if not student_name:
            print(f"Student ID {student_id} not found in student data.")  # 디버깅 출력
            return render_home("등록되지 않은 학생입니다.")


        # 출근 처리
        if action == "check_in":
            if has_record(student_id, "출근"):
                return render_home(f"{student_name}님, 이미 출근 기록이 존재합니다.")
            write_to_csv(student_id, "출근")
            return render_home(f"{student_name}님, {current_time}에 출근 기록이 추가되었습니다.")

        # 퇴근 처리
        if action == "check_out":
            if not has_record(student_id, "출근"):
                return render_home(f"{student_name}님, 출근 기록이 없습니다. 먼저 출근하세요.")
            if has_record(student_id, "퇴근"):
                return render_home(f"{student_name}님, 이미 퇴근 기록이 존재합니다.")
            write_to_csv(student_id, "퇴근")
            return render_home(f"{student_name}님, {current_time}에 퇴근 기록이 추가되었습니다.")

    # 주간 출석부
    @app.route("/weekly", methods=["GET", "POST"])
    def weekly():
        student_data = load_student_data()
        current_year = datetime.now(KST).year
        today = datetime.now(KST)
        today_date = today.date()

        # 기본값
        selected_month = today.month
        selected_week = None

        if request.method == "POST":
            selected_month = int(request.form.get("month"))
            selected_week = int(request.form.get("week"))

        # 주차 리스트 생성
        month_start = datetime(current_year, selected_month, 1, tzinfo=KST)
        month_end = (
            datetime(current_year, selected_month + 1, 1, tzinfo=KST) - timedelta(days=1)
            if selected_month < 12
            else datetime(current_year + 1, 1, 1, tzinfo=KST) - timedelta(days=1)
        )

        weeks = []
        current = month_start - timedelta(days=month_start.weekday())  # 월요일 기준

        while current <= month_end:
            week_end = current + timedelta(days=4)

            # 오늘 이후의 시작 주는 제외
            if current.date() > today_date:
                break

            if (month_start <= current <= month_end) or (month_start <= week_end <= month_end):
                weeks.append((current, week_end))

            current += timedelta(weeks=1)

        # 주차 자동 선택 (오늘 포함된 주차)
        if selected_week is None:
            for idx, (start, end) in enumerate(weeks):
                if start.date() <= today_date <= end.date():
                    selected_week = idx + 1
                    break
            else:
                selected_week = len(weeks)

        # 선택한 주차 인덱스로 start/end 가져오기
        if 1 <= selected_week <= len(weeks):
            week_start, week_end = weeks[selected_week - 1]
        else:
            # 주차 계산: 월요일 기준으로 선택 주차 직접 계산
            week_start = month_start - timedelta(days=month_start.weekday()) + timedelta(weeks=selected_week - 1)
            week_end = week_start + timedelta(days=4)

        # 출석 데이터 계산
        week_data = calculate_weekly_data(week_start, week_end, student_data)

        # 근무 시간 계산
        total_hours = []
        for student_name, days in week_data.items():
            total_time = sum(
                float(day["근무시간"])
                for day in days.values()
                if day["근무시간"] != "0.0"
            )
            total_hours.append((student_name, total_time))

        ranked_hours = sorted(total_hours, key=lambda x: (-x[1], x[0]))

        title = f"{selected_month}월 {selected_week}주차 ({week_start.strftime('%m/%d')}~{week_end.strftime('%m/%d')}) 출석부"

        return render_template(
            "weekly.html",
            title=title,
            week_data=week_data,
            ranked_hours=ranked_hours,
            selected_month=selected_month,
            selected_week=selected_week,
            weeks=weeks,
            enumerate=enumerate,
        )

    # 전체 근무시간 랭킹
    @app.route("/total")
    def total():
        student_data = load_student_data()
        today = datetime.now(KST)
        semester_start = datetime(today.year, 3, 1, tzinfo=KST)

        # 누적 근무시간 계산
        total_hours = calculate_total_hours(semester_start, today, student_data)
        # 누적 근무시간 순위 정렬
        ranked_total_hours = sorted(total_hours, key=lambda x: (-x[1], x[0]))


        return render_template(
            "total.html",
            title="IPUD 2025-1 출석 랭킹",
            ranked_total_hours=ranked_total_hours,
            date=today.strftime("%Y-%m-%d"),
            enumerate=enumerate
        )



    # 공휴일 관리
    @app.route("/manage_holidays", methods=["GET", "POST"])
    def manage_holidays():
        print("메니지 홀리데이 호출")

        holidays = load_holidays()
        if request.method == "POST":
            action = request.form["action"]
            if action == "add":

                new_date = request.form["date"]
                if new_date not in holidays:
                    holidays.append(new_date)
            elif action == "delete_selected":
                print("호출되었음음")
                selected_dates = request.form.getlist(
                    "selected_dates"
                )  # 다중 선택된 날짜
                print("selected_dates", selected_dates)
                holidays = [h for h in holidays if h not in selected_dates]
                print("holidays", holidays)
            save_holidays(holidays)
        return render_template("manage_holidays.html", holidays=holidays)

    # 헬퍼 함수
    def render_home(message):
        """
        헬퍼 함수: 홈 페이지로 메시지와 함께 리디렉션합니다.
        """
        # 메시지에 줄 바꿈 추가 (HTML 태그 사용)
        if "출퇴근 가능 시간이 아닙니다" in message:
            message = message.replace("(", "<br>(")  # 줄 바꿈을 추가

        return render_template(
            "home.html",
            date=get_current_date(),
            time=get_current_time(),
            message=message,
        )

    def get_current_date():
        days_in_korean = [
            "월요일",
            "화요일",
            "수요일",
            "목요일",
            "금요일",
            "토요일",
            "일요일",
        ]
        now = datetime.now(KST)
        korean_day = days_in_korean[now.weekday()]
        return now.strftime(f"%Y년 %m월 %d일 {korean_day}")

    def get_current_time():
        return (
            datetime.now(KST)
            .strftime("%p %I:%M")
            .replace("AM", "오전")
            .replace("PM", "오후")
        )
