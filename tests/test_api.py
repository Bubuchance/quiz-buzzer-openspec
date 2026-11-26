import csv
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from app.google_sheets import SheetsError, error_for_status
from app.guided_notes import spreadsheet_from_xlsx
from app.main import create_app
from samples.make_samples import group_workbook, moved_workbook, single_workbook

PASS = "246810"
EMAIL = "buzzer@demo.iam.gserviceaccount.com"
SHEET_URL = "https://docs.google.com/spreadsheets/d/{}/edit#gid=0"


class FakeGateway:
    """記憶體中的假 Google Sheets：read 回傳格線、write 直接改格線（模擬雲端）。"""

    def __init__(self):
        self.books, self.writes, self.shared = {}, [], set()

    def add(self, sheet_id, xlsx, title="學習單", shared=True):
        self.books[sheet_id] = spreadsheet_from_xlsx(xlsx, title)
        if shared:
            self.shared.add(sheet_id)

    def status(self):
        return {"configured": True, "service_account_email": EMAIL, "credentials_file": "credentials/x.json", "hint": None}

    def read(self, sheet_id):
        if sheet_id not in self.books:
            raise error_for_status(404, EMAIL)
        if sheet_id not in self.shared:
            raise error_for_status(403, EMAIL)
        return self.books[sheet_id]

    def write(self, sheet_id, sheet_title, updates):
        self.writes.append((sheet_id, sheet_title, dict(updates)))
        grid = next(g for g in self.books[sheet_id].sheets if g.title == sheet_title)
        for a1, value in updates.items():
            col = ord(a1[0]) - 64
            row = int(a1[1:])
            while len(grid.rows) < row:
                grid.rows.append([])
            while len(grid.rows[row - 1]) < col:
                grid.rows[row - 1].append("")
            grid.rows[row - 1][col - 1] = value


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
def client(gateway):
    app = create_app(PASS, gateway=gateway)
    with TestClient(app) as c:
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def teacher(client):
    r = client.post("/api/teacher/login", json={"passcode": PASS})
    assert r.status_code == 200
    return r.json()["token"]


def student(client, group, name="同學"):
    r = client.post("/api/student/join", json={"name": name, "group": group})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def upload(client, token, data=None, name="學習單", sheet_id="SHEET1234567890abcdefgh"):
    """把範例學習單放進假的雲端，再用網址匯入。"""
    gw = client.app.state.sheets
    if sheet_id not in gw.books:
        gw.add(sheet_id, data or group_workbook(), name)
    return client.post("/api/teacher/import/url", headers=auth(token), json={"url": SHEET_URL.format(sheet_id)})


def test_pages_served(client):
    for path in ["/", "/teacher", "/student", "/static/app.css", "/static/common.js"]:
        assert client.get(path).status_code == 200, path


def test_login_and_join(client):
    assert client.post("/api/teacher/login", json={"passcode": "nope"}).status_code == 401
    t = teacher(client)
    assert client.get("/api/me", headers=auth(t)).json()["role"] == "teacher"
    assert client.post("/api/student/join", json={"name": " ", "group": 1}).status_code == 400
    assert client.post("/api/student/join", json={"name": "a", "group": 9}).status_code == 400
    s = student(client, 2, "小明")
    assert client.get("/api/me", headers=auth(s)).json() == {"role": "student", "name": "小明", "group": 2}
    assert client.get("/api/groups").json() == {"groups": [1, 2, 3, 4]}


def test_permissions(client):
    t, s = teacher(client), student(client, 1)
    for path in ["/api/teacher/open", "/api/teacher/close", "/api/teacher/reset"]:
        assert client.post(path, headers=auth(s)).status_code == 403
        assert client.post(path).status_code == 401
    assert client.post("/api/teacher/settings", headers=auth(s), json={"group_count": 3}).status_code == 403
    assert upload(client, s).status_code == 403
    assert client.get("/api/teacher/export/csv", headers=auth(s)).status_code == 403
    assert client.post("/api/teacher/export/google-sheets", headers=auth(s)).status_code == 403
    assert client.get("/api/teacher/sheets-status", headers=auth(s)).status_code == 403
    assert client.post("/api/student/submit", headers=auth(t), json={"number": 1, "answers": ["x"]}).status_code == 403
    assert client.post("/api/student/submit", json={"number": 1, "answers": ["x"]}).status_code == 401


