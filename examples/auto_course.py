import json
import logging
import time

from pushover_complete import PushoverAPI
from tqdm.auto import tqdm

from nchu import Student

# Fill in your credentials
USERNAME = ""
PASSWORD = ""
PUSHOVER_TOKEN = ""
PUSHOVER_USER_KEY = ""
SLEEP_TIME = 1


def load_monitoring_courses():
    with open("monitoring.json") as f:
        return json.load(f)


def store_monitoring_courses(new_courses):
    with open("monitoring.json", "w") as f:
        return json.dump(new_courses, f)


def notify(message):
    p = PushoverAPI(PUSHOVER_TOKEN)
    p.send_message(PUSHOVER_USER_KEY, message, priority=2, expire=3600, retry=30)


def handle_0349_conflict(Tomy, table):
    available_seat = int(table.find_all("td")[8].string)
    selected_seat = int(table.find_all("td")[9].string)
    message = ""
    if available_seat > selected_seat:
        notify("OP-GDYY Triggered")
        try:
            Tomy.remove_course("0348")
            table, messages = Tomy.add_course_with_codes(["0349"])
            message = messages[0]
        except Exception:
            logging.exception("Error")
            message = "Error"
    else:
        logging.info("OP-GDYY handled without select")
    return message


def check_python(Tomy):
    url_list = "https://onepiece2-sso.nchu.edu.tw/cofsys/plsql/enro_direct1_list"
    url_check = "https://onepiece2-sso.nchu.edu.tw/cofsys/plsql/enro_direct2_chk"

    r1 = Tomy.session.get(url_list)
    assert r1.status_code == 200
    assert "選課號碼加選" in r1.text

    resp_check = Tomy.session.post(url_check, data="V_WANT=1159")
    assert resp_check.status_code == 200
    assert "1159" in resp_check.text
    course_table = Tomy._get_add_course_form_table(resp_check.text, "CODE")
    available_seat = int(course_table.find_all("td")[8].string)
    selected_seat = int(course_table.find_all("td")[9].string)
    if available_seat > selected_seat:
        notify("OP-Python now Available")
    else:
        logging.info("OP-Python checked without select")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
    )
    while True:
        try:
            logging.info("-----Start Session-----")
            # Start new Session
            monitoring = load_monitoring_courses()
            Tomy = Student(USERNAME, PASSWORD)
            Tomy.login_acad()
            logging.info("Login Success")

            # Loop for monitoring
            selected = []
            for idx in range(0, len(monitoring), 10):
                course_codes = monitoring[idx : idx + 10]

                logging.info(f"Try Selecting <{', '.join(course_codes)}>")
                try_count = 5
                success = False
                for i in range(try_count):
                    try:
                        table, messages = Tomy.add_course_with_codes(course_codes)
                        logging.info(messages)

                        # Special handle for 0349 GuDianYinYueShangXi
                        if "0349" in course_codes:
                            message = handle_0349_conflict(Tomy, table)
                            if "加選成功" in message:
                                notify(f"Selected: 0349 ({message})")
                                selected.append("0349")

                        # for idx, msg in enumerate(messages):
                        #     if "加選成功" in msg:
                        #         notify(f"Selected: {course_codes[idx]} ({msg})")
                        #         selected.append(course_codes[idx])
                        logging.info("Attempt failed with no error")
                        break
                    except Exception:
                        logging.exception("Error")
                else:
                    logging.info(f"Exceed max retires: {try_count}")

            if selected:
                new_monitoring = monitoring.copy()
                for selected_course in selected:
                    new_monitoring.remove(selected_course)
                store_monitoring_courses(new_monitoring)

            # Commissioned
            check_python(Tomy)
        except Exception:
            logging.exception("Error")
        logging.info(f"Sleep for {SLEEP_TIME} minutes")
        for _ in tqdm(range(SLEEP_TIME * 60)):
            time.sleep(1)
