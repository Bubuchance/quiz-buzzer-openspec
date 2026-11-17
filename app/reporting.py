"""結果彙整、角色視圖與 CSV 匯出。"""
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

from app.activity import PHASE_LABELS, Activity, Identity, Phase, group_name

CSV_HEADER = ["題號", "組別", "答案", "搶答順位", "是否搶答成功", "送出時間"]


def build_results(activity: Activity) -> dict:
    """每題結果（含順位、成功組別、對錯標記）以及計分板。"""
    ranked = activity.ranked()
    questions = []
    wins = {g: 0 for g in range(1, activity.group_count + 1)}
    scores = {g: 0 for g in range(1, activity.group_count + 1)}
    for q in activity.questions:
        subs = ranked.get(q.number, [])
        winner = subs[0] if subs else None
        mark = activity.marks.get(q.number) if winner else None
        if winner is not None:
            wins[winner.group] = wins.get(winner.group, 0) + 1
            scores.setdefault(winner.group, 0)
            if mark == "correct":
                scores[winner.group] += 1
        questions.append({
            "number": q.number,
            "sub_count": q.sub_count,
            "mark": mark,
            "winner": None if winner is None else {
                "group": winner.group, "group_name": group_name(winner.group),
                "answers": winner.answers, "student": winner.student,
            },
            "submissions": [
                {
                    "group": s.group, "group_name": group_name(s.group), "answers": s.answers,
                    "student": s.student, "rank": rank, "elapsed": s.elapsed,
                    "effective": round(activity.effective_time(s) - (activity.opened_at or s.at), 3),
                    "delayed": activity.fair_mode and s.prior_wins > 0,
                    "success": rank == 1,
                }
                for rank, s in enumerate(subs, start=1)
            ],
        })
    scoreboard = sorted(
        ({"group": g, "group_name": group_name(g), "score": scores.get(g, 0), "wins": n} for g, n in wins.items()),
        key=lambda row: (-row["score"], -row["wins"], row["group"]),
    )
    return {"questions": questions, "scoreboard": scoreboard}


def view_for(activity: Activity, identity: Identity) -> dict:
    """依角色過濾後的完整狀態快照（WebSocket 推送內容）。

    學生在「已結束」之前只會拿到自己組別的送出紀錄與進度，
    不包含其他組的答案、送出與否、數量、順位或暫定成功組別。
    """
    with activity._lock:
        is_teacher = identity.role == "teacher"
        view = {
            "version": activity.version,
            "phase": activity.phase.value,
            "phase_label": PHASE_LABELS[activity.phase],
            "has_questions": bool(activity.questions),
            "group_count": activity.group_count,
            "groups": [{"group": g, "group_name": group_name(g)} for g in range(1, activity.group_count + 1)],
            "fair_mode": activity.fair_mode,
            "fair_delay": activity.fair_delay,
            "time_limit": activity.time_limit,
            "remaining_seconds": activity.remaining_seconds(),
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

        mine = {
            str(s.number): {"answers": s.answers, "student": s.student}
            for subs in activity.submissions.values() for s in subs if s.group == identity.group
        }
        view["group_valid"] = identity.group is not None and identity.group <= activity.group_count
        view["my_submissions"] = mine
        view["progress"] = {"submitted": len(mine), "total": len(activity.questions)}
        if activity.phase == Phase.CLOSED:
            view["results"] = build_results(activity)
        return view


def format_answers(sub_count: int, answers: list[str]) -> str:
    if not sub_count:
        return answers[0]
    return "".join(f"（{i}）{a}" for i, a in enumerate(answers, start=1))


def format_wall_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def results_csv(activity: Activity) -> str:
    """UTF-8 含 BOM 的 CSV，Excel 可直接開啟中文；每筆送出一列。"""
    ranked = activity.ranked()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for q in activity.questions:
        for rank, s in enumerate(ranked.get(q.number, []), start=1):
            writer.writerow([
                q.number, group_name(s.group), format_answers(q.sub_count, s.answers),
                rank, "是" if rank == 1 else "否", format_wall_time(s.wall),
            ])
    return "﻿" + buffer.getvalue()
