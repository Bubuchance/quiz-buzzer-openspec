"""搶答活動的狀態、規則與判定。

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

from app.guided_notes import BlankKey, Question, Spreadsheet, build_writes, parse_spreadsheet

MIN_GROUPS, MAX_GROUPS, DEFAULT_GROUPS = 1, 20, 4
MIN_DELAY, MAX_DELAY, DEFAULT_DELAY = 1, 30, 3
MIN_TIME_LIMIT, MAX_TIME_LIMIT = 0, 3600
MAX_NAME_LENGTH = 20
MAX_ANSWER_LENGTH = 500
MARKS = ("correct", "wrong")


class Phase(str, Enum):
    NO_QUESTIONS = "no_questions"  # 對外也顯示「準備中」
    READY = "ready"
    OPEN = "open"
    CLOSED = "closed"


PHASE_LABELS = {
    Phase.NO_QUESTIONS: "準備中",
    Phase.READY: "準備中",
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
    at: float  # 伺服器 monotonic 時間（判定先後用）
    wall: float  # 牆上時間（CSV 顯示用）
    elapsed: float  # 距離開啟搶答的秒數
    prior_wins: int = 0  # 收到當下該組已搶答成功題數（公平模式用）


def group_name(group: int) -> str:
    return f"第 {group} 組"


@dataclass
class Activity:
    teacher_passcode: str
    clock: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], float] = time.time
    questions: list[Question] = field(default_factory=list)
    sheet_id: str | None = None  # 匯入來源的 Google Sheets 試算表 ID
    source_name: str = ""
    group_count: int = DEFAULT_GROUPS
    fair_mode: bool = False
    fair_delay: int = DEFAULT_DELAY
    time_limit: int = 0  # 秒；0 = 不限時
    phase: Phase = Phase.NO_QUESTIONS
    submissions: dict[int, list[Submission]] = field(default_factory=dict)
    marks: dict[int, str] = field(default_factory=dict)
    opened_at: float | None = None
    deadline: float | None = None
    round_id: int = 0
    identities: dict[str, Identity] = field(default_factory=dict)
    version: int = 0  # 每次狀態改變 +1
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

    def import_notes(self, spreadsheet: Spreadsheet, sheet_id: str) -> None:
        """匯入從雲端 Google Sheets 讀到的內容。"""
        with self._lock:  # 先檢查階段，避免搶答中還去解析
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答進行中不能匯入，請先結束搶答", 409)
        questions = parse_spreadsheet(spreadsheet).questions  # 格式錯誤會拋出 GuidedNotesError，原題目不變
        with self._lock:
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答進行中不能匯入，請先結束搶答", 409)
            self.questions = questions
            self.sheet_id = sheet_id
            self.source_name = spreadsheet.title or "Google Sheets"
            self._clear_round()
            self.phase = Phase.READY
            self._touch()

    def update_settings(self, group_count: int | None = None, fair_mode: bool | None = None,
                        fair_delay: int | None = None, time_limit: int | None = None) -> None:
        def in_range(value, low, high):
            return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high

        with self._lock:
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答進行中不能修改設定，請先結束搶答", 409)
            if group_count is not None and not in_range(group_count, MIN_GROUPS, MAX_GROUPS):
                raise ActivityError(f"組數需介於 {MIN_GROUPS} 到 {MAX_GROUPS}")
            if fair_delay is not None and not in_range(fair_delay, MIN_DELAY, MAX_DELAY):
                raise ActivityError(f"延遲量需介於 {MIN_DELAY} 到 {MAX_DELAY} 秒")
            if time_limit is not None and not in_range(time_limit, MIN_TIME_LIMIT, MAX_TIME_LIMIT):
                raise ActivityError(f"時限需介於 {MIN_TIME_LIMIT} 到 {MAX_TIME_LIMIT} 秒（0 表示不限時）")
            if group_count is not None:
                self.group_count = group_count
            if fair_mode is not None:
                self.fair_mode = bool(fair_mode)
            if fair_delay is not None:
                self.fair_delay = fair_delay
            if time_limit is not None:
                self.time_limit = time_limit
            self._touch()

    def open(self) -> int:
        """開啟搶答，回傳本回合編號（倒數計時用）。"""
        with self._lock:
            if self.phase == Phase.NO_QUESTIONS:
                raise ActivityError("請先匯入 Guided Notes 題目", 409)
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答已經在進行中", 409)
            if self.phase == Phase.CLOSED:
                raise ActivityError("本輪已結束，請先按「重設」再開始新一輪", 409)
            self.phase = Phase.OPEN
            self.opened_at = self.clock()
            self.deadline = self.opened_at + self.time_limit if self.time_limit else None
            self.round_id += 1
            self._touch()
            return self.round_id

    def close(self) -> None:
        with self._lock:
            if self.phase != Phase.OPEN:
                raise ActivityError("目前沒有進行中的搶答", 409)
            self.phase = Phase.CLOSED
            self.deadline = None
            self._touch()

    def expire(self, round_id: int) -> bool:
        """倒數時間到時呼叫；只有同一回合且仍在搶答中才結束。回傳是否有結束。"""
        with self._lock:
            if self.phase != Phase.OPEN or self.round_id != round_id:
                return False
            self.phase = Phase.CLOSED
            self.deadline = None
            self._touch()
            return True

    def expire_if_due(self) -> bool:
        """若已超過時限就自動結束；回傳是否剛結束。"""
        with self._lock:
            if self.phase == Phase.OPEN and self.deadline is not None and self.clock() >= self.deadline:
                return self.expire(self.round_id)
            return False

    def remaining_seconds(self) -> float | None:
        with self._lock:
            if self.phase != Phase.OPEN or self.deadline is None:
                return None
            return max(0.0, round(self.deadline - self.clock(), 3))

    def reset(self) -> None:
        with self._lock:
            if self.phase == Phase.OPEN:
                raise ActivityError("搶答進行中不能重設，請先結束搶答", 409)
            if self.phase == Phase.NO_QUESTIONS:
                raise ActivityError("尚未匯入題目", 409)
            self._clear_round()
            self.phase = Phase.READY
            self._touch()

    def mark(self, number: int, mark: str | None) -> None:
        with self._lock:
            if self.phase != Phase.CLOSED:
                raise ActivityError("搶答結束後才能標記對錯", 409)
            if self.question(number) is None:
                raise ActivityError("題號不存在", 404)
            if mark is not None and mark not in MARKS:
                raise ActivityError("標記只能是「對」或「錯」")
            if number not in self.winners():
                raise ActivityError("此題無人搶答，不能標記", 409)
            if mark is None:
                self.marks.pop(number, None)
            else:
                self.marks[number] = mark
            self._touch()

    # ---------- 學生操作 ----------

    def submit(self, identity: Identity, number: int, answers: list[str]) -> Submission:
        with self._lock:
            if self.expire_if_due():
                raise ActivityError("搶答時間已到", 409)
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
            # 收到當下依公平規則算出的暫定成功題數，之後不再改變
            current = rank_submissions(self.submissions, True, self.fair_delay)
            prior_wins = sum(1 for subs in current.values() if subs and subs[0].group == identity.group)
            now = self.clock()
            self._seq += 1
            submission = Submission(identity.group, number, cleaned, identity.name, self._seq, now,
                                    self.wall_clock(), round(now - (self.opened_at or now), 3), prior_wins)
            existing.append(submission)
            self._touch()
            return submission

    # ---------- 查詢與判定 ----------

    def question(self, number: int) -> Question | None:
        return next((q for q in self.questions if q.number == number), None)

    def ranked(self) -> dict[int, list[Submission]]:
        """每題依順位排序的送出。"""
        with self._lock:
            return rank_submissions(self.submissions, self.fair_mode, self.fair_delay)

    def winners(self) -> dict[int, Submission]:
        return {n: subs[0] for n, subs in self.ranked().items() if subs}

    def effective_time(self, s: Submission) -> float:
        return effective_time(s, self.fair_mode, self.fair_delay)

    def ensure_can_write_back(self) -> str:
        """寫回雲端前的檢查；回傳試算表 ID。"""
        with self._lock:
            if self.sheet_id is None:
                raise ActivityError("尚未匯入 Google Sheets 題目", 409)
            if self.phase != Phase.CLOSED:
                raise ActivityError("搶答結束後才能寫回 Google Sheets", 409)
            return self.sheet_id

    def prepare_writeback(self, fresh: Spreadsheet) -> tuple[str, dict[str, str]]:
        """以剛從雲端重新讀到的內容，比對結構並計算要寫入的儲存格。回傳 (工作表名稱, {A1: 文字})。"""
        self.ensure_can_write_back()
        try:
            parsed = parse_spreadsheet(fresh)
        except ValueError as exc:
            raise ActivityError(f"試算表在匯入後被修改，無法寫回：{exc}。請重新匯入", 409) from exc
        with self._lock:
            imported = [(q.number, q.sub_count) for q in self.questions]
            if parsed.structure() != imported:
                raise ActivityError("試算表的題目在匯入後被修改（題號或題組小題數不同），請重新匯入後再寫回", 409)
            return parsed.sheet_title, build_writes(parsed, self.export_answers())

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

    def _clear_round(self) -> None:
        self.submissions = {}
        self.marks = {}
        self.opened_at = None
        self.deadline = None
        self._seq = 0

    def _touch(self) -> None:
        self.version += 1


def effective_time(s: Submission, fair_mode: bool, delay: float) -> float:
    """有效時間 = 收到時間 + 收到當下已成功題數 × 延遲量（公平模式）；否則就是收到時間。"""
    return s.at + s.prior_wins * delay if fair_mode else s.at


def rank_submissions(submissions: dict[int, list[Submission]], fair_mode: bool,
                     delay: float) -> dict[int, list[Submission]]:
    """每題依（有效時間, 收到序號）排序；第一名即搶答成功。"""
    return {
        n: sorted(subs, key=lambda s: (effective_time(s, fair_mode, delay), s.seq))
        for n, subs in submissions.items() if subs
    }
