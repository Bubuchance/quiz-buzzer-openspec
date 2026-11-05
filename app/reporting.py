"""結果彙整、角色視圖與 CSV 匯出。"""
from __future__ import annotations

import csv
from io import StringIO

from app.activity import PHASE_LABELS, Activity, Identity, Phase, group_name

CSV_HEADER = ["題號", "小題", "組別", "答案", "搶答順位", "是否成功", "送出秒數"]


def build_results(activity: Activity) -> dict:
    """每題結果（含順位與成功組別）以及各組成功題數。"""
    winners = activity.winners()
    questions = []
    wins = {g: 0 for g in range(1, activity.group_count + 1)}
    for q in activity.questions:
        subs = sorted(activity.submissions.get(q.number, []), key=lambda s: s.seq)
        winner = winners.get(q.number)
        if winner is not None:
            wins[winner.group] = wins.get(winner.group, 0) + 1
        questions.append({
            "number": q.number,
            "sub_count": q.sub_count,
            "winner": None if winner is None else {
                "group": winner.group, "group_name": group_name(winner.group),
                "answers": winner.answers, "student": winner.student,
            },
            "submissions": [
                {
                    "group": s.group, "group_name": group_name(s.group), "answers": s.answers,
                    "student": s.student, "rank": rank, "elapsed": s.elapsed,
                    "success": winner is not None and s.seq == winner.seq,
                }
                for rank, s in enumerate(subs, start=1)
            ],
        })
    scoreboard = sorted(
        ({"group": g, "group_name": group_name(g), "wins": n} for g, n in wins.items()),
        key=lambda row: (-row["wins"], row["group"]),
    )
    return {"questions": questions, "scoreboard": scoreboard}


def view_for(activity: Activity, identity: Identity) -> dict:
    """依角色過濾後的完整狀態快照（WebSocket 推送內容）。

    學生在「已結束」之前只會拿到自己組別的送出紀錄，
    不包含其他組的答案、送出與否、數量、順位或暫定成功組別。
    """
    with activity._lock:
        is_teacher = identity.role == "teacher"
        view = {
            "version": activity.version,
            "phase": activity.phase.value,
            "phase_label": PHASE_LABELS[activity.phase],
            "group_count": activity.group_count,
            "groups": [{"group": g, "group_name": group_name(g)} for g in range(1, activity.group_count + 1)],
            "fair_mode": activity.fair_mode,
            "fair_window": activity.fair_window,
            "source_name": activity.source_name,
            "questions": [
                {"number": q.number, "sub_count": q.sub_count, **({"locations": q.locations} if is_teacher else {})}
                for q in activity.questions
            ],
            "me": {"role": identity.role, "name": identity.name, "group": identity.group,
                   "group_name": group_name(identity.group) if identity.group else None},
        }
        if is_teacher:
            view["results"] = build_results(activity)
            view["members"] = {str(g): names for g, names in activity.members().items()}
            return view

        view["group_valid"] = identity.group is not None and identity.group <= activity.group_count
        view["my_submissions"] = {
            str(s.number): {"answers": s.answers, "student": s.student}
            for subs in activity.submissions.values() for s in subs if s.group == identity.group
        }
        if activity.phase == Phase.CLOSED:
            view["results"] = build_results(activity)
        return view


def results_csv(activity: Activity) -> str:
    """UTF-8 含 BOM 的 CSV，Excel 可直接開啟中文；題組每個小題各一列。"""
    results = build_results(activity)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for q in results["questions"]:
        for s in q["submissions"]:
            for index, answer in enumerate(s["answers"], start=1):
                writer.writerow([
                    q["number"], index if q["sub_count"] else "", s["group_name"], answer,
                    s["rank"], "是" if s["success"] else "否", f"{s['elapsed']:.3f}",
                ])
    return "﻿" + buffer.getvalue()
