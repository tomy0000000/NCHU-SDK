"""SDK for accessing NCHU Portal System"""
import logging
import traceback
from enum import Enum
from functools import wraps
from getpass import getpass
from time import time
from urllib import parse

import bs4
import pandas as pd
import requests

__version__ = "0.2.0"

logger = logging.getLogger(__name__)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler = logging.FileHandler(f"log_{int(time())}.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_1_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36"
)

PORTAL_BASE = "https://portal.nchu.edu.tw"
ACAD_BASE = "https://onepiece2-sso.nchu.edu.tw"
ACAD_MAP = {
    "home": "cofsys/plsql/acad_home",
    "login": "cofsys/plsql/ACAD_PASSCHK",
    "sidebar": "cofsys/plsql/studframe_left",
    "ge_entry": "cofsys/plsql/gned_main",
    "ge_select": "cofsys/plsql/gned_add1_workflow",
    "ge_list": "cofsys/plsql/gned_add2_list",
    "ge_check": "cofsys/plsql/gned_add3_check",
    "ge_final": "cofsys/plsql/gned_add4_dml",
    "dept_list": "cofsys/plsql/enro_nomo1_list",
    "dept_check": "cofsys/plsql/enro_nomo2_check",
    "dept_final": "cofsys/plsql/enro_nomo3_dml",
    "direct_list": "cofsys/plsql/enro_direct1_list",
    "direct_check": "cofsys/plsql/enro_direct2_chk",
    "direct_final": "cofsys/plsql/enro_direct3_dml",
    "delete_list": "cofsys/plsql/enro_del1_list",
    "delete_check": "cofsys/plsql/enro_del2_check",
    "delete_final": "cofsys/plsql/enro_del3_drop",
    "ques_list": "cofsys/plsql/Stud_Question_Main1",
    "ques_confirm": "cofsys/plsql/Stud_Question_Conf3",
    "ques_final": "cofsys/plsql/Stud_Question_Dml4",
    "ques_ta_list": "cofsys/plsql/ta_ques_stu",
    "ques_ta_fill": "cofsys/plsql/ta_ques_stu_des",
    "ques_ta_send": "cofsys/plsql/ta_ques_stu_des_udt",
}

ERROR_MSG = """
Oops, error <{error}> raised when running <{func_name}>!
details: {error_msg}

Please click the folder on left sidebar and download all logs and tracebacks,
then report this incident to author at
https://github.com/tomy0000000/NCHU-SDK/issues

or email to
0zh7o2e41@relay.firefox.com

Thank you ( ´▽｀).
"""


class FillingPolicy(Enum):
    AWFUL = 1
    NEUTRAL = 3
    GREAT = 5


def _acad_url(path: str):
    return parse.urljoin(ACAD_BASE, ACAD_MAP[path])