def test_chinese_title_used_for_csv_name(client):
    t = teacher(client)
    assert upload(client, t, name="第五章學習單").status_code == 200
    r = client.get("/api/teacher/export/csv", headers=auth(t))
    assert "%E7%AC%AC%E4%BA%94%E7%AB%A0" in r.headers["content-disposition"]  # 第五章


def test_sheets_status(client):
    t = teacher(client)
    assert client.get("/api/teacher/sheets-status", headers=auth(t)).json()["service_account_email"] == EMAIL


def test_import_errors(client, gateway):
    t = teacher(client)
    r = client.post("/api/teacher/import/url", headers=auth(t), json={"url": "https://example.com/x"})
    assert r.status_code == 400 and "Google Sheets 網址" in r.json()["detail"]
    r = client.post("/api/teacher/import/url", headers=auth(t), json={"url": SHEET_URL.format("MISSING1234567890abcdef")})
    assert r.status_code == 404 and "找不到試算表" in r.json()["detail"]
    gateway.add("PRIVATE1234567890abcdef", group_workbook(), shared=False)
    r = client.post("/api/teacher/import/url", headers=auth(t), json={"url": SHEET_URL.format("PRIVATE1234567890abcdef")})
    assert r.status_code == 403 and EMAIL in r.json()["detail"] and "編輯者" in r.json()["detail"]
    gateway.add("NOHEADER1234567890abcde", single_workbook())
    gateway.books["NOHEADER1234567890abcde"].sheets[0].rows = [["沒有標題"]]
    r = client.post("/api/teacher/import/url", headers=auth(t), json={"url": "NOHEADER1234567890abcde"})
    assert r.status_code == 400 and "題號" in r.json()["detail"]
    assert upload(client, t, moved_workbook(), sheet_id="MOVED1234567890abcdefgh").json()["question_count"] == 3


def test_gateway_unconfigured_message(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "none.json"))
    with TestClient(create_app(PASS)) as c:
        t = teacher(c)
        assert c.get("/api/teacher/sheets-status", headers=auth(t)).json()["configured"] is False
        r = c.post("/api/teacher/import/url", headers=auth(t), json={"url": SHEET_URL.format("ABCDEFGHIJKLMNOPQRSTUV")})
        assert r.status_code == 503 and "尚未設定 Google 服務帳號" in r.json()["detail"]


