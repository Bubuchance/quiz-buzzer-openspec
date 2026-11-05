"""搶答活動的狀態、規則與角色視圖。

這個模組不碰網路，所有規則都能用單元測試直接驗證。
整個服務只有一場活動；所有修改都在同一把鎖內完成，確保同時送出時有確定的先後。
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from app.guided_notes import BlankKey, Question, parse_guided_notes

MIN_GROUPS, MAX_GROUPS, DEFAULT_GROUPS = 1, 20, 4
MIN_WINDOW, MAX_WINDOW, DEFAULT_WINDOW = 1, 30, 3
MAX_NAME_LENGTH = 20
MAX_ANSWER_LENGTH = 500


class Phase(str, Enum):
    NO_QUESTIONS = "no_questions"
    READY = "ready"
    OPEN = "open"
    CLOSED = "closed"


PHASE_LABELS = {
    Phase.NO_QUESTIONS: "未匯入",
    Phase.READY: "等待開始",
    Phase.OPEN: "搶答中",
    Phase.CLOSED: "已結束",
}


class ActivityError(Exception):
    """違反規則時拋出；status 對應 HTTP 狀態碼，message 直接顯示給使用者。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Identity:
    token: str
    role: str  # "teacher" 或 "student"
    name: str
    group: int | None = None


@dataclass
class Submission:
    group: int
    number: int
    answers: list[str]
    student: str
    seq: int
    at: float  # 伺服器 monotonic 時間
    elapsed: float  # 距離開啟搶答的秒數


def group_name(group: int) -> str:
    return f"第 {group} 組"


