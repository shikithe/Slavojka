"""Offline tests: source signals only fully verified, committed-ready content."""
import base64
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from lista.notify_memarasix import (
    fingerprint, verify_source, acknowledged, relay, dispatch
)

NOW = datetime(2026,11,8,9,5,tzinfo=timezone.utc)


def docs():
    fixture={"fixture_id":"espn:football:eng.1:123", "match":"Home - Away",
             "datetime":"2026-11-08T19:00:00Z"}
    return {
        "shared/active-list.json":{
            "date":"2026-11-08","publication_allowed":True,
            "expires_at":"2026-11-09T08:59:00+01:00","fixtures":[fixture]
        },
        "shared/agent/history-h2h.json":{
            "date":"2026-11-08","fixtures":[fixture],"leagues":{"eng.1":{"teams":{}}}
        },
        "shared/kvoter/provider-offers.json":{
            "offers":[{"event_id":"1","odd":1.5}]
        },
        "shared/kvoter/matched_fixtures.json":{
            "fixtures":[{"fixture_id":"espn:football:eng.1:123"}]
        }
    }


def populated(root, objects=None):
    for name, doc in (objects or docs()).items():
        p=root/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(doc),encoding="utf-8")


def encoded(value):
    return {"encoding":"base64","content":base64.b64encode(json.dumps(value).encode()).decode()}


class ReadyRelayTests(unittest.TestCase):
    def test_source_ready_only_if_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            populated(root)
            signal=verify_source(root,NOW)
            self.assertEqual(signal["fixture_count"],1)
            self.assertEqual(signal["date"],"2026-11-08")
            self.assertEqual(len(signal["active_sha256"]),64)

    def test_unmatched_source_never_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=docs()
            rows["shared/kvoter/matched_fixtures.json"]["fixtures"]=[]
            populated(root,rows)
            with self.assertRaises(ValueError):
                verify_source(root,NOW)

    def test_expired_or_yesterday_source_never_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=docs()
            rows["shared/active-list.json"]["date"]="2026-11-07"
            populated(root,rows)
            with self.assertRaises(ValueError):
                verify_source(root,NOW)

    def test_ack_requires_matching_real_active_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            populated(root)
            signal=verify_source(root,NOW)
            active=docs()["shared/active-list.json"]
            receipt={"date":signal["date"],"active_sha256":signal["active_sha256"]}
            def requester(method,url,token,data=None):
                self.assertEqual(method,"GET")
                return encoded(receipt if "sync-receipt" in url else active)
            self.assertTrue(acknowledged(signal,"token",requester))
            active["fixtures"].append({"fixture_id":"wrong"})
            self.assertFalse(acknowledged(signal,"token",requester))

    def test_relay_retries_until_matching_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            populated(root)
            ready=verify_source(root,NOW)
            invoked=[]
            def requester(method,url,token,data=None):
                if method=="POST":
                    invoked.append(data)
                    return {}
                if "sync-receipt" in url:
                    return encoded({"date":ready["date"],"active_sha256":ready["active_sha256"]
                                   if len(invoked)>=2 else "mismatch"})
                return encoded(docs()["shared/active-list.json"])
            state=relay(root,"token",NOW,requester=requester,nap=lambda _:None,rounds=3,checks=1)
            self.assertEqual(state,"confirmed")
            self.assertEqual(len(invoked),2)
            self.assertEqual(invoked[0]["event_type"],"listasix-active-list-ready")

    def test_no_secret_fails_safe_without_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            populated(root)
            self.assertEqual(relay(root,"",NOW),"missing_credentials")


if __name__=="__main__":
    unittest.main()
