import csv
from io import StringIO

import pytest

from app.activity import Activity, ActivityError, Phase
from app.guided_notes import GuidedNotesError
from app.reporting import CSV_HEADER, build_results, results_csv, view_for
from samples.make_samples import group_workbook, single_workbook


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def act(clock):
    a = Activity(teacher_passcode="123456", clock=clock, wall_clock=lambda: 1_763_366_405.123)
    a.import_notes(group_workbook(), "uml.xlsx")  # 1,2,4 單題；3 題組(2)；5 題組(3)
    return a


def students(act, *groups):
    return [act.join_student(f"學生{g}", g) for g in groups]


# --- 身分 ---

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
    assert a.token != b.token and act.identity(a.token) is a and act.identity("nope") is None


# --- 2.1 階段 ---

def test_phase_labels_three_stages(clock):
    a = Activity(teacher_passcode="x", clock=clock)
    t = a.login_teacher("x")
    assert view_for(a, t)["phase_label"] == "準備中" and not view_for(a, t)["has_questions"]
    a.import_notes(single_workbook(), "s.xlsx")
    assert view_for(a, t)["phase_label"] == "準備中"
    a.open()
    assert view_for(a, t)["phase_label"] == "搶答中"
    a.close()
    assert view_for(a, t)["phase_label"] == "已結束"


def test_phase_flow(clock):
    a = Activity(teacher_passcode="x", clock=clock)
    with pytest.raises(ActivityError, match="先匯入"):
        a.open()
    a.import_notes(single_workbook(), "s.xlsx")
    a.open()
    with pytest.raises(ActivityError):
        a.open()
    with pytest.raises(ActivityError, match="不能匯入"):
        a.import_notes(single_workbook(), "s.xlsx")
    with pytest.raises(ActivityError, match="不能重設"):
        a.reset()
    a.close()
    with pytest.raises(ActivityError, match="重設"):
        a.open()
    with pytest.raises(ActivityError):
        a.close()


def test_reset_and_reimport_clear_submissions_and_marks(act):
    (s1,) = students(act, 1)
    act.open()
    act.submit(s1, 1, ["循序圖"])
    act.close()
    act.mark(1, "correct")
    act.reset()
    assert act.phase == Phase.READY and act.submissions == {} and act.marks == {} and len(act.questions) == 5
    act.open()
    act.submit(s1, 1, ["a"])
    act.close()
    act.mark(1, "wrong")
    act.import_notes(single_workbook(), "s.xlsx")
    assert act.submissions == {} and act.marks == {}


def test_failed_import_keeps_old_questions(act):
    with pytest.raises(GuidedNotesError):
        act.import_notes(b"bad", "bad.xlsx")
    assert len(act.questions) == 5 and act.source_name == "uml.xlsx"


# --- 設定 ---

def test_settings_ranges(act):
    act.update_settings(group_count=6, fair_mode=True, fair_delay=5, time_limit=60)
    assert (act.group_count, act.fair_mode, act.fair_delay, act.time_limit) == (6, True, 5, 60)
    for kwargs in [{"group_count": 0}, {"group_count": 21}, {"fair_delay": 0}, {"fair_delay": 31},
                   {"time_limit": -1}, {"time_limit": 3601}]:
        with pytest.raises(ActivityError):
            act.update_settings(**kwargs)
    assert (act.group_count, act.fair_delay, act.time_limit) == (6, 5, 60)
    act.update_settings(time_limit=0)
    assert act.time_limit == 0
    act.open()
    with pytest.raises(ActivityError, match="不能修改設定"):
        act.update_settings(group_count=3)


def test_defaults(clock):
    a = Activity(teacher_passcode="x", clock=clock)
    assert (a.group_count, a.fair_mode, a.fair_delay, a.time_limit) == (4, False, 3, 0)


# --- 送出 ---

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


# --- 判定 ---

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


def _fair_setup(act, clock, second_at):
    """第 1 組先拿下第 2、4 題；開啟後第 10 秒第 1 組送第 1 題，第 second_at 秒第 2 組送。"""
    act.update_settings(fair_mode=True, fair_delay=3)
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s1, 2, ["元件圖"])
    act.submit(s1, 4, ["使用案例"])
    clock.advance(10)
    first = act.submit(s1, 1, ["循序圖"])
    clock.advance(second_at - 10)
    second = act.submit(s2, 1, ["循序圖"])
    return first, second


def test_fair_mode_delays_group_with_more_wins(act, clock):
    first, second = _fair_setup(act, clock, 15)
    assert (first.prior_wins, second.prior_wins) == (2, 0)
    assert act.winners()[1].group == 2
    q1 = build_results(act)["questions"][0]
    assert [(s["group"], s["rank"], s["effective"]) for s in q1["submissions"]] == [(2, 1, 15.0), (1, 2, 16.0)]


def test_fair_mode_still_faster_after_delay(act, clock):
    _fair_setup(act, clock, 17)
    assert act.winners()[1].group == 1


def test_fair_mode_off_uses_receive_time(act, clock):
    _fair_setup(act, clock, 15)
    act.close()
    act.update_settings(fair_mode=False)
    assert act.winners()[1].group == 1


def test_prior_wins_counted_at_receive_time(act, clock):
    act.update_settings(fair_mode=True, fair_delay=3)
    s1, s2 = students(act, 1, 2)
    act.open()
    a = act.submit(s1, 1, ["a"])  # 第 1 組 0 題
    b = act.submit(s1, 2, ["b"])  # 此時第 1 組暫定已成功 1 題
    c = act.submit(s2, 2, ["c"])
    assert (a.prior_wins, b.prior_wins, c.prior_wins) == (0, 1, 0)


