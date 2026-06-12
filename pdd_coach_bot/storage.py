from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class UserState:
    user_id: int
    first_name: str
    timezone: str
    intensity: str
    touches_per_day: int
    notifications_enabled: bool
    exam_date: str | None
    goal: str | None
    study_minutes: int | None
    experience_level: str | None
    onboarding_step: str | None


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS users (
                    tg_user_id INTEGER PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    intensity TEXT NOT NULL,
                    touches_per_day INTEGER NOT NULL,
                    notifications_enabled INTEGER NOT NULL DEFAULT 1,
                    exam_date TEXT,
                    goal TEXT,
                    study_minutes INTEGER,
                    experience_level TEXT,
                    onboarding_step TEXT,
                    pinned_daily_plan_message_id INTEGER,
                    pinned_daily_plan_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lesson_progress (
                    tg_user_id INTEGER NOT NULL,
                    lesson_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    confidence INTEGER NOT NULL DEFAULT 0,
                    read_count INTEGER NOT NULL DEFAULT 0,
                    last_read_at TEXT,
                    next_review_at TEXT,
                    PRIMARY KEY (tg_user_id, lesson_id),
                    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS topic_progress (
                    tg_user_id INTEGER NOT NULL,
                    topic_id TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    last_activity_at TEXT,
                    next_review_at TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    PRIMARY KEY (tg_user_id, topic_id),
                    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS question_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_user_id INTEGER NOT NULL,
                    question_id TEXT NOT NULL,
                    topic_id TEXT,
                    is_correct INTEGER NOT NULL,
                    answered_at TEXT NOT NULL,
                    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS question_progress (
                    tg_user_id INTEGER NOT NULL,
                    question_id TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    last_seen_at TEXT,
                    last_correct_at TEXT,
                    next_review_at TEXT,
                    PRIMARY KEY (tg_user_id, question_id),
                    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    tg_user_id INTEGER PRIMARY KEY,
                    mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS notifications_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_user_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS session_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_user_id INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    topic_id TEXT,
                    ticket_id TEXT,
                    correct_answers INTEGER NOT NULL,
                    wrong_answers INTEGER NOT NULL,
                    total_questions INTEGER NOT NULL,
                    completed_at TEXT NOT NULL,
                    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
                );
                """
            )
            existing_user_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "exam_date" not in existing_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN exam_date TEXT")
            if "goal" not in existing_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN goal TEXT")
            if "study_minutes" not in existing_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN study_minutes INTEGER")
            if "experience_level" not in existing_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN experience_level TEXT")
            if "onboarding_step" not in existing_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN onboarding_step TEXT")
            if "pinned_daily_plan_message_id" not in existing_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN pinned_daily_plan_message_id INTEGER")
            if "pinned_daily_plan_date" not in existing_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN pinned_daily_plan_date TEXT")

    def upsert_user(
        self,
        tg_user_id: int,
        first_name: str,
        timezone: str,
        intensity: str,
        touches_per_day: int,
        exam_date: str | None = None,
        goal: str | None = None,
        study_minutes: int | None = None,
        experience_level: str | None = None,
        onboarding_step: str | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    tg_user_id, first_name, timezone, intensity, touches_per_day, notifications_enabled, exam_date, goal, study_minutes, experience_level, onboarding_step, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tg_user_id) DO UPDATE SET
                    first_name=excluded.first_name,
                    timezone=excluded.timezone,
                    intensity=excluded.intensity,
                    touches_per_day=excluded.touches_per_day,
                    exam_date=COALESCE(excluded.exam_date, users.exam_date),
                    goal=COALESCE(excluded.goal, users.goal),
                    study_minutes=COALESCE(excluded.study_minutes, users.study_minutes),
                    experience_level=COALESCE(excluded.experience_level, users.experience_level),
                    onboarding_step=COALESCE(excluded.onboarding_step, users.onboarding_step),
                    updated_at=excluded.updated_at
                """,
                (
                    tg_user_id,
                    first_name,
                    timezone,
                    intensity,
                    touches_per_day,
                    exam_date,
                    goal,
                    study_minutes,
                    experience_level,
                    onboarding_step,
                    now,
                    now,
                ),
            )

    def get_user(self, tg_user_id: int) -> UserState | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE tg_user_id = ?", (tg_user_id,)).fetchone()
        if not row:
            return None
        return UserState(
            user_id=row["tg_user_id"],
            first_name=row["first_name"],
            timezone=row["timezone"],
            intensity=row["intensity"],
            touches_per_day=row["touches_per_day"],
            notifications_enabled=bool(row["notifications_enabled"]),
            exam_date=row["exam_date"],
            goal=row["goal"],
            study_minutes=row["study_minutes"],
            experience_level=row["experience_level"],
            onboarding_step=row["onboarding_step"],
        )

    def set_notifications_enabled(self, tg_user_id: int, enabled: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET notifications_enabled = ?, updated_at = ? WHERE tg_user_id = ?",
                (1 if enabled else 0, utc_now(), tg_user_id),
            )

    def set_exam_date(self, tg_user_id: int, exam_date: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET exam_date = ?, updated_at = ? WHERE tg_user_id = ?",
                (exam_date, utc_now(), tg_user_id),
            )

    def update_profile(
        self,
        tg_user_id: int,
        *,
        goal: str | None = None,
        study_minutes: int | None = None,
        experience_level: str | None = None,
        onboarding_step: str | None = None,
        intensity: str | None = None,
        touches_per_day: int | None = None,
    ) -> None:
        assignments: list[str] = ["updated_at = ?"]
        values: list[object] = [utc_now()]
        if goal is not None:
            assignments.append("goal = ?")
            values.append(goal)
        if study_minutes is not None:
            assignments.append("study_minutes = ?")
            values.append(study_minutes)
        if experience_level is not None:
            assignments.append("experience_level = ?")
            values.append(experience_level)
        if onboarding_step is not None:
            assignments.append("onboarding_step = ?")
            values.append(onboarding_step)
        if intensity is not None:
            assignments.append("intensity = ?")
            values.append(intensity)
        if touches_per_day is not None:
            assignments.append("touches_per_day = ?")
            values.append(touches_per_day)
        values.append(tg_user_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE tg_user_id = ?",
                tuple(values),
            )

    def get_daily_plan_pin_state(self, tg_user_id: int) -> tuple[int | None, str | None]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT pinned_daily_plan_message_id, pinned_daily_plan_date FROM users WHERE tg_user_id = ?",
                (tg_user_id,),
            ).fetchone()
        if not row:
            return None, None
        return row["pinned_daily_plan_message_id"], row["pinned_daily_plan_date"]

    def set_daily_plan_pin_state(self, tg_user_id: int, message_id: int | None, plan_date: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET pinned_daily_plan_message_id = ?, pinned_daily_plan_date = ?, updated_at = ?
                WHERE tg_user_id = ?
                """,
                (message_id, plan_date, utc_now(), tg_user_id),
            )

    def save_session(self, tg_user_id: int, mode: str, payload: dict[str, object]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (tg_user_id, mode, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tg_user_id) DO UPDATE SET
                    mode=excluded.mode,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (tg_user_id, mode, json.dumps(payload, ensure_ascii=False), utc_now()),
            )

    def get_session(self, tg_user_id: int) -> tuple[str, dict[str, object]] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT mode, payload_json FROM sessions WHERE tg_user_id = ?", (tg_user_id,)).fetchone()
        if not row:
            return None
        return row["mode"], json.loads(row["payload_json"])

    def clear_session(self, tg_user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE tg_user_id = ?", (tg_user_id,))

    def mark_lesson(
        self,
        tg_user_id: int,
        lesson_id: str,
        status: str,
        confidence_delta: int,
        next_review_at: str | None,
    ) -> None:
        with self.connect() as conn:
            current = conn.execute(
                "SELECT confidence, read_count FROM lesson_progress WHERE tg_user_id = ? AND lesson_id = ?",
                (tg_user_id, lesson_id),
            ).fetchone()
            confidence = (current["confidence"] if current else 0) + confidence_delta
            read_count = (current["read_count"] if current else 0) + 1
            conn.execute(
                """
                INSERT INTO lesson_progress (
                    tg_user_id, lesson_id, status, confidence, read_count, last_read_at, next_review_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tg_user_id, lesson_id) DO UPDATE SET
                    status=excluded.status,
                    confidence=excluded.confidence,
                    read_count=excluded.read_count,
                    last_read_at=excluded.last_read_at,
                    next_review_at=excluded.next_review_at
                """,
                (tg_user_id, lesson_id, status, confidence, read_count, utc_now(), next_review_at),
            )

    def get_lesson_progress(self, tg_user_id: int) -> dict[str, sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM lesson_progress WHERE tg_user_id = ?", (tg_user_id,)).fetchall()
        return {row["lesson_id"]: row for row in rows}

    def record_attempt(self, tg_user_id: int, question_id: str, topic_id: str | None, is_correct: bool) -> None:
        answered_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO question_attempts (tg_user_id, question_id, topic_id, is_correct, answered_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tg_user_id, question_id, topic_id, 1 if is_correct else 0, answered_at),
            )
            question_row = conn.execute(
                """
                SELECT score, correct_count, wrong_count, streak
                FROM question_progress
                WHERE tg_user_id = ? AND question_id = ?
                """,
                (tg_user_id, question_id),
            ).fetchone()
            old_score = float(question_row["score"]) if question_row else 0.0
            correct_count = int(question_row["correct_count"]) if question_row else 0
            wrong_count = int(question_row["wrong_count"]) if question_row else 0
            streak = int(question_row["streak"]) if question_row else 0
            if is_correct:
                correct_count += 1
                streak += 1
                new_score = min(12.0, old_score + (1.0 if streak < 2 else 1.5))
                last_correct_at = answered_at
            else:
                wrong_count += 1
                streak = 0
                new_score = max(-6.0, old_score - 2.0)
                last_correct_at = question_row["last_correct_at"] if question_row else None
            conn.execute(
                """
                INSERT INTO question_progress (
                    tg_user_id, question_id, score, correct_count, wrong_count, streak, last_seen_at, last_correct_at, next_review_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tg_user_id, question_id) DO UPDATE SET
                    score=excluded.score,
                    correct_count=excluded.correct_count,
                    wrong_count=excluded.wrong_count,
                    streak=excluded.streak,
                    last_seen_at=excluded.last_seen_at,
                    last_correct_at=excluded.last_correct_at,
                    next_review_at=excluded.next_review_at
                """,
                (
                    tg_user_id,
                    question_id,
                    new_score,
                    correct_count,
                    wrong_count,
                    streak,
                    answered_at,
                    last_correct_at,
                    _next_question_review_timestamp(new_score, streak, is_correct),
                ),
            )
            if topic_id:
                row = conn.execute(
                    "SELECT score, correct_count, wrong_count FROM topic_progress WHERE tg_user_id = ? AND topic_id = ?",
                    (tg_user_id, topic_id),
                ).fetchone()
                old_score = float(row["score"]) if row else 0.0
                correct_count = int(row["correct_count"]) if row else 0
                wrong_count = int(row["wrong_count"]) if row else 0
                new_score = max(-4.0, min(10.0, old_score + (1.2 if is_correct else -1.4)))
                if is_correct:
                    correct_count += 1
                else:
                    wrong_count += 1
                status = _topic_status(new_score, correct_count, wrong_count)
                next_review_at = _next_review_timestamp(new_score, is_correct)
                conn.execute(
                    """
                    INSERT INTO topic_progress (
                        tg_user_id, topic_id, score, correct_count, wrong_count, last_activity_at, next_review_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tg_user_id, topic_id) DO UPDATE SET
                        score=excluded.score,
                        correct_count=excluded.correct_count,
                        wrong_count=excluded.wrong_count,
                        last_activity_at=excluded.last_activity_at,
                        next_review_at=excluded.next_review_at,
                        status=excluded.status
                    """,
                    (
                        tg_user_id,
                        topic_id,
                        new_score,
                        correct_count,
                        wrong_count,
                        answered_at,
                        next_review_at,
                        status,
                    ),
                )

    def get_topic_progress(self, tg_user_id: int) -> dict[str, sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM topic_progress WHERE tg_user_id = ?", (tg_user_id,)).fetchall()
        return {row["topic_id"]: row for row in rows}

    def get_question_progress(self, tg_user_id: int) -> dict[str, sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM question_progress WHERE tg_user_id = ?", (tg_user_id,)).fetchall()
        return {row["question_id"]: row for row in rows}

    def get_recent_errors(self, tg_user_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT question_id, topic_id, answered_at
                FROM question_attempts
                WHERE tg_user_id = ? AND is_correct = 0
                ORDER BY answered_at DESC
                LIMIT ?
                """,
                (tg_user_id, limit),
            ).fetchall()

    def get_recent_attempts(self, tg_user_id: int, limit: int = 50) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT question_id, topic_id, is_correct, answered_at
                FROM question_attempts
                WHERE tg_user_id = ?
                ORDER BY answered_at DESC
                LIMIT ?
                """,
                (tg_user_id, limit),
            ).fetchall()

    def get_recent_error_question_ids(self, tg_user_id: int, limit: int = 12) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT question_id, MAX(answered_at) AS last_seen
                FROM question_attempts
                WHERE tg_user_id = ? AND is_correct = 0
                GROUP BY question_id
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (tg_user_id, limit),
            ).fetchall()
        return [str(row["question_id"]) for row in rows]

    def record_completed_session(
        self,
        tg_user_id: int,
        mode: str,
        correct_answers: int,
        wrong_answers: int,
        total_questions: int,
        topic_id: str | None = None,
        ticket_id: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO session_history (
                    tg_user_id, mode, topic_id, ticket_id, correct_answers, wrong_answers, total_questions, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tg_user_id, mode, topic_id, ticket_id, correct_answers, wrong_answers, total_questions, utc_now()),
            )

    def get_question_stats(self, tg_user_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT question_id) AS unique_seen,
                    COUNT(DISTINCT CASE WHEN is_correct = 1 THEN question_id END) AS unique_correct,
                    SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS total_correct,
                    COUNT(*) AS total_attempts
                FROM question_attempts
                WHERE tg_user_id = ?
                """,
                (tg_user_id,),
            ).fetchone()
        return row

    def get_problem_question_count(self, tg_user_id: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM (
                    SELECT
                        question_id,
                        SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS c,
                        SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS w
                    FROM question_attempts
                    WHERE tg_user_id = ?
                    GROUP BY question_id
                    HAVING w > c OR c = 0
                )
                """,
                (tg_user_id,),
            ).fetchone()
        return int(row["c"])

    def get_seen_question_ids(self, tg_user_id: int) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT question_id FROM question_attempts WHERE tg_user_id = ?",
                (tg_user_id,),
            ).fetchall()
        return {str(row["question_id"]) for row in rows}

    def get_correct_question_ids(self, tg_user_id: int) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT question_id FROM question_attempts WHERE tg_user_id = ? AND is_correct = 1",
                (tg_user_id,),
            ).fetchall()
        return {str(row["question_id"]) for row in rows}

    def get_ticket_stats(self, tg_user_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS sessions_count,
                    COUNT(DISTINCT ticket_id) AS unique_tickets,
                    AVG(CASE WHEN total_questions > 0 THEN correct_answers * 100.0 / total_questions END) AS avg_percent,
                    SUM(CASE WHEN wrong_answers = 0 AND total_questions >= 20 THEN 1 ELSE 0 END) AS perfect_runs,
                    MAX(completed_at) AS last_completed_at
                FROM session_history
                WHERE tg_user_id = ? AND mode = 'ticket'
                """,
                (tg_user_id,),
            ).fetchone()
        return row

    def get_per_ticket_best_scores(self, tg_user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT ticket_id, MAX(correct_answers) AS best_correct, MAX(total_questions) AS total_questions
                FROM session_history
                WHERE tg_user_id = ? AND mode = 'ticket' AND ticket_id IS NOT NULL
                GROUP BY ticket_id
                """,
                (tg_user_id,),
            ).fetchall()

    def get_last_ticket_session(self, tg_user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT ticket_id, correct_answers, total_questions, completed_at
                FROM session_history
                WHERE tg_user_id = ? AND mode = 'ticket' AND ticket_id IS NOT NULL
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                (tg_user_id,),
            ).fetchone()

    def get_today_activity(self, tg_user_id: int, start_iso: str, end_iso: str) -> dict[str, int]:
        with self.connect() as conn:
            question_stats = conn.execute(
                """
                SELECT
                    COUNT(*) AS questions_today,
                    COUNT(DISTINCT question_id) AS unique_questions_today
                FROM question_attempts
                WHERE tg_user_id = ? AND answered_at >= ? AND answered_at < ?
                """,
                (tg_user_id, start_iso, end_iso),
            ).fetchone()
            lesson_stats = conn.execute(
                """
                SELECT COUNT(*) AS lessons_today
                FROM lesson_progress
                WHERE tg_user_id = ? AND last_read_at >= ? AND last_read_at < ?
                """,
                (tg_user_id, start_iso, end_iso),
            ).fetchone()
            session_stats = conn.execute(
                """
                SELECT
                    COUNT(*) AS sessions_today,
                    SUM(CASE WHEN mode = 'ticket' THEN 1 ELSE 0 END) AS tickets_today,
                    SUM(CASE WHEN mode IN ('mixed', 'errors', 'topic') THEN 1 ELSE 0 END) AS practice_today
                FROM session_history
                WHERE tg_user_id = ? AND completed_at >= ? AND completed_at < ?
                """,
                (tg_user_id, start_iso, end_iso),
            ).fetchone()
        return {
            "questions_today": int(question_stats["questions_today"] or 0),
            "unique_questions_today": int(question_stats["unique_questions_today"] or 0),
            "lessons_today": int(lesson_stats["lessons_today"] or 0),
            "sessions_today": int(session_stats["sessions_today"] or 0),
            "tickets_today": int(session_stats["tickets_today"] or 0),
            "practice_today": int(session_stats["practice_today"] or 0),
        }

    def get_question_attempts_between(self, tg_user_id: int, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT question_id, topic_id, is_correct, answered_at
                FROM question_attempts
                WHERE tg_user_id = ? AND answered_at >= ? AND answered_at < ?
                ORDER BY answered_at DESC
                """,
                (tg_user_id, start_iso, end_iso),
            ).fetchall()

    def get_session_history_between(self, tg_user_id: int, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT mode, topic_id, ticket_id, correct_answers, wrong_answers, total_questions, completed_at
                FROM session_history
                WHERE tg_user_id = ? AND completed_at >= ? AND completed_at < ?
                ORDER BY completed_at DESC
                """,
                (tg_user_id, start_iso, end_iso),
            ).fetchall()

    def log_notification(self, tg_user_id: int, notification_type: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO notifications_log (tg_user_id, notification_type, sent_at) VALUES (?, ?, ?)",
                (tg_user_id, notification_type, utc_now()),
            )

    def notifications_sent_between(
        self,
        tg_user_id: int,
        start_iso: str,
        end_iso: str,
        notification_type: str | None = None,
    ) -> int:
        with self.connect() as conn:
            if notification_type is None:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM notifications_log
                    WHERE tg_user_id = ? AND sent_at >= ? AND sent_at < ?
                    """,
                    (tg_user_id, start_iso, end_iso),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM notifications_log
                    WHERE tg_user_id = ? AND sent_at >= ? AND sent_at < ? AND notification_type = ?
                    """,
                    (tg_user_id, start_iso, end_iso, notification_type),
                ).fetchone()
        return int(row["c"])

    def list_users(self) -> list[UserState]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
        return [
            UserState(
                user_id=row["tg_user_id"],
                first_name=row["first_name"],
                timezone=row["timezone"],
                intensity=row["intensity"],
                touches_per_day=row["touches_per_day"],
                notifications_enabled=bool(row["notifications_enabled"]),
                exam_date=row["exam_date"],
                goal=row["goal"],
                study_minutes=row["study_minutes"],
                experience_level=row["experience_level"],
                onboarding_step=row["onboarding_step"],
            )
            for row in rows
        ]


def _topic_status(score: float, correct_count: int, wrong_count: int) -> str:
    if correct_count + wrong_count == 0:
        return "new"
    if score <= -1:
        return "weak"
    if score < 3:
        return "learning"
    if score < 6:
        return "solid"
    return "strong"


def _next_review_timestamp(score: float, is_correct: bool) -> str:
    now = datetime.now(UTC)
    if not is_correct:
        due = now.replace(microsecond=0)
    elif score >= 6:
        due = now.replace(microsecond=0) + _hours(72)
    elif score >= 3:
        due = now.replace(microsecond=0) + _hours(24)
    else:
        due = now.replace(microsecond=0) + _hours(8)
    return due.isoformat()


def _hours(value: int):
    from datetime import timedelta

    return timedelta(hours=value)


def _next_question_review_timestamp(score: float, streak: int, is_correct: bool) -> str:
    now = datetime.now(UTC).replace(microsecond=0)
    if not is_correct:
        if score <= -3:
            return (now + _hours(3)).isoformat()
        return (now + _hours(8)).isoformat()
    if streak >= 5 and score >= 8:
        return (now + _hours(168)).isoformat()
    if streak >= 3 and score >= 5:
        return (now + _hours(72)).isoformat()
    if streak >= 2 and score >= 2:
        return (now + _hours(24)).isoformat()
    return (now + _hours(8)).isoformat()
