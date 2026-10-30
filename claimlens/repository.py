"""
claimlens/repository.py
SQLite persistence layer for ClaimLens AI cases, fields, findings, and audit logs.
Uses parameterized queries only — no f-strings in SQL.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from claimlens.models import Case, Decision, ExtractedField, Finding


class CaseRepository:
    """Stores and retrieves Case objects in a local SQLite database.

    Creates the ``data/`` folder and all tables automatically on first use.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str = "data/claimlens.db") -> None:
        self.db_path = db_path
        # Make sure the parent folder exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def _init_tables(self) -> None:
        """Create tables if they do not already exist."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename        TEXT NOT NULL,
                    doc_type        TEXT NOT NULL,
                    status          TEXT NOT NULL,
                    recommendation  TEXT,
                    reasons         TEXT,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fields (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id     INTEGER NOT NULL,
                    name        TEXT NOT NULL,
                    value       TEXT,
                    confidence  REAL NOT NULL,
                    status      TEXT NOT NULL,
                    source_text TEXT
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id  INTEGER NOT NULL,
                    code     TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id   INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    actor     TEXT NOT NULL,
                    action    TEXT NOT NULL,
                    details   TEXT
                );
            """)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open and return a new SQLite connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # lets us access columns by name
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_case(self, case: Case) -> int:
        """Insert a new case (with its fields and findings) and return its ID.

        Args:
            case: A populated Case dataclass (case_id may be None).

        Returns:
            The integer primary-key of the newly inserted row.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()

            # Insert the top-level case row
            reasons_json = json.dumps(case.decision.reasons if case.decision else [])
            recommendation = case.decision.recommendation if case.decision else None
            cur.execute(
                """
                INSERT INTO cases (filename, doc_type, status, recommendation, reasons, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (case.filename, case.doc_type, case.status,
                 recommendation, reasons_json, case.created_at),
            )
            case_id: int = cur.lastrowid  # type: ignore[assignment]

            # Insert each extracted field
            for ef in case.fields.values():
                cur.execute(
                    """
                    INSERT INTO fields (case_id, name, value, confidence, status, source_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (case_id, ef.name, ef.value, ef.confidence, ef.status, ef.source_text),
                )

            # Insert findings from the decision (if any)
            findings = case.decision.risk_indicators if case.decision else []
            for f in findings:
                cur.execute(
                    """
                    INSERT INTO findings (case_id, code, severity, message)
                    VALUES (?, ?, ?, ?)
                    """,
                    (case_id, f.code, f.severity, f.message),
                )

            conn.commit()
            return case_id
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"create_case failed: {exc}") from exc
        finally:
            conn.close()

    def get_case(self, case_id: int) -> "Case | None":
        """Rebuild a full Case object from the database.

        Args:
            case_id: Primary key of the case row.

        Returns:
            A Case dataclass with fields, findings and decision, or None.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()

            # Fetch the case row
            cur.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
            row = cur.fetchone()
            if row is None:
                return None

            # Rebuild fields dict
            cur.execute("SELECT * FROM fields WHERE case_id = ?", (case_id,))
            fields: dict[str, ExtractedField] = {}
            for frow in cur.fetchall():
                ef = ExtractedField(
                    name=frow["name"],
                    value=frow["value"],
                    confidence=frow["confidence"],
                    status=frow["status"],
                    source_text=frow["source_text"] or "",
                )
                fields[frow["name"]] = ef

            # Rebuild findings list
            cur.execute("SELECT * FROM findings WHERE case_id = ?", (case_id,))
            findings: list[Finding] = [
                Finding(code=r["code"], severity=r["severity"], message=r["message"])
                for r in cur.fetchall()
            ]

            # Rebuild Decision
            reasons: list[str] = json.loads(row["reasons"] or "[]")
            decision = Decision(
                recommendation=row["recommendation"] or "",
                reasons=reasons,
                risk_indicators=findings,
            ) if row["recommendation"] else None

            return Case(
                case_id=row["id"],
                filename=row["filename"],
                doc_type=row["doc_type"],
                fields=fields,
                findings=findings,
                decision=decision,
                status=row["status"],
                created_at=row["created_at"],
            )
        except Exception as exc:
            raise RuntimeError(f"get_case failed: {exc}") from exc
        finally:
            conn.close()

    def list_cases(
        self,
        search: str = "",
        status: str = "",
        recommendation: str = "",
    ) -> list[Case]:
        """Return a list of Cases, optionally filtered.

        Args:
            search:         Substring match against filename or applicant name.
            status:         Exact match against the case status column.
            recommendation: Exact match against the recommendation column.

        Returns:
            List of Case objects (fields and findings are included).
        """
        conn = self._connect()
        try:
            cur = conn.cursor()

            # Build WHERE clauses with parameterized values only
            conditions: list[str] = []
            params: list[object] = []

            if search:
                conditions.append("(c.filename LIKE ? OR f.value LIKE ?)")
                like = f"%{search}%"
                params.extend([like, like])
            if status:
                conditions.append("c.status = ?")
                params.append(status)
            if recommendation:
                conditions.append("c.recommendation = ?")
                params.append(recommendation)

            where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            # Build the full query string (structure only, no user data inline)
            query = (
                "SELECT DISTINCT c.id "
                "FROM cases c "
                "LEFT JOIN fields f ON f.case_id = c.id AND f.name = 'applicant_name' "
                + where_clause
                + " ORDER BY c.id"
            )
            cur.execute(query, params)
            rows = cur.fetchall()

            cases: list[Case] = []
            for row in rows:
                case = self.get_case(row["id"])
                if case is not None:
                    cases.append(case)
            return cases
        except Exception as exc:
            raise RuntimeError(f"list_cases failed: {exc}") from exc
        finally:
            conn.close()

    def update_field(
        self,
        case_id: int,
        name: str,
        new_value: str,
        reviewer: str,
    ) -> None:
        """Overwrite one extracted field with a manually corrected value.

        Sets confidence=1.0, status="verified", source_text="Manual correction"
        and writes an audit entry recording the old and new values.

        Args:
            case_id:   Target case ID.
            name:      Field name to update (e.g. "monthly_income").
            new_value: Corrected string value supplied by the reviewer.
            reviewer:  Name/ID of the human actor making the correction.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()

            # Fetch the old value for the audit entry
            cur.execute(
                "SELECT value FROM fields WHERE case_id = ? AND name = ?",
                (case_id, name),
            )
            old_row = cur.fetchone()
            old_value = old_row["value"] if old_row else None

            if old_row:
                # Update the existing field row
                cur.execute(
                    """
                    UPDATE fields
                    SET value = ?, confidence = 1.0, status = 'verified',
                        source_text = 'Manual correction'
                    WHERE case_id = ? AND name = ?
                    """,
                    (new_value, case_id, name),
                )
            else:
                # Field did not exist yet — insert it
                cur.execute(
                    """
                    INSERT INTO fields (case_id, name, value, confidence, status, source_text)
                    VALUES (?, ?, ?, 1.0, 'verified', 'Manual correction')
                    """,
                    (case_id, name, new_value),
                )

            # Write audit entry
            details = json.dumps({"field": name, "old": old_value, "new": new_value})
            self._add_audit_cur(cur, case_id, reviewer, "field_corrected", details)

            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"update_field failed: {exc}") from exc
        finally:
            conn.close()

    def save_decision(self, case_id: int, decision: Decision) -> None:
        """Replace findings and update recommendation/reasons for a case.

        Args:
            case_id:  Target case ID.
            decision: New Decision produced by the rule engine.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()

            # Delete old findings and insert the new ones
            cur.execute("DELETE FROM findings WHERE case_id = ?", (case_id,))
            for f in decision.risk_indicators:
                cur.execute(
                    """
                    INSERT INTO findings (case_id, code, severity, message)
                    VALUES (?, ?, ?, ?)
                    """,
                    (case_id, f.code, f.severity, f.message),
                )

            # Update case row
            reasons_json = json.dumps(decision.reasons)
            cur.execute(
                """
                UPDATE cases
                SET recommendation = ?, reasons = ?
                WHERE id = ?
                """,
                (decision.recommendation, reasons_json, case_id),
            )

            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"save_decision failed: {exc}") from exc
        finally:
            conn.close()

    def record_override(
        self,
        case_id: int,
        new_recommendation: str,
        reason: str,
        reviewer: str,
    ) -> None:
        """Apply a manual override to a case's recommendation.

        Args:
            case_id:            Target case ID.
            new_recommendation: The override recommendation string.
            reason:             Mandatory explanation for the override.
            reviewer:           Name/ID of the reviewer performing the override.

        Raises:
            ValueError: If reason is empty.
        """
        if not reason or not reason.strip():
            raise ValueError("Override reason must not be empty.")

        conn = self._connect()
        try:
            cur = conn.cursor()

            # Fetch old recommendation for the audit record
            cur.execute("SELECT recommendation FROM cases WHERE id = ?", (case_id,))
            row = cur.fetchone()
            old_recommendation = row["recommendation"] if row else None

            # Apply the override
            cur.execute(
                """
                UPDATE cases
                SET recommendation = ?, status = 'overridden'
                WHERE id = ?
                """,
                (new_recommendation, case_id),
            )

            # Audit entry
            details = json.dumps({
                "old_recommendation": old_recommendation,
                "new_recommendation": new_recommendation,
                "reason": reason,
            })
            self._add_audit_cur(cur, case_id, reviewer, "decision_overridden", details)

            conn.commit()
        except ValueError:
            raise
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"record_override failed: {exc}") from exc
        finally:
            conn.close()

    def add_audit(
        self,
        case_id: int,
        actor: str,
        action: str,
        details: str,
    ) -> None:
        """Write one entry to the audit log.

        Args:
            case_id: Associated case ID.
            actor:   Who performed the action (e.g. "system", "reviewer").
            action:  Short action label (e.g. "uploaded", "auto_analyzed").
            details: Free-text or JSON detail string.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            self._add_audit_cur(cur, case_id, actor, action, details)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"add_audit failed: {exc}") from exc
        finally:
            conn.close()

    def get_audit_log(self, case_id: int) -> list[dict]:
        """Return all audit entries for a case, newest first.

        Args:
            case_id: Target case ID.

        Returns:
            List of dicts with keys: id, case_id, timestamp, actor, action, details.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, case_id, timestamp, actor, action, details
                FROM audit_log
                WHERE case_id = ?
                ORDER BY timestamp DESC, id DESC
                """,
                (case_id,),
            )
            return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            raise RuntimeError(f"get_audit_log failed: {exc}") from exc
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_audit_cur(
        self,
        cur: sqlite3.Cursor,
        case_id: int,
        actor: str,
        action: str,
        details: str,
    ) -> None:
        """Insert an audit row using an existing cursor (no commit)."""
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        cur.execute(
            """
            INSERT INTO audit_log (case_id, timestamp, actor, action, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, timestamp, actor, action, details),
        )