@dataclass
class Activity:
    teacher_passcode: str
    clock: Callable[[], float] = time.monotonic
    questions: list[Question] = field(default_factory=list)
    source_bytes: bytes | None = None
    source_name: str = ""
    group_count: int = DEFAULT_GROUPS
    fair_mode: bool = False
    fair_window: int = DEFAULT_WINDOW
    phase: Phase = Phase.NO_QUESTIONS
    submissions: dict[int, list[Submission]] = field(default_factory=dict)
    opened_at: float | None = None
    identities: dict[str, Identity] = field(default_factory=dict)
    version: int = 0  # 每次狀態改變 +1，方便前端與測試判斷是否有更新
    _seq: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ---------- 身分 ----------

    def login_teacher(self, passcode: str) -> Identity:
        if not passcode or not secrets.compare_digest(passcode.encode(), self.teacher_passcode.encode()):
            raise ActivityError("通行碼錯誤", 401)
        return self._new_identity("teacher", "老師")

    def join_student(self, name: str, group: int) -> Identity:
        name = (name or "").strip()
        if not name:
            raise ActivityError("請輸入名字")
        if len(name) > MAX_NAME_LENGTH:
            raise ActivityError(f"名字最多 {MAX_NAME_LENGTH} 個字")
        with self._lock:
            if not isinstance(group, int) or not MIN_GROUPS <= group <= self.group_count:
                raise ActivityError("組別不存在")
            identity = self._new_identity("student", name, group)
            self._touch()
            return identity

    def _new_identity(self, role: str, name: str, group: int | None = None) -> Identity:
        identity = Identity(secrets.token_urlsafe(24), role, name, group)
        with self._lock:
            self.identities[identity.token] = identity
        return identity

    def identity(self, token: str | None) -> Identity | None:
        return self.identities.get(token or "")

    # ---------- 老師操作 ----------

    def import_notes(self, data: bytes, source_name: str) -> None:
        questions = parse_guided_notes(data)  # 格式錯誤會拋出 GuidedNotesError，原題目不變
        with self._lock:
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答進行中不能匯入，請先結束搶答", 409)
            self.questions = questions
            self.source_bytes = data
            self.source_name = source_name or "guided-notes.xlsx"
            self._clear_submissions()
            self.phase = Phase.READY
            self._touch()

    def update_settings(self, group_count: int | None = None, fair_mode: bool | None = None,
                        fair_window: int | None = None) -> None:
        with self._lock:
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答進行中不能修改設定，請先結束搶答", 409)
            if group_count is not None and not (isinstance(group_count, int) and MIN_GROUPS <= group_count <= MAX_GROUPS):
                raise ActivityError(f"組數需介於 {MIN_GROUPS} 到 {MAX_GROUPS}")
            if fair_window is not None and not (isinstance(fair_window, int) and MIN_WINDOW <= fair_window <= MAX_WINDOW):
                raise ActivityError(f"時間窗需介於 {MIN_WINDOW} 到 {MAX_WINDOW} 秒")
            if group_count is not None:
                self.group_count = group_count
            if fair_mode is not None:
                self.fair_mode = bool(fair_mode)
            if fair_window is not None:
                self.fair_window = fair_window
            self._touch()

    def open(self) -> None:
        with self._lock:
            if self.phase == Phase.NO_QUESTIONS:
                raise ActivityError("請先匯入 Guided Notes 題目", 409)
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答已經在進行中", 409)
            if self.phase == Phase.CLOSED:
                raise ActivityError("本輪已結束，請先按「重設」再開始新一輪", 409)
            self.phase = Phase.OPEN
            self.opened_at = self.clock()
            self._touch()

    def close(self) -> None:
        with self._lock:
            if self.phase != Phase.OPEN:
                raise ActivityError("目前沒有進行中的搶答", 409)
            self.phase = Phase.CLOSED
            self._touch()

    def reset(self) -> None:
        with self._lock:
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答進行中不能重設，請先結束搶答", 409)
            if self.phase == Phase.NO_QUESTIONS:
                raise ActivityError("尚未匯入題目", 409)
            self._clear_submissions()
            self.phase = Phase.READY
            self._touch()

    # ---------- 學生操作 ----------

    def submit(self, identity: Identity, number: int, answers: list[str]) -> Submission:
        with self._lock:
            if self.phase != Phase.OPEN:
                raise ActivityError("目前不在搶答中", 409)
            if identity.group is None or not MIN_GROUPS <= identity.group <= self.group_count:
                raise ActivityError("你的組別已不存在，請重新加入", 409)
            question = self.question(number)
            if question is None:
                raise ActivityError("題號不存在", 404)
            expected = max(question.sub_count, 1)
            if not isinstance(answers, list) or len(answers) != expected:
                raise ActivityError(f"此題需要填寫 {expected} 個答案")
            cleaned = [str(a).strip() for a in answers]
            if any(not a for a in cleaned):
                raise ActivityError("題組需填完所有小題" if question.is_group else "答案不可空白")
            if any(len(a) > MAX_ANSWER_LENGTH for a in cleaned):
                raise ActivityError(f"每個答案最多 {MAX_ANSWER_LENGTH} 字")
            existing = self.submissions.setdefault(number, [])
            if any(s.group == identity.group for s in existing):
                raise ActivityError("本組已送出此題", 409)
            now = self.clock()
            self._seq += 1
            submission = Submission(identity.group, number, cleaned, identity.name, self._seq, now,
                                    round(now - (self.opened_at or now), 3))
            existing.append(submission)
            self._touch()
            return submission

    # ---------- 查詢與判定 ----------

    def question(self, number: int) -> Question | None:
        return next((q for q in self.questions if q.number == number), None)

    def winners(self) -> dict[int, Submission]:
        """回傳每題的搶答成功送出。純計算，每次依送出紀錄重算。"""
        with self._lock:
            return compute_winners(self.submissions, self.fair_mode, self.fair_window)

    def export_answers(self) -> dict[BlankKey, str]:
        answers: dict[BlankKey, str] = {}
        for number, sub in self.winners().items():
            question = self.question(number)
            if question is None:
                continue
            for key, answer in zip(question.blank_keys(), sub.answers):
                answers[key] = answer
        return answers

    def members(self) -> dict[int, list[str]]:
        result: dict[int, list[str]] = {g: [] for g in range(1, self.group_count + 1)}
        for ident in self.identities.values():
            if ident.role == "student" and ident.group in result:
                result[ident.group].append(ident.name)
        return result

    # ---------- 內部 ----------

    def _clear_submissions(self) -> None:
        self.submissions = {}
        self.opened_at = None
        self._seq = 0

    def _touch(self) -> None:
        self.version += 1


def compute_winners(submissions: dict[int, list[Submission]], fair_mode: bool,
                    fair_window: float) -> dict[int, Submission]:
    """一般模式：每題最早送出者成功。

    公平模式：各題依「第一份答案送達時間」先後處理；第一份送達後 fair_window 秒內
    送達的組別為候選，候選中目前成功題數最少者成功，同數取較早送出者。
    """
    ordered = {n: sorted(subs, key=lambda s: s.seq) for n, subs in submissions.items() if subs}
    if not fair_mode:
        return {n: subs[0] for n, subs in ordered.items()}

    wins: dict[int, int] = {}
    result: dict[int, Submission] = {}
    for number in sorted(ordered, key=lambda n: ordered[n][0].seq):
        subs = ordered[number]
        deadline = subs[0].at + fair_window
        candidates = [s for s in subs if s.at <= deadline]
        winner = min(candidates, key=lambda s: (wins.get(s.group, 0), s.seq))
        wins[winner.group] = wins.get(winner.group, 0) + 1
        result[number] = winner
    return result
