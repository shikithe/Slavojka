import base64
import json
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from lista.notify_memarasix_expiry import local_day, relay, acknowledged

SAR = ZoneInfo("Europe/Sarajevo")
WHEN = datetime(2026,11,9,8,56,tzinfo=SAR)

class ExpiryRelayTest(unittest.TestCase):
    def test_before_0855_no_signal(self):
        def nope(*args):
            raise AssertionError("No GitHub requests expected before 08:55")
        self.assertIsNone(local_day(datetime(2026,11,9,8,54,tzinfo=SAR)))
        self.assertEqual(relay("test",datetime(2026,11,9,8,54,tzinfo=SAR),nope),"not_due")

    def test_one_dispatch_when_ack_missing(self):
        calls=[]
        def fake(method,url,token,data=None):
            calls.append((method,url,data))
            if method=="GET":
                return {"encoding":"base64","content":base64.b64encode(json.dumps({"date":"2026-11-08","status":"expired_previous_day"}).encode()).decode()}
            if method=="POST":
                return {}
        self.assertEqual(relay("test",WHEN,fake),"dispatched")
        sent=[x for x in calls if x[0]=="POST"]
        self.assertEqual(len(sent),1)
        self.assertEqual(sent[0][2]["event_type"],"listasix-expire-import")
        self.assertEqual(sent[0][2]["client_payload"]["date"],"2026-11-09")

    def test_ack_prevents_duplicate_dispatch(self):
        def fake(method,url,token,data=None):
            if method!="GET":
                raise AssertionError("Not allowed to dispatch after ack")
            payload={"date":"2026-11-09","status":"expired_previous_day"}
            return {"encoding":"base64","content":base64.b64encode(json.dumps(payload).encode()).decode()}
        self.assertEqual(relay("test",WHEN,fake),"confirmed")

    def test_missing_token_no_dispatch(self):
        self.assertEqual(relay("",WHEN),"missing_token")

    def test_wrong_date_ack_not_confirmed(self):
        def fake(method,url,token,data=None):
            return {"encoding":"base64","content":base64.b64encode(json.dumps({"date":"2026-11-08","status":"expired_previous_day"}).encode()).decode()}
        self.assertFalse(acknowledged("2026-11-09","test",fake))

if __name__=="__main__":
    unittest.main()
