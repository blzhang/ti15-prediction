"""L5 审计层：赛前冻结存证。

设计文档 §4.5：预测产出后立即冻结 + 哈希存证，赛后才能诚实地评分。
不这么做，事后就没法证明预测是赛前做的。
"""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_predictions(src_path, out_dir, label):
    """把 src_path 复制成不可变副本并记录 sha256 与 UTC 时间戳。"""
    os.makedirs(out_dir, exist_ok=True)
    frozen_path = os.path.join(out_dir, "frozen_%s.json" % label)
    shutil.copyfile(src_path, frozen_path)
    record = {
        "label": label,
        "frozen_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": _sha256(frozen_path),
        "src": os.path.abspath(src_path),
        "frozen_path": os.path.abspath(frozen_path),
    }
    with open(os.path.join(out_dir, "freeze_%s.json" % label), "w") as f:
        json.dump(record, f, indent=1, ensure_ascii=False)
    return record


def verify_frozen(record_path):
    """重算冻结副本的哈希，与存证记录比对。"""
    with open(record_path) as f:
        rec = json.load(f)
    if not os.path.exists(rec["frozen_path"]):
        return False
    return _sha256(rec["frozen_path"]) == rec["sha256"]
