import json, os, shutil, tempfile
import pytest
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


def test_verify_frozen_survives_directory_move():
    """存证目录被整体搬到新位置（等价于换机器重新 clone 仓库）后，
    内容未被篡改，verify_frozen 必须仍返回 True——不能把「搬家」误报成「被篡改」。
    """
    base = tempfile.mkdtemp()
    try:
        src = os.path.join(base, "pred.json")
        json.dump({"champion": {"A": 0.6, "B": 0.4}}, open(src, "w"))

        out_dir = os.path.join(base, "frozen_orig")
        freeze_predictions(src, out_dir, label="move-test")

        # 整个存证目录搬到一个新的绝对路径下（模拟搬目录/换机器/新 clone）
        moved_dir = os.path.join(base, "relocated", "frozen_moved")
        os.makedirs(os.path.dirname(moved_dir), exist_ok=True)
        shutil.move(out_dir, moved_dir)

        record_path = os.path.join(moved_dir, "freeze_move-test.json")
        assert verify_frozen(record_path) is True
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_verify_frozen_detects_tamper_after_move():
    """搬家之后如果冻结副本内容真的被改了，verify_frozen 必须仍能测出来——
    确保迁移修复没有把校验削弱成「只要文件存在就永远 True」。
    """
    base = tempfile.mkdtemp()
    try:
        src = os.path.join(base, "pred.json")
        json.dump({"champion": {"A": 1.0}}, open(src, "w"))

        out_dir = os.path.join(base, "frozen_orig")
        rec = freeze_predictions(src, out_dir, label="move-tamper")

        moved_dir = os.path.join(base, "relocated", "frozen_moved")
        os.makedirs(os.path.dirname(moved_dir), exist_ok=True)
        shutil.move(out_dir, moved_dir)

        moved_frozen_file = os.path.join(moved_dir, os.path.basename(rec["frozen_path"]))
        with open(moved_frozen_file, "w") as f:
            f.write('{"champion": {"A": 0.42}}')

        record_path = os.path.join(moved_dir, "freeze_move-tamper.json")
        assert verify_frozen(record_path) is False
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_freeze_predictions_refuses_overwrite_by_default():
    """同一个 label 重复冻结，默认必须拒绝——防止静默覆盖先前的存证。"""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "pred.json")
        json.dump({"champion": {"A": 0.5, "B": 0.5}}, open(src, "w"))
        freeze_predictions(src, d, label="dup")

        with pytest.raises(FileExistsError) as exc_info:
            freeze_predictions(src, d, label="dup")

        msg = str(exc_info.value)
        assert "dup" in msg
        assert "frozen_dup.json" in msg or "freeze_dup.json" in msg

        # 拒绝覆盖时，原有证据必须原封不动
        assert verify_frozen(os.path.join(d, "freeze_dup.json")) is True


def test_freeze_predictions_allows_overwrite_when_explicit():
    """显式传 overwrite=True 才允许覆盖同 label 的旧存证。"""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "pred.json")
        json.dump({"champion": {"A": 0.5, "B": 0.5}}, open(src, "w"))
        rec1 = freeze_predictions(src, d, label="dup2")

        json.dump({"champion": {"A": 0.9, "B": 0.1}}, open(src, "w"))
        rec2 = freeze_predictions(src, d, label="dup2", overwrite=True)

        assert rec2["sha256"] != rec1["sha256"]
        assert verify_frozen(os.path.join(d, "freeze_dup2.json")) is True
