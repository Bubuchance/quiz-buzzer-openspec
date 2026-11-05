import csv
from io import BytesIO, StringIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from samples.make_samples import group_workbook, moved_workbook, single_workbook

from app.main import create_app

PASS = "246810"


@pytest.fixture
def client():
    xlsx = moved_workbook()
    app = create_app(PASS, fetch=lambda url: xlsx)
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


def upload(client, token, data=None, name="notes.xlsx"):
    return client.post("/api/teacher/import/file", headers=auth(token),
                       files={"file": (name, data or group_workbook())})


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
    assert client.get(f"/api/teacher/export/guided-notes?token={s}").status_code == 403
    assert client.post("/api/student/submit", headers=auth(t), json={"number": 1, "answers": ["x"]}).status_code == 403
    assert client.post("/api/student/submit", json={"number": 1, "answers": ["x"]}).status_code == 401


def test_chinese_filename_upload_and_download_name(client):
    t = teacher(client)
    assert upload(client, t, name="第五章學習單.xlsx").status_code == 200
    r = client.get("/api/teacher/export/csv", headers=auth(t))
    assert "%E7%AC%AC%E4%BA%94%E7%AB%A0" in r.headers["content-disposition"]  # 第五章


def test_import_errors_and_url(client):
    t = teacher(client)
    r = upload(client, t, b"not xlsx")
    assert r.status_code == 400 and "不是有效的" in r.json()["detail"]
    r = client.post("/api/teacher/import/url", headers=auth(t), json={"url": "https://example.com/x"})
    assert r.status_code == 400
    r = client.post("/api/teacher/import/url", headers=auth(t),
                    json={"url": "https://docs.google.com/spreadsheets/d/ABC/edit"})
    assert r.status_code == 200 and r.json()["question_count"] == 3


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

    r = client.get(f"/api/teacher/export/guided-notes?token={t}")
    assert r.status_code == 200 and "filename*=UTF-8''" in r.headers["content-disposition"]
    ws = load_workbook(BytesIO(r.content)).active
    values = [c.value for row in ws.iter_rows() for c in row if c.value]
    assert "描述物件之間訊息傳遞先後順序的圖是 循序圖。" in values
    assert "題組：類別圖中，空心菱形代表 聚合，實心菱形代表 組合。" in values
    assert "描述系統由哪些元件組成的圖是 {{2}}。" in values

    r = client.get("/api/teacher/export/csv", headers=auth(t))
    rows = list(csv.reader(StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "題號" and len(rows) == 1 + 2 + 2


def test_settings_api(client):
    t = teacher(client)
    assert client.post("/api/teacher/settings", headers=auth(t), json={"group_count": 6}).status_code == 200
    assert client.get("/api/groups").json()["groups"][-1] == 6
    r = client.post("/api/teacher/settings", headers=auth(t), json={"fair_window": 31})
    assert r.status_code == 400


def test_export_before_import(client):
    t = teacher(client)
    assert client.get("/api/teacher/export/guided-notes", headers=auth(t)).status_code == 409
    assert client.get("/api/teacher/export/csv", headers=auth(t)).status_code == 409


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
