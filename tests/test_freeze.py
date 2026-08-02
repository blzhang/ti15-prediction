import json, os, tempfile
from model.freeze import freeze_predictions, verify_frozen


def test_freeze_records_hash_and_is_verifiable():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "pred.json")
        json.dump({"champion": {"A": 0.5, "B": 0.5}}, open(src, "w"))
        rec = freeze_predictions(src, d, label="test-run")

        assert rec["label"] == "test-run"
        assert len(rec["sha256"]) == 64
        assert rec["frozen_at_utc"].endswith("Z")
        assert os.path.exists(rec["frozen_path"])
        assert verify_frozen(os.path.join(d, "freeze_test-run.json")) is True


def test_verify_fails_when_frozen_copy_tampered():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "pred.json")
        json.dump({"champion": {"A": 1.0}}, open(src, "w"))
        rec = freeze_predictions(src, d, label="t2")
        with open(rec["frozen_path"], "w") as f:
            f.write('{"champion": {"A": 0.9}}')
        assert verify_frozen(os.path.join(d, "freeze_t2.json")) is False