# --- 2.3 倒數計時 ---

def test_countdown_expires(act, clock):
    act.update_settings(time_limit=60)
    (s1,) = students(act, 1)
    round_id = act.open()
    assert act.remaining_seconds() == 60
    clock.advance(15)
    assert act.remaining_seconds() == 45
    assert view_for(act, s1)["remaining_seconds"] == 45
    clock.advance(45)
    with pytest.raises(ActivityError, match="時間已到"):
        act.submit(s1, 1, ["太晚"])
    assert act.phase == Phase.CLOSED and act.submissions.get(1, []) == []
    assert act.expire(round_id) is False  # 已結束，再呼叫不做事


def test_countdown_timer_callback(act, clock):
    act.update_settings(time_limit=30)
    round_id = act.open()
    assert act.expire_if_due() is False
    clock.advance(30)
    assert act.expire(round_id) is True and act.phase == Phase.CLOSED and act.remaining_seconds() is None


def test_manual_close_cancels_old_round(act, clock):
    act.update_settings(time_limit=60)
    old_round = act.open()
    clock.advance(20)
    act.close()
    act.reset()
    act.open()
    clock.advance(40)
    assert act.expire(old_round) is False and act.phase == Phase.OPEN


def test_no_time_limit(act):
    act.open()
    assert act.remaining_seconds() is None and act.expire_if_due() is False


# --- 3.1 標記與計分板 ---

def test_marking_rules_and_scoreboard(act):
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s1, 1, ["a"])
    act.submit(s2, 2, ["b"])
    act.submit(s2, 4, ["c"])
    with pytest.raises(ActivityError, match="結束後才能標記"):
        act.mark(1, "correct")
    act.close()
    board = build_results(act)["scoreboard"]
    assert [(r["group"], r["score"], r["wins"]) for r in board[:3]] == [(2, 0, 2), (1, 0, 1), (3, 0, 0)]
    act.mark(1, "correct")
    act.mark(2, "correct")
    act.mark(4, "wrong")
    board = build_results(act)["scoreboard"]
    assert [(r["group"], r["score"], r["wins"]) for r in board[:2]] == [(2, 1, 2), (1, 1, 1)]
    act.mark(2, "wrong")
    board = build_results(act)["scoreboard"]
    assert [(r["group"], r["score"]) for r in board[:2]] == [(1, 1), (2, 0)]
    act.mark(1, None)
    assert 1 not in act.marks
    assert build_results(act)["questions"][3]["mark"] == "wrong"
    with pytest.raises(ActivityError, match="無人搶答"):
        act.mark(3, "correct")
    with pytest.raises(ActivityError, match="對"):
        act.mark(2, "maybe")
    with pytest.raises(ActivityError, match="題號不存在"):
        act.mark(99, "correct")


# --- 3.3 學生視圖 ---

def test_student_view_hides_other_groups_until_closed(act):
    teacher = act.login_teacher("123456")
    s1, s1b, s2 = act.join_student("甲", 1), act.join_student("乙", 1), act.join_student("丙", 2)
    act.open()
    act.submit(s2, 1, ["第二組的秘密答案"])
    act.submit(s2, 4, ["x"])
    act.submit(s1, 2, ["元件圖"])

    v1 = view_for(act, s1b)
    text = repr(v1)
    assert "第二組的秘密答案" not in text and "results" not in v1 and "丙" not in text
    assert v1["my_submissions"] == {"2": {"answers": ["元件圖"], "student": "甲"}}
    assert v1["progress"] == {"submitted": 1, "total": 5}
    assert view_for(act, s2)["progress"] == {"submitted": 2, "total": 5}
    assert "locations" not in v1["questions"][0]

    vt = view_for(act, teacher)
    assert vt["results"]["questions"][0]["winner"]["group"] == 2 and vt["questions"][0]["locations"]

    act.close()
    v1_closed = view_for(act, s1)
    assert v1_closed["phase_label"] == "已結束"
    assert v1_closed["results"]["questions"][0]["winner"]["answers"] == ["第二組的秘密答案"]


# --- 3.2 CSV ---

def test_csv_columns_and_rows(act, clock):
    s1, s2 = students(act, 1, 2)
    act.open()
    act.submit(s1, 3, ["聚合", "組合"])
    act.submit(s2, 3, ["x", "y"])
    act.submit(s2, 1, ["循序圖"])
    text = results_csv(act)
    assert text.startswith("﻿")
    rows = list(csv.reader(StringIO(text.lstrip("﻿"))))
    assert rows[0] == CSV_HEADER == ["題號", "組別", "答案", "搶答順位", "是否搶答成功", "送出時間"]
    assert rows[1][:5] == ["1", "第 2 組", "循序圖", "1", "是"]
    assert rows[2][:5] == ["3", "第 1 組", "（1）聚合（2）組合", "1", "是"]
    assert rows[3][:5] == ["3", "第 2 組", "（1）x（2）y", "2", "否"]
    assert len(rows) == 4
    assert len(rows[1][5]) == len("2025-11-17 15:20:05.123") and rows[1][5].endswith(".123")


def test_export_answers_maps_group_items(act):
    (s1,) = students(act, 1)
    act.open()
    act.submit(s1, 5, ["單一職責", "開放封閉", "里氏替換"])
    act.submit(s1, 1, ["循序圖"])
    assert act.export_answers() == {(1, None): "循序圖", (5, 1): "單一職責", (5, 2): "開放封閉", (5, 3): "里氏替換"}
