import logging
import traceback
from enum import Enum
from functools import wraps
from getpass import getpass
from time import time
from urllib.parse import urljoin

import bs4
import pandas as pd
import requests

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
    return urljoin(ACAD_BASE, ACAD_MAP[path])


def catch_error(func):
    @wraps(func)
    def decorated_view_function(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as error:
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

    return decorated_view_function


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

    @catch_error
    def login_sso(self):
        url_entry = "https://idp.nchu.edu.tw/nidp/idff/sso"
        param_entry = {
            "id": 4,
            "sid": 2,
            "option": "credential",
            "sid": 2,
            "target": urljoin(ACAD_BASE, ACAD_MAP["home"]),
        }

        # Main Entry Page
        page_entry = self.session.post(url_entry, params=param_entry)
        assert page_entry.status_code == 200

        # Login with URL given in entry page
        url_login = (
            bs4.BeautifulSoup(page_entry.text, "lxml").find("form").attrs["action"]
        )
        logger.debug(f"SSO login URL: {url_login}")
        page_login = self.session.post(
            url_login,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "Ecom_User_ID": self.username,
                "Ecom_Password": self.__password,
                "option": "credential",
            },
        )
        assert page_login.status_code == 200

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

    @catch_error
    def get_questionnaire(self):
        logger.info("BEGIN: get_questionnaire")
        url_list = _acad_url("ques_list")
        page = self.session.get(url_list)
        assert page.status_code == 200
        assert "期末教學意見調查" in page.text
        logger.debug("List page request success")

        table = bs4.BeautifulSoup(page.text, features="lxml").find_all("table")[2]
        header = ["".join(tag.strings) for tag in table.select("th")]
        links = [
            urljoin(url_list, row.select_one("td:nth-of-type(10) a")["href"])
            for row in table.find_all("tr")
        ]
        logger.debug(f"Parsed links: {links}")
        complete = [
            bool(row.select_one("td:nth-of-type(11) img"))
            for row in table.find_all("tr")
        ]
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
