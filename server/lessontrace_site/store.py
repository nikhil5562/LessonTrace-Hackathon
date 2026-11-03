"""Small local pilot store. Browser ownership is enforced on every record lookup."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid


class Store:
    def __init__(self, path: Path, legacy_ledger: Path | None = None, *, provider_limit_cents: int = 100):
        if isinstance(provider_limit_cents, bool) or not isinstance(provider_limit_cents, int) or not 10 <= provider_limit_cents <= 3500 or provider_limit_cents % 10:
            raise ValueError('Set an explicitly approved testing limit in whole 10-cent reservations, from 10 to 3500 cents.')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.legacy_ledger = legacy_ledger
        self.provider_limit_cents = provider_limit_cents
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                  id TEXT PRIMARY KEY, owner TEXT NOT NULL, mode TEXT NOT NULL,
                  source TEXT NOT NULL, source_hash TEXT NOT NULL, status TEXT NOT NULL,
                  report TEXT, hints INTEGER NOT NULL DEFAULT 0, solution_viewed INTEGER NOT NULL DEFAULT 0,
                  created REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_owner ON runs(owner, created);
                CREATE TABLE IF NOT EXISTS progress (owner TEXT, key TEXT, value TEXT, PRIMARY KEY(owner,key));
                CREATE TABLE IF NOT EXISTS packs (
                  id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL,
                  text TEXT NOT NULL, source_hash TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
                  created REAL NOT NULL, UNIQUE(owner,version)
                );
                CREATE TABLE IF NOT EXISTS provider_reservations (
                  id TEXT PRIMARY KEY, owner TEXT NOT NULL, purpose TEXT NOT NULL,
                  cents INTEGER NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS learning_sessions (
                  owner TEXT NOT NULL, id TEXT NOT NULL, context TEXT NOT NULL,
                  title TEXT NOT NULL, record TEXT NOT NULL, updated REAL NOT NULL,
                  PRIMARY KEY(owner,id)
                );
                CREATE INDEX IF NOT EXISTS learning_sessions_owner ON learning_sessions(owner,updated);
                CREATE TABLE IF NOT EXISTS provider_calls (
                  reservation_id TEXT PRIMARY KEY, owner TEXT NOT NULL, session_id TEXT,
                  purpose TEXT NOT NULL, outcome TEXT NOT NULL, failure TEXT,
                  latency_ms INTEGER NOT NULL, prompt_tokens INTEGER, completion_tokens INTEGER,
                  total_tokens INTEGER, model TEXT, created REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS provider_calls_owner_session ON provider_calls(owner,session_id);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def set_progress(self, owner, key, value):
        with self.db() as db:
            db.execute("INSERT INTO progress VALUES (?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value", (owner, key, json.dumps(value)))

    def progress(self, owner):
        with self.db() as db:
            return {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT key,value FROM progress WHERE owner=?", (owner,))}

    def mutate_progress(self, owner, key, default, change):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT value FROM progress WHERE owner=? AND key=?',(owner,key)).fetchone()
            value=json.loads(row['value']) if row else json.loads(json.dumps(default))
            change(value)
            db.execute('INSERT INTO progress VALUES (?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value',(owner,key,json.dumps(value)))
        return value

    def save_lesson(self, owner, record):
        with self.db() as db:
            db.execute('INSERT INTO learning_sessions VALUES (?,?,?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET title=excluded.title,record=excluded.record,updated=excluded.updated',
                (owner,record['lesson_id'],record.get('context','video'),record['title'],json.dumps(record),time.time()))

    def saved_lesson(self, owner, identifier):
        with self.db() as db:row=db.execute('SELECT record FROM learning_sessions WHERE owner=? AND id=?',(owner,identifier)).fetchone()
        return json.loads(row['record']) if row else None

    def lesson_list(self, owner):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT id,context,title,updated FROM learning_sessions WHERE owner=? ORDER BY updated DESC LIMIT 40',(owner,))]

    def create_run(self, owner, mode, source, source_hash):
        identifier = str(uuid.uuid4())
        with self.db() as db:
            recent = db.execute("SELECT count(*) FROM runs WHERE owner=? AND created>?", (owner, time.time()-3600)).fetchone()[0]
            if recent >= 120:
                raise ValueError("This browser has reached the pilot's hourly run limit.")
            db.execute("INSERT INTO runs(id,owner,mode,source,source_hash,status,created) VALUES(?,?,?,?,?,'queued',?)", (identifier, owner, mode, source, source_hash, time.time()))
        return identifier

    def get_run(self, owner, identifier):
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=? AND owner=?", (identifier, owner)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["report"] = json.loads(result["report"]) if result["report"] else None
        return result

    def finish_run(self, owner, identifier, status, report=None):
        with self.db() as db:
            db.execute("UPDATE runs SET status=?,report=? WHERE id=? AND owner=? AND status != 'cancelled'", (status, json.dumps(report) if report is not None else None, identifier, owner))

    def cancel_run(self, owner, identifier):
        with self.db() as db:
            db.execute("UPDATE runs SET status='cancelled' WHERE owner=? AND id=? AND status IN ('queued','running')", (owner, identifier))

    def history(self, owner):
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT id,mode,status,hints,solution_viewed,created,source_hash,json_extract(report,'$.origin') AS origin FROM runs WHERE owner=? ORDER BY created DESC LIMIT 40", (owner,))]

    def legacy_provider_cents(self):
        if not self.legacy_ledger or not self.legacy_ledger.is_file():
            return 0
        try:
            legacy = json.loads(self.legacy_ledger.read_text(encoding="utf-8"))
            micro = legacy["reserved_micro_usd"]
            if not isinstance(micro, int) or isinstance(micro, bool) or micro < 0:
                raise ValueError
            return (micro + 9999) // 10000
        except (OSError, ValueError, KeyError):
            raise ValueError("The earlier testing budget could not be verified. Live requests remain paused.") from None

    def provider_allowance(self):
        with self.db() as db:
            reserved = db.execute("SELECT coalesce(sum(cents),0) FROM provider_reservations").fetchone()[0]
        try:
            reserved += self.legacy_provider_cents()
        except ValueError:
            return {"remaining_requests": 0, "status": "Earlier reservations need verification."}
        return {"remaining_requests": max(0,(self.provider_limit_cents-reserved)//10), "reserved_cents":reserved, "limit_cents":self.provider_limit_cents,
                "status":"Conservative test reservations, not actual billed charges."}

    def reserve_provider(self, owner, purpose):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            reserved = db.execute("SELECT coalesce(sum(cents),0) FROM provider_reservations").fetchone()[0]
            legacy_cents = self.legacy_provider_cents()
            if reserved + legacy_cents + 10 > self.provider_limit_cents:
                raise ValueError("The pilot's cumulative provider reservation limit has been reached.")
            identifier=str(uuid.uuid4())
            db.execute("INSERT INTO provider_reservations VALUES(?,?,?,?,?)", (identifier, owner, purpose, 10, time.time()))
        return identifier

    def record_provider_call(self,context,session,result,latency_ms,failure):
        usage=(result or {}).get('usage') or {}
        if not isinstance(usage,dict):usage={}
        def tokens(key):
            value=usage.get(key)
            return value if isinstance(value,int) and not isinstance(value,bool) and 0<=value<=1_000_000_000 else None
        with self.db() as db:
            db.execute('INSERT INTO provider_calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (context['reservation_id'],context['owner'],session,context['purpose'],'failed' if failure else 'response_received',str(failure)[:60] if failure else None,
                 max(0,latency_ms),tokens('prompt_tokens'),tokens('completion_tokens'),tokens('total_tokens'),str((result or {}).get('model',''))[:100] or None,time.time()))

    def provider_usage(self,owner,session=None):
        query='SELECT c.*,r.cents FROM provider_calls c JOIN provider_reservations r ON r.id=c.reservation_id WHERE c.owner=?'
        args=[owner]
        if session:query+=' AND c.session_id=?';args.append(session)
        with self.db() as db:rows=[dict(row) for row in db.execute(query,args)]
        return {'recorded_calls':len(rows),'failed_calls':sum(row['outcome']=='failed' for row in rows),'reserved_cents':sum(row['cents'] for row in rows),
            'reported_prompt_tokens':sum(row['prompt_tokens'] or 0 for row in rows),'reported_completion_tokens':sum(row['completion_tokens'] or 0 for row in rows),
            'reported_total_tokens':sum(row['total_tokens'] or 0 for row in rows),'calls_with_usage':sum(row['total_tokens'] is not None for row in rows),
            'latency_ms':sum(row['latency_ms'] for row in rows),'billed_cost_usd':None,
            'coverage':'Calls recorded since this update only. Reserved cents are not actual billed cost; older reservations remain in the global allowance.'}

    def invalidate_packs(self, owner):
        with self.db() as db:
            db.execute("UPDATE packs SET approved=0 WHERE owner=?", (owner,))

    def hint_level(self, owner, identifier):
        with self.db() as db:
            db.execute("UPDATE runs SET hints=min(hints+1,4) WHERE owner=? AND id=?", (owner, identifier))
            return db.execute("SELECT hints FROM runs WHERE owner=? AND id=?", (owner, identifier)).fetchone()[0]

    def mark_solution(self, owner, identifier, mode):
        with self.db() as db:
            db.execute("UPDATE runs SET solution_viewed=1 WHERE owner=? AND id=?", (owner, identifier))
        self.set_progress(owner, mode + "_solution_viewed", True)

    def create_pack(self, owner, text, source_hash):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("SELECT coalesce(max(version),0)+1 FROM packs WHERE owner=?", (owner,)).fetchone()[0]
            db.execute("UPDATE packs SET approved=0 WHERE owner=?", (owner,))
            identifier = str(uuid.uuid4())
            db.execute("INSERT INTO packs(id,owner,version,text,source_hash,created) VALUES(?,?,?,?,?,?)", (identifier, owner, version, text, source_hash, time.time()))
        return self.get_pack(owner, identifier)

    def get_pack(self, owner, identifier=None):
        with self.db() as db:
            if identifier:
                row = db.execute("SELECT * FROM packs WHERE owner=? AND id=?", (owner, identifier)).fetchone()
            else:
                row = db.execute("SELECT * FROM packs WHERE owner=? ORDER BY version DESC LIMIT 1", (owner,)).fetchone()
        return dict(row) if row else None

    def approve_pack(self, owner, identifier):
        with self.db() as db:
            db.execute("UPDATE packs SET approved=1 WHERE owner=? AND id=? AND version=(SELECT max(version) FROM packs WHERE owner=?)", (owner, identifier, owner))
        return self.get_pack(owner, identifier)

    def delete_owner(self, owner):
        with self.db() as db:
            for table in ("runs", "progress", "packs", "learning_sessions"):
                db.execute(f"DELETE FROM {table} WHERE owner=?", (owner,))
            db.execute("UPDATE provider_calls SET owner='',session_id=NULL WHERE owner=?",(owner,))
            db.execute("UPDATE provider_reservations SET owner='' WHERE owner=?",(owner,))