def test_full_flow_with_exports(client):
    t = teacher(client)
    assert upload(client, t).json()["question_count"] == 5
    s1, s2 = student(client, 1, "甲"), student(client, 2, "乙")
    assert client.post("/api/student/submit", headers=auth(s1), json={"number": 1, "answers": ["x"]}).status_code == 409
    assert client.post("/api/teacher/open", headers=auth(t)).status_code == 200
    assert client.post("/api/student/submit", headers=auth(s2), json={"number": 1, "answers": ["循序圖"]}).status_code == 200
    assert client.post("/api/student/submit", headers=auth(s1), json={"number": 1, "answers": ["元件圖"]}).status_code == 200
    r = client.post("/api/student/submit", headers=auth(s1), json={"number": 1, "answers": ["again"]})
    assert r.status_code == 409 and r.json()["detail"] == "本組已送出此題"
    assert client.post("/api/student/submit", headers=auth(s1),
                       json={"number": 3, "answers": ["聚合", "組合"]}).status_code == 200

    # 搶答中學生看不到別組
    state1 = client.get("/api/state", headers=auth(s1)).json()
    assert "results" not in state1 and "循序圖" not in str(state1)
    assert client.post("/api/teacher/close", headers=auth(t)).status_code == 200
    assert client.get("/api/state", headers=auth(s1)).json()["results"]["questions"][0]["winner"]["group"] == 2

    r = client.post("/api/teacher/export/google-sheets", headers=auth(t))
    assert r.status_code == 200, r.text
    assert r.json()["answered"] == 2 and r.json()["url"].startswith("https://docs.google.com/spreadsheets/d/")
    gw = client.app.state.sheets
    sheet_id, sheet_title, updates = gw.writes[-1]
    assert sheet_title == "Guided Notes"
    assert [updates[f"C{n}"] for n in range(3, 8)] == ["循序圖", "", "（1）聚合", "（2）組合", ""]
    grid = gw.books[sheet_id].sheets[0]
    assert grid.value(3, 3) == "循序圖" and grid.value(3, 2) == "描述物件之間訊息傳遞先後順序的圖是 ____。"

    r = client.get("/api/teacher/export/csv", headers=auth(t))
    rows = list(csv.reader(StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["題號", "組別", "答案", "搶答順位", "是否搶答成功", "送出時間"] and len(rows) == 1 + 3
    assert rows[3][:5] == ["3", "第 1 組", "（1）聚合（2）組合", "1", "是"]

    # 寫回後再匯入同一份試算表，題目結構不變
    client.post("/api/teacher/reset", headers=auth(t))
    assert upload(client, t).json()["question_count"] == 5
    assert client.get("/api/state", headers=auth(t)).json()["spreadsheet_url"].endswith("/edit")


def test_settings_api(client):
    t = teacher(client)
    assert client.post("/api/teacher/settings", headers=auth(t), json={"group_count": 6}).status_code == 200
    assert client.get("/api/groups").json()["groups"][-1] == 6
    r = client.post("/api/teacher/settings", headers=auth(t), json={"fair_delay": 31})
    assert r.status_code == 400
    assert client.post("/api/teacher/settings", headers=auth(t), json={"time_limit": 3601}).status_code == 400
    r = client.post("/api/teacher/settings", headers=auth(t), json={"fair_mode": True, "fair_delay": 5, "time_limit": 90})
    state = client.get("/api/state", headers=auth(t)).json()
    assert (state["fair_mode"], state["fair_delay"], state["time_limit"]) == (True, 5, 90)


def test_export_before_import(client):
    t = teacher(client)
    assert client.post("/api/teacher/export/google-sheets", headers=auth(t)).status_code == 409
    assert client.get("/api/teacher/export/csv", headers=auth(t)).status_code == 409


def test_writeback_rules(client, gateway):
    t = teacher(client)
    upload(client, t)
    r = client.post("/api/teacher/export/google-sheets", headers=auth(t))
    assert r.status_code == 409 and "搶答結束後" in r.json()["detail"]
    client.post("/api/teacher/open", headers=auth(t))
    assert client.post("/api/teacher/export/google-sheets", headers=auth(t)).status_code == 409
    client.post("/api/teacher/close", headers=auth(t))
    gateway.books["SHEET1234567890abcdefgh"].sheets[0].rows.pop(4)  # 匯入後有人刪掉第 3 題的第 1 小題
    r = client.post("/api/teacher/export/google-sheets", headers=auth(t))
    assert r.status_code == 409 and "重新匯入" in r.json()["detail"]
    assert gateway.writes == []


def test_websocket_sync(client):
    t = teacher(client)
    upload(client, t, single_workbook())
    s1, s2 = student(client, 1, "甲"), student(client, 2, "乙")
    with client.websocket_connect(f"/ws?token={s1}") as w1, client.websocket_connect(f"/ws?token={s2}") as w2:
        assert w1.receive_json()["state"]["phase"] == "ready"
        assert w2.receive_json()["state"]["phase"] == "ready"
        client.post("/api/teacher/open", headers=auth(t))
        assert w1.receive_json()["state"]["phase_label"] == "搶答中"
        assert w2.receive_json()["state"]["phase_label"] == "搶答中"
        # 第 2 組送出：第 1 組收到的快照不得含有第 2 組資訊
        client.post("/api/student/submit", headers=auth(s2), json={"number": 1, "answers": ["實作"]})
        snap1 = w1.receive_json()["state"]
        snap2 = w2.receive_json()["state"]
        assert snap1["my_submissions"] == {} and "實作" not in str(snap1)
        assert snap2["my_submissions"]["1"]["answers"] == ["實作"]
        client.post("/api/teacher/close", headers=auth(t))
        closed = w1.receive_json()["state"]
        assert closed["phase"] == "closed" and closed["results"]["questions"][0]["winner"]["group"] == 2
        w2.receive_json()


def test_websocket_rejects_bad_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=bad") as w:
            w.receive_json()


def test_passcode_generated_when_not_configured(monkeypatch):
    monkeypatch.delenv("TEACHER_PASSCODE", raising=False)
    app = create_app()
    code = app.state.activity.teacher_passcode
    assert len(code) == 6 and code.isdigit()


def test_passcode_from_environment(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSCODE", "env-secret")
    with TestClient(create_app()) as c:
        assert c.post("/api/teacher/login", json={"passcode": "env-secret"}).status_code == 200


def test_reconnect_receives_latest_state(client):
    """模擬斷線期間老師結束搶答：重新連線後第一個快照就是「已結束」與結果。"""
    t = teacher(client)
    upload(client, t, single_workbook())
    s1 = student(client, 1)
    with client.websocket_connect(f"/ws?token={s1}") as w:
        assert w.receive_json()["state"]["phase"] == "ready"
    client.post("/api/teacher/open", headers=auth(t))
    client.post("/api/teacher/close", headers=auth(t))
    with client.websocket_connect(f"/ws?token={s1}") as w:
        state = w.receive_json()["state"]
        assert state["phase"] == "closed" and "results" in state


def test_teacher_receives_new_submission_live(client):
    t = teacher(client)
    upload(client, t, single_workbook())
    s3 = student(client, 3, "阿三")
    with client.websocket_connect(f"/ws?token={t}") as wt:
        wt.receive_json()
        client.post("/api/teacher/open", headers=auth(t))
        wt.receive_json()
        client.post("/api/student/submit", headers=auth(s3), json={"number": 1, "answers": ["實作"]})
        q1 = wt.receive_json()["state"]["results"]["questions"][0]
        assert q1["submissions"][0]["group"] == 3 and q1["submissions"][0]["rank"] == 1
        assert q1["winner"]["group"] == 3


def test_mark_api_and_permissions(client):
    t = teacher(client)
    upload(client, t, single_workbook())
    s1 = student(client, 1)
    client.post("/api/teacher/open", headers=auth(t))
    client.post("/api/student/submit", headers=auth(s1), json={"number": 1, "answers": ["實作"]})
    r = client.post("/api/teacher/mark", headers=auth(t), json={"number": 1, "mark": "correct"})
    assert r.status_code == 409 and "結束後" in r.json()["detail"]
    client.post("/api/teacher/close", headers=auth(t))
    assert client.post("/api/teacher/mark", headers=auth(s1), json={"number": 1, "mark": "correct"}).status_code == 403
    assert client.post("/api/teacher/mark", headers=auth(t), json={"number": 1, "mark": "correct"}).status_code == 200
    state = client.get("/api/state", headers=auth(s1)).json()
    assert state["results"]["questions"][0]["mark"] == "correct"
    assert state["results"]["scoreboard"][0] == {"group": 1, "group_name": "第 1 組", "score": 1, "wins": 1}
    assert client.post("/api/teacher/mark", headers=auth(t), json={"number": 2, "mark": "correct"}).status_code == 409


def test_student_progress_in_state(client):
    t = teacher(client)
    upload(client, t, single_workbook())
    s1, s2 = student(client, 1), student(client, 2)
    client.post("/api/teacher/open", headers=auth(t))
    client.post("/api/student/submit", headers=auth(s2), json={"number": 2, "answers": ["x"]})
    client.post("/api/student/submit", headers=auth(s1), json={"number": 1, "answers": ["y"]})
    assert client.get("/api/state", headers=auth(s1)).json()["progress"] == {"submitted": 1, "total": 5}


def test_countdown_auto_close_broadcasts(client):
    t = teacher(client)
    upload(client, t, single_workbook())
    s1 = student(client, 1)
    client.post("/api/teacher/settings", headers=auth(t), json={"time_limit": 1})
    with client.websocket_connect(f"/ws?token={s1}") as w:
        w.receive_json()
        client.post("/api/teacher/open", headers=auth(t))
        opened = w.receive_json()["state"]
        assert opened["phase"] == "open" and 0 < opened["remaining_seconds"] <= 1
        closed = w.receive_json()["state"]  # 約 1 秒後伺服器自動結束並推送
        assert closed["phase"] == "closed" and closed["remaining_seconds"] is None
    r = client.post("/api/student/submit", headers=auth(s1), json={"number": 1, "answers": ["late"]})
    assert r.status_code == 409