def catch_error(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            if str(error) == "Incorrect password":
                raise error
            print(
                ERROR_MSG.format(
                    error=error.__class__.__name__,
                    error_msg=str(error),
                    func_name=func.__name__,
                )
            )
            traceback_file = f"traceback_{int(time())}.txt"
            with open(traceback_file, "w") as f:
                f.write(traceback.format_exc())
            logger.info(f"Write traceback to {traceback_file}")

    return decorated_function


def acad_required(func):
    @wraps(func)
    def decorated_function(self, *args, **kwargs):
        if not any(
            [parse.urlparse(ACAD_BASE).netloc in c.domain for c in self.session.cookies]
        ):
            self.login_acad()
        return func(self, *args, **kwargs)

    return decorated_function


class Student:
    def __init__(self, username=None, password=None):
        if not username:
            username = input("Username: ")
        if not password:
            password = getpass("Password: ")
        self.username = username
        self.__password = password
        logger.info(f"User <{self.username}> created")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self.login_sso()
        logger.info(f"User <{self.username}> logined to SSO")

    #
    # Login Methods
    #

    @catch_error
    def login_sso(self):
        # Hit Portal to get SSO login location
        page_portal_entry = self.session.get(PORTAL_BASE)
        soup_portal_entry = bs4.BeautifulSoup(page_portal_entry.text, features="lxml")
        url_sso_entry = parse.urljoin(
            page_portal_entry.url, soup_portal_entry.find("form").attrs["action"]
        )
        logger.debug(f"SSO Entry URL: {url_sso_entry}")

        # Get SSO login page
        page_sso_entry = self.session.post(url_sso_entry)
        assert page_sso_entry.status_code == 200
        form_sso = bs4.BeautifulSoup(page_sso_entry.text, features="lxml").find("form")
        url_sso_login = form_sso.attrs["action"]
        form_login_data = {
            field["name"]: field["value"]
            for field in form_sso.select("input[type=hidden]")
        }
        logger.debug(f"SSO login URL: {url_sso_login}")
        logger.debug(f"SSO login data (redacted): {form_login_data}")
        form_login_data["Ecom_User_ID"] = self.username
        form_login_data["Ecom_Password"] = self.__password

        # Login with URL given in entry page
        page_sso_login = self.session.post(
            url_sso_login,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=form_login_data,
        )
        assert page_sso_login.status_code == 200
        if "Login failed" in page_sso_login.text or "登入失敗" in page_sso_login.text:
            raise ValueError("Incorrect password")

    @catch_error
    def login_acad(self):
        # Redirect Authentication to ACAD System and acquire frameset
        page_login = self.session.post(
            _acad_url("login"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "v_emp": self.username,
                "v_pwd": self.__password,
                "v_lang": "chn",
            },
        )
        assert page_login.status_code == 200
        assert "FRAMESET" in page_login.text
        logger.debug("ACAD Login request success")

        # Get ACAD Sidebar (for verification)
        page_sidebar = self.session.get(_acad_url("sidebar"))
        assert page_sidebar.status_code == 200
        assert self.username in page_sidebar.text
        logger.debug("ACAD Sidebar request success")

        logger.info(f"User <{self.username}> logined to ACAD")

    #
    # Questionnaire methods
    #

    @catch_error
    @acad_required
    def get_questionnaire(self):
        logger.info("BEGIN: get_questionnaire")
        url_list = _acad_url("ques_list")
        page = self.session.get(url_list)
        page.raise_for_status()
        assert "期末教學意見調查" in page.text
        logger.debug("List page request success")

        table = bs4.BeautifulSoup(page.text, features="lxml").find_all("table")[2]
        header = ["".join(tag.strings) for tag in table.select("th")]
        print(table.find_all("tr"))
        links = []
        complete = []
        for row in table.find_all("tr"):
            if not row.select_one("td:nth-of-type(10) a"):
                continue
        links = [
            parse.urljoin(url_list, row.select_one("td:nth-of-type(10) a")["href"])
            for row in table.find_all("tr")
        ]
        complete = [
            bool(row.select_one("td:nth-of-type(11) img"))
            for row in table.find_all("tr")
        ]
        logger.debug(f"Parsed links: {links}")
        logger.debug(f"Parsed complete: {complete}")
        converters = {i: lambda x: str(x) for i in range(11)}
        df = pd.read_html(str(table), converters=converters)[0]
        df.columns = header
        df["填答評量"] = links
        df["完成填答"] = complete
        results = [val for key, val in df.T.to_dict().items()]
        logger.info("END: get_questionnaire")

        return results

    @catch_error
    @acad_required
    def fill_questionnaire(self, questionnaire, policy=FillingPolicy.GREAT):
        logger.info("BEGIN: fill_questionnaire")
        policy = FillingPolicy(policy)
        logger.debug(f"policy: {policy}")
        page_fill = self.session.get(questionnaire["填答評量"])
        assert page_fill.status_code == 200
        assert questionnaire["課程名稱"] in page_fill.text
        logger.debug("Fill page request success")

        # Prepare form data
        form_fill_data = {}
        form_fill = bs4.BeautifulSoup(page_fill.text, features="lxml").find("form")

        # Collect hidden field
        hiddens = form_fill.select("input[type=hidden]")
        for field in hiddens:
            form_fill_data[field["name"]] = field["value"]
        logger.debug(f"hiddens: {hiddens}")

        # Fill radios
        radios = {field["name"]: "" for field in form_fill.select("input[type=radio]")}
        for field in radios:
            form_fill_data[field] = policy.value
        logger.debug(f"hiddens: {hiddens}")

        # Outliners
        if "v_A1" in form_fill_data:
            form_fill_data["v_A1"] = 1
            logger.debug(f"v_A1 fixed: {form_fill_data['v_A1']}")
        if "v_B10" in form_fill_data:
            form_fill_data["v_B10"] = 3 - (policy.value - 3)
            logger.debug(f"v_B10 fixed: {form_fill_data['v_B10']}")

        # Fill texts
        texts = {field["name"]: "" for field in form_fill.select("input[type=text]")}
        for field in texts:
            form_fill_data[field] = ""
        logger.debug(f"texts: {texts}")

        logger.debug(f"form_fill_data: {form_fill_data}")
        url_confirm = _acad_url("ques_confirm")
        page_confirm = self.session.post(url_confirm, data=form_fill_data)
        assert page_confirm.status_code == 200
        assert questionnaire["課程名稱"] in page_confirm.text
        logger.debug("Confirm page request success")

        # Recollect data from confirm form
        form_confirm_data = {}
        form_confirm = bs4.BeautifulSoup(page_confirm.text, features="lxml").find(
            "form"
        )
        for field in form_confirm.select("input[type=hidden]"):
            form_confirm_data[field["name"]] = field["value"]

        logger.debug(f"form_confirm_data: {form_confirm_data}")
        url_final = _acad_url("ques_final")
        page_final = self.session.post(url_final, data=form_confirm_data)
        assert page_final.status_code == 200
        assert "儲存完成" in page_final.text
        logger.debug("Final page request success")

        logger.info("END: fill_questionnaire")
        return True

    @catch_error
    @acad_required
    def get_ta_questionnaire(self):
        logger.info("BEGIN: get_ta_questionnaire")
        url_list = _acad_url("ques_ta_list")
        page = self.session.get(url_list)
        assert page.status_code == 200
        assert "學生TA服務意見調查" in page.text
        logger.debug("List page request success")

        table = bs4.BeautifulSoup(page.text, features="lxml").find_all("table")[2]
        header = ["".join(tag.strings) for tag in table.select("th")]

        # Parse Results
        results = []
        for course in table.find_all("tr"):
            questionnaire = {}
            for index, (key, content) in enumerate(zip(header, course.find_all("td"))):
                if index == 7:
                    questionnaire[key] = []
                    questionnaire["完成填答"] = []
                    for form in content.find_all("form"):
                        questionnaire[key].append(
                            {
                                field["name"]: field["value"]
                                for field in form.select("input[type=hidden]")
                            }
                        )
                        questionnaire["完成填答"].append(
                            bool("已填寫" in "".join(form.strings))
                        )
                else:
                    questionnaire[key] = "".join(content.strings).replace("\n", "")
            results.append(questionnaire)

        logger.info("END: get_ta_questionnaire")
        return results

    @catch_error
    @acad_required
    def fill_ta_questionnaire(self, ta_questionnaire, policy=FillingPolicy.GREAT):
        logger.info("BEGIN: fill_ta_questionnaire")
        policy = FillingPolicy(policy)
        logger.debug(f"policy: {policy}")
        page_fill = self.session.post(_acad_url("ques_ta_fill"), data=ta_questionnaire)
        assert page_fill.status_code == 200
        assert ta_questionnaire["v_ta"] in page_fill.text
        logger.debug("Fill page request success")

        # Prepare form data
        form_fill_data = {}
        form_fill = bs4.BeautifulSoup(page_fill.text, features="lxml").find("form")

        # Collect hidden field
        hiddens = form_fill.select("input[type=hidden]")
        for field in hiddens:
            form_fill_data[field["name"]] = field["value"]
        logger.debug(f"hiddens: {hiddens}")

        # Fill radios
        radios = {field["name"]: "" for field in form_fill.select("input[type=radio]")}
        for field in radios:
            form_fill_data[field] = policy.value
        logger.debug(f"hiddens: {hiddens}")

        # Fill texts
        form_fill_data[form_fill.find("textarea")["name"]] = ""

        logger.debug(f"form_fill_data: {form_fill_data}")
        url_send = _acad_url("ques_ta_send")
        page_send = self.session.post(url_send, data=form_fill_data)
        assert page_send.status_code == 200
        assert f"{ta_questionnaire['v_ta']}&nbsp;&nbsp;已填寫" in page_send.text
        logger.debug("Confirm page request success")

        logger.info("END: fill_ta_questionnaire")
        return True

    #
    # Add/Drop Course Methods
    #

    @staticmethod
    def _get_add_course_form_table(raw_html, method):
        INDEX = {
            "GE": 1,
            "ACAD": 1,
            "CODE": 0,
            "DROP": 0,
        }
        soup = bs4.BeautifulSoup(raw_html, "lxml")
        course_table = soup.find_all("form")[INDEX[method]]
        return course_table

    @staticmethod
    def _course_code_to_secret(course_table, course_code):
        for tag in course_table.find_all("tr"):
            if tag.find_all("td")[1].string == course_code:
                return tag.find("input").attrs["value"]
        return None

    def ge_get_list(self):
        r6 = self.session.get(_acad_url("ge_entry"))
        assert r6.status_code == 200
        assert "選課狀態" in r6.text

        r7 = self.session.get(_acad_url("ge_select"))
        assert r7.status_code == 200
        assert "本時段不開放此功能" not in r7.text

        r8 = self.session.post(_acad_url("ge_list"))
        assert r8.status_code == 200
        assert "本時段不開放此功能" not in r8.text
        assert "通識課程一覽表" in r8.text

        return r8.text

    @staticmethod
    def ge_get_df(raw_html):
        soup = bs4.BeautifulSoup(raw_html, "lxml")
        converters = {i: lambda x: str(x) for i in range(13)}
        df = pd.concat(
            [
                pd.read_html(str(soup.find_all("table")[6]), converters=converters)[0],
                pd.read_html(str(soup.find_all("table")[8]), converters=converters)[0],
                pd.read_html(str(soup.find_all("table")[10]), converters=converters)[0],
            ]
        ).set_index(1)
        return df

    def add_course_from_ge(self, course_code):
        ge_raw = self.ge_get_list()
        course_table = self._get_add_course_form_table(ge_raw, "GE")
        course_secret = self._course_code_to_secret(course_table, course_code)

        resp_confirm = self.session.post(
            _acad_url("ge_check"), data={"v_click": course_secret}
        )
        assert resp_confirm.status_code == 200
        assert course_code in resp_confirm.text

        soup_confirm = bs4.BeautifulSoup(resp_confirm.text, "lxml")
        confirm_code = soup_confirm.select_one("input[NAME='v_click']").attrs["value"]
        resp_final = self.session.post(
            _acad_url("ge_final"), data={"v_click": confirm_code}
        )
        assert resp_final.status_code == 200
        assert course_code in resp_final.text

        soup = bs4.BeautifulSoup(resp_final.text, "lxml")
        message = soup.find_all("table")[5].find_all("td")[11].string

        if "加選成功" not in message:
            raise RuntimeError(message)
        return message

    def acad_get_list(self):
        page_dept_list = self.session.get(_acad_url("dept_list"))
        assert page_dept_list.status_code == 200
        assert "系所必選修課程加選" in page_dept_list.text

        return page_dept_list.text

    @staticmethod
    def acad_get_df(raw_html):
        soup = bs4.BeautifulSoup(raw_html, "lxml")
        course_table = soup.find_all("form")[1]

    #         converters = {i:lambda x: str(x) for i in range(13)}
    #         df = pd.concat([
    #             pd.read_html(str(soup.find_all("table")[6]), converters=converters)[0],
    #             pd.read_html(str(soup.find_all("table")[8]), converters=converters)[0],
    #             pd.read_html(str(soup.find_all("table")[10]), converters=converters)[0]
    #         ]).set_index(1)
    #         return course_table, df

    def add_course_from_acad(self, course_code):
        acad_raw = self.acad_get_list()
        course_table = self._get_add_course_form_table(acad_raw, "ACAD")
        course_secret = self._course_code_to_secret(course_table, course_code)

        resp_confirm = self.session.post(
            _acad_url("dept_check"), data={"v_tick": course_secret}
        )
        assert resp_confirm.status_code == 200
        assert course_code in resp_confirm.text

        resp_final = self.session.post(
            _acad_url("dept_final"),
            data={
                "p_stud_no": self.username,
                "v_tick": course_secret,
            },
        )
        assert resp_final.status_code == 200
        assert course_code in resp_final.text

        soup = bs4.BeautifulSoup(resp_final.text, "lxml")
        message = soup.find_all("table")[6].find_all("td")[7].string

        if "加選成功" not in message:
            raise RuntimeError(message)
        return message

    def add_course_with_codes(self, course_codes):
        r1 = self.session.get(_acad_url("direct_list"))
        assert r1.status_code == 200
        assert "選課號碼加選" in r1.text

        data_confirm = {"V_WANT": code for code in course_codes}
        page_confirm = self.session.post(_acad_url("direct_check"), data=data_confirm)
        assert page_confirm.status_code == 200
        for code in course_codes:
            assert code in page_confirm.text

        course_table = self._get_add_course_form_table(page_confirm.text, "CODE")
        course_secrets = [
            self._course_code_to_secret(course_table, code) for code in course_codes
        ]

        data_final = {"v_tick": secret for secret in course_secrets}
        data_final["p_stud_no"] = self.username
        resp_final = self.session.post(_acad_url("direct_final"), data=data_final)
        assert resp_final.status_code == 200
        for code in course_codes:
            assert code in resp_final.text

        soup = bs4.BeautifulSoup(resp_final.text, "lxml")
        messages = []
        for row in soup.find_all("table")[0].find_all("tr")[:-1]:
            messages.append(row.find_all("td")[7].string)
        return course_table, messages

    def remove_course(self, course_code):
        url_list = _acad_url("delete_list")
        url_check = _acad_url("delete_check")
        url_final = _acad_url("delete_final")

        resp_list = self.session.get(url_list)
        assert resp_list.status_code == 200
        assert "課程退選" in resp_list.text

        course_table = self._get_add_course_form_table(resp_list.text, "DROP")
        course_secret = self._course_code_to_secret(course_table, course_code)

        page_confirm = self.session.post(url_check, data={"v_del": course_secret})
        assert page_confirm.status_code == 200
        assert course_code in page_confirm.text

        resp_final = self.session.post(url_final, data={"v_del": course_secret})
        assert resp_final.status_code == 200
        assert course_code in resp_final.text

        soup = bs4.BeautifulSoup(resp_final.text, "lxml")
        message = soup.find_all("table")[1].find_all("td")[6].string

        if "退選成功" not in message:
            raise RuntimeError(message)
        return message
