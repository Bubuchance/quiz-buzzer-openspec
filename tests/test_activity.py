import csv
from io import StringIO

import pytest

from app.activity import Activity, ActivityError, Phase
from app.reporting import build_results, results_csv, view_for
from samples.make_samples import group_workbook, single_workbook


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def act(clock):
    a = Activity(teacher_passcode="123456", clock=clock)
    a.import_notes(group_workbook(), "uml.xlsx")  # 1,2,4 單題；3 題組(2)；5 題組(3)
    return a


def students(act, *groups):
    return [act.join_student(f"學生{g}", g) for g in groups]


# --- 4.1 身分 ---

def test_teacher_login(act):
    assert act.login_teacher("123456").role == "teacher"
    for bad in ["", "000000", "1234567"]:
        with pytest.raises(ActivityError, match="通行碼錯誤"):
            act.login_teacher(bad)


def test_student_join_rules(act):
    s = act.join_student("  小明 ", 2)
    assert (s.role, s.name, s.group) == ("student", "小明", 2)
    with pytest.raises(ActivityError, match="請輸入名字"):
        act.join_student("   ", 1)
    with pytest.raises(ActivityError, match="組別不存在"):
        act.join_student("x", 5)
    with pytest.raises(ActivityError, match="最多"):
        act.join_student("x" * 21, 1)


def test_tokens_are_unique_and_resolvable(act):
    a, b = students(act, 1, 1)
    assert a.token != b.token
    assert act.identity(a.token) is a
    assert act.identity("nope") is None


# --- 3.1 階段 ---

def test_phase_flow(clock):
    a = Activity(teacher_passcode="x", clock=clock)
    assert a.phase == Phase.NO_QUESTIONS
    with pytest.raises(ActivityError, match="先匯入"):
        a.open()
    a.import_notes(single_workbook(), "s.xlsx")
    assert a.phase == Phase.READY
    a.open()
    assert a.phase == Phase.OPEN
    with pytest.raises(ActivityError):
        a.open()
    with pytest.raises(ActivityError, match="不能匯入"):
        a.import_notes(single_workbook(), "s.xlsx")
    with pytest.raises(ActivityError, match="不能重設"):
        a.reset()
    a.close()
    assert a.phase == Phase.CLOSED
    with pytest.raises(ActivityError, match="重設"):
        a.open()
    with pytest.raises(ActivityError):
        a.close()


def test_reset_clears_submissions_keeps_questions(act):
    (s1,) = students(act, 1)
    act.open()
    act.submit(s1, 1, ["循序圖"])
    act.close()
    act.reset()
    assert act.phase == Phase.READY and act.submissions == {} and len(act.questions) == 5


def test_reimport_clears_submissions(act):
    (s1,) = students(act, 1)
    act.open()
    act.submit(s1, 1, ["a"])
    act.close()
    act.import_notes(single_workbook(), "s.xlsx")
    assert act.phase == Phase.READY and act.submissions == {}


def test_failed_import_keeps_old_questions(act):
    from app.guided_notes import GuidedNotesError
    with pytest.raises(GuidedNotesError):
        act.import_notes(b"bad", "bad.xlsx")
    assert len(act.questions) == 5 and act.source_name == "uml.xlsx"


# --- 3.2 設定 ---

def test_settings_ranges(act):
    act.update_settings(group_count=6, fair_mode=True, fair_window=5)
    assert (act.group_count, act.fair_mode, act.fair_window) == (6, True, 5)
    for kwargs in [{"group_count": 0}, {"group_count": 21}, {"fair_window": 0}, {"fair_window": 31}]:
        with pytest.raises(ActivityError):
            act.update_settings(**kwargs)
    assert (act.group_count, act.fair_window) == (6, 5)
    act.open()
    with pytest.raises(ActivityError, match="不能修改設定"):
        act.update_settings(group_count=3)


# --- 3.3 送出 ---

def test_submit_rules(act):
    s1, s1b, s2 = act.join_student("甲", 1), act.join_student("乙", 1), act.join_student("丙", 2)
    with pytest.raises(ActivityError, match="不在搶答中"):
        act.submit(s1, 1, ["x"])
    act.open()
    with pytest.raises(ActivityError, match="答案不可空白"):
        act.submit(s1, 1, ["   "])
    with pytest.raises(ActivityError, match="填完所有小題"):
        act.submit(s1, 3, ["空心", ""])
    with pytest.raises(ActivityError, match="2 個答案"):
        act.submit(s1, 3, ["只有一個"])
    with pytest.raises(ActivityError, match="題號不存在"):
        act.submit(s1, 99, ["x"])
    sub = act.submit(s1, 1, ["  循序圖 "])
    assert sub.answers == ["循序圖"] and sub.seq == 1
    with pytest.raises(ActivityError, match="本組已送出"):
        act.submit(s1b, 1, ["別的答案"])
    assert act.submissions[1][0].answers == ["循序圖"]
    act.submit(s2, 3, ["聚合", "組合"])
    act.close()
    with pytest.raises(ActivityError, match="不在搶答中"):
        act.submit(s2, 2, ["x"])


