"""
Event Bus & Asynchronous Notification Worker
GEC Hackathon 2026 - Problem Statement 01
Healthcare: Patient Triage & Queue Management

Handles:
1. Event generation on patient registration, priority elevation, doctor availability.
2. Synchronous processing: Triage confirmation, immediate critical queue updates,
   and critical clinical alerts.
3. Asynchronous processing: Background thread worker processing the notification queue
   for simulated SMS, email, hospital announcements, and routine analytics reports.
4. Real-time push via In-Memory SSE (Server-Sent Events) queue for connected UI dashboards.
"""

import threading
import time
import uuid
import json
import queue
from datetime import datetime
import sqlite3

class EventBus:
    """
    Hospital Event Processing Engine separating Synchronous critical clinical actions
    from Asynchronous background notifications and reporting.
    """
    _instance = None
    _sse_subscribers = []
    _lock = threading.Lock()

    def __init__(self, db_path):
        self.db_path = db_path
        self.async_worker_running = True
        self.worker_thread = threading.Thread(target=self._process_async_notifications_loop, daemon=True)
        self.worker_thread.start()

    def get_db_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # 1. Server-Sent Events (SSE) Client Streaming
    # -------------------------------------------------------------
    def subscribe_sse(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._sse_subscribers.append(q)
        return q

    def unsubscribe_sse(self, q):
        with self._lock:
            if q in self._sse_subscribers:
                self._sse_subscribers.remove(q)

    def _broadcast_to_sse(self, event_data):
        with self._lock:
            dead_queues = []
            for q in self._sse_subscribers:
                try:
                    q.put_nowait(event_data)
                except queue.Full:
                    dead_queues.append(q)
            for dead in dead_queues:
                if dead in self._sse_subscribers:
                    self._sse_subscribers.remove(dead)

    # -------------------------------------------------------------
    # 2. Synchronous Workflow Handler (Immediate Critical Path)
    # -------------------------------------------------------------
    def dispatch_sync(self, event_type, entity_type, entity_id, payload, db_cursor=None):
        """
        Processes critical workflows synchronously within the transaction:
        - Triage confirmation
        - Critical / Urgent queue reordering
        - Emergency Doctor alerts
        """
        event_uuid = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        payload_str = json.dumps(payload)

        # Log to event_logs
        should_close = False
        if db_cursor is None:
            conn = self.get_db_conn()
            cursor = conn.cursor()
            should_close = True
        else:
            cursor = db_cursor

        cursor.execute('''
            INSERT INTO event_logs (event_uuid, event_type, entity_type, entity_id, is_critical_sync, payload_json)
            VALUES (?, ?, ?, ?, 1, ?)
        ''', (event_uuid, event_type, entity_type, entity_id, payload_str))

        if should_close:
            conn.commit()
            conn.close()

        # Synchronous in-memory actions:
        event_obj = {
            "uuid": event_uuid,
            "type": event_type,
            "entity": entity_type,
            "id": entity_id,
            "is_critical_sync": True,
            "payload": payload,
            "timestamp": created_at
        }

        # Real-time broadcast to all open staff screens
        self._broadcast_to_sse(event_obj)
        return event_obj

    # -------------------------------------------------------------
    # 3. Asynchronous Workflow Enqueuer (Decoupled Background Path)
    # -------------------------------------------------------------
    def dispatch_async(self, event_type, entity_type, entity_id, payload, notifications=None):
        """
        Processes routine notifications, audits, and non-blocking tasks asynchronously.
        Enqueues items into the notifications_queue table for the background worker thread.
        """
        event_uuid = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        payload_str = json.dumps(payload)

        conn = self.get_db_conn()
        cursor = conn.cursor()

        # 1. Log event
        cursor.execute('''
            INSERT INTO event_logs (event_uuid, event_type, entity_type, entity_id, is_critical_sync, payload_json)
            VALUES (?, ?, ?, ?, 0, ?)
        ''', (event_uuid, event_type, entity_type, entity_id, payload_str))

        # 2. Enqueue simulated routine notifications (SMS, Email, Dashboard)
        if notifications:
            for notif in notifications:
                cursor.execute('''
                    INSERT INTO notifications_queue (recipient, recipient_role, channel, message, status, priority)
                    VALUES (?, ?, ?, ?, 'PENDING', ?)
                ''', (
                    notif.get('recipient', 'Unknown'),
                    notif.get('role', 'PATIENT'),
                    notif.get('channel', 'SMS'),
                    notif.get('message', ''),
                    notif.get('priority', 'ROUTINE')
                ))

        conn.commit()
        conn.close()

        event_obj = {
            "uuid": event_uuid,
            "type": event_type,
            "entity": entity_type,
            "id": entity_id,
            "is_critical_sync": False,
            "payload": payload,
            "timestamp": created_at
        }
        self._broadcast_to_sse(event_obj)
        return event_obj

    # -------------------------------------------------------------
    # 4. Background Async Worker Loop (Runs in Daemon Thread)
    # -------------------------------------------------------------
    def _process_async_notifications_loop(self):
        """
        Background daemon continually polling for pending notifications,
        simulating async communication delivery (SMS / Email gateway / PA announcements)
        without impeding the main HTTP triage request-response loop.
        """
        while self.async_worker_running:
            try:
                conn = self.get_db_conn()
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT id, recipient, channel, message, priority
                    FROM notifications_queue
                    WHERE status = 'PENDING'
                    ORDER BY id ASC
                    LIMIT 5
                ''')
                pending = cursor.fetchall()

                for row in pending:
                    notif_id = row['id']
                    # Simulate gateway latency (50ms - 100ms)
                    time.sleep(0.08)

                    cursor.execute('''
                        UPDATE notifications_queue
                        SET status = 'SENT', sent_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (notif_id,))
                    conn.commit()

                    # Notify SSE clients about sent notification
                    self._broadcast_to_sse({
                        "type": "NOTIFICATION_DISPATCHED",
                        "notification_id": notif_id,
                        "recipient": row['recipient'],
                        "channel": row['channel'],
                        "priority": row['priority']
                    })

                conn.close()
            except Exception as e:
                # Log worker exception without crashing daemon
                print(f"[Async Worker Error] {e}")

            time.sleep(1.5) # Poll interval