def test_student_in_removed_group_cannot_submit(act):
    (s4,) = students(act, 4)
    act.update_settings(group_count=2)
    act.open()
    with pytest.raises(ActivityError, match="組別已不存在"):
        act.submit(s4, 1, ["x"])


# --- 3.4 判定 ---

def test_first_submission_wins(act, clock):
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s2, 1, ["B"])
    clock.advance(0.5)
    act.submit(s1, 1, ["A"])
    assert act.winners()[1].group == 2
    q1 = build_results(act)["questions"][0]
    assert [(s["group"], s["rank"], s["success"]) for s in q1["submissions"]] == [(2, 1, True), (1, 2, False)]
    assert build_results(act)["questions"][1]["winner"] is None


def test_fair_mode_prefers_group_with_fewer_wins(act, clock):
    act.update_settings(fair_mode=True, fair_window=3)
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s1, 2, ["元件圖"])  # 第 1 組先拿下第 2、4 題
    act.submit(s1, 4, ["使用案例"])
    clock.advance(10)
    act.submit(s1, 1, ["循序圖"])
    clock.advance(1)  # 1 秒後，在時間窗內
    act.submit(s2, 1, ["循序圖"])
    winners = act.winners()
    assert winners[1].group == 2
    q1 = build_results(act)["questions"][0]
    assert [(s["group"], s["rank"]) for s in q1["submissions"]] == [(1, 1), (2, 2)]


def test_fair_mode_outside_window_keeps_fastest(act, clock):
    act.update_settings(fair_mode=True, fair_window=3)
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s1, 2, ["x"])
    act.submit(s1, 4, ["x"])
    act.submit(s1, 1, ["循序圖"])
    clock.advance(5)
    act.submit(s2, 1, ["循序圖"])
    assert act.winners()[1].group == 1


def test_fair_mode_tie_uses_time(act, clock):
    act.update_settings(fair_mode=True, fair_window=3)
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s2, 1, ["b"])
    clock.advance(1)
    act.submit(s1, 1, ["a"])
    assert act.winners()[1].group == 2


# --- 4.2 角色視圖 ---

def test_student_view_hides_other_groups_until_closed(act):
    teacher = act.login_teacher("123456")
    s1, s1b, s2 = act.join_student("甲", 1), act.join_student("乙", 1), act.join_student("丙", 2)
    act.open()
    act.submit(s2, 1, ["第二組的秘密答案"])
    act.submit(s1, 2, ["元件圖"])

    v1 = view_for(act, s1b)
    text = repr(v1)
    assert "第二組的秘密答案" not in text and "results" not in v1 and "丙" not in text
    assert v1["my_submissions"] == {"2": {"answers": ["元件圖"], "student": "甲"}}
    assert "locations" not in v1["questions"][0]

    vt = view_for(act, teacher)
    assert vt["results"]["questions"][0]["winner"]["group"] == 2
    assert vt["questions"][0]["locations"]

    act.close()
    v1_closed = view_for(act, s1)
    assert v1_closed["phase_label"] == "已結束"
    assert v1_closed["results"]["questions"][0]["winner"]["answers"] == ["第二組的秘密答案"]


# --- 5.1 結果與 CSV ---

def test_scoreboard_sorted_by_wins(act):
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s1, 1, ["a"])
    act.submit(s2, 2, ["b"])
    act.submit(s2, 4, ["c"])
    board = build_results(act)["scoreboard"]
    assert [(r["group"], r["wins"]) for r in board[:3]] == [(2, 2), (1, 1), (3, 0)]


def test_csv_columns_and_group_rows(act, clock):
    s1, s2 = students(act, 1, 2)
    act.open()
    clock.advance(2.5)
    act.submit(s1, 3, ["聚合", "組合"])
    act.submit(s2, 3, ["x", "y"])
    act.submit(s2, 1, ["循序圖"])
    text = results_csv(act)
    assert text.startswith("﻿")
    rows = list(csv.reader(StringIO(text.lstrip("﻿"))))
    assert rows[0] == ["題號", "小題", "組別", "答案", "搶答順位", "是否成功", "送出秒數"]
    assert ["1", "", "第 2 組", "循序圖", "1", "是", "2.500"] in rows
    assert ["3", "1", "第 1 組", "聚合", "1", "是", "2.500"] in rows
    assert ["3", "2", "第 1 組", "組合", "1", "是", "2.500"] in rows
    assert ["3", "2", "第 2 組", "y", "2", "否", "2.500"] in rows
    assert len(rows) == 1 + 1 + 2 + 2


def test_export_answers_maps_group_items(act):
    s1, = students(act, 1)
    act.open()
    act.submit(s1, 5, ["單一職責", "開放封閉", "里氏替換"])
    act.submit(s1, 1, ["循序圖"])
    assert act.export_answers() == {(1, None): "循序圖", (5, 1): "單一職責", (5, 2): "開放封閉", (5, 3): "里氏替換"}
