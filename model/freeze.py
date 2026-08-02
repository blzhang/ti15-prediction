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


def freeze_predictions(src_path, out_dir, label, overwrite=False):
    """把 src_path 复制成不可变副本并记录 sha256 与 UTC 时间戳。

    存证记录同时保存绝对路径（`frozen_path`/`src`，供人工/调试直接读，语义与旧版一致）
    与「相对于记录文件所在目录」的路径（`frozen_path_rel`/`src_rel`）。相对路径是
    verify_frozen 的主验证依据——只要存证目录整体保持不变地被搬到别的地方（换目录、
    换机器、重新 clone 仓库），相对路径依旧成立，不会被误报为「被篡改」。

    overwrite=False（默认）时，若同一 label 的存证已存在（`frozen_<label>.json`
    或 `freeze_<label>.json` 任一文件已存在），拒绝覆盖并抛 FileExistsError，
    防止静默覆盖先前的证据；显式传 overwrite=True 才允许覆盖。
    """
    os.makedirs(out_dir, exist_ok=True)
    frozen_path = os.path.join(out_dir, "frozen_%s.json" % label)
    record_path = os.path.join(out_dir, "freeze_%s.json" % label)

    if not overwrite:
        existing = [p for p in (frozen_path, record_path) if os.path.exists(p)]
        if existing:
            raise FileExistsError(
                "label %r 的存证已存在，拒绝覆盖：%s"
                "（如确需覆盖旧证据，显式传 overwrite=True）"
                % (label, ", ".join(existing))
            )

    shutil.copyfile(src_path, frozen_path)

    record_dir = os.path.abspath(out_dir)
    frozen_path_abs = os.path.abspath(frozen_path)
    src_abs = os.path.abspath(src_path)
    record = {
        "label": label,
        "frozen_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": _sha256(frozen_path),
        "src": src_abs,
        "frozen_path": frozen_path_abs,
        "src_rel": os.path.relpath(src_abs, record_dir),
        "frozen_path_rel": os.path.relpath(frozen_path_abs, record_dir),
    }
    with open(record_path, "w") as f:
        json.dump(record, f, indent=1, ensure_ascii=False)
    return record


def _resolve_frozen_path(rec, record_path):
    """定位冻结副本的实际文件路径，对「存证目录整体被搬家」免疫。

    解析优先级：
    1. record_path 所在目录 + rec["frozen_path_rel"]——搬目录/换机器/新 clone 后依旧成立。
    2. rec["frozen_path"] 绝对路径——兼容没有 frozen_path_rel 字段的旧格式记录，
       或相对路径解出的文件确实不存在时的退路。
    两者都定位不到实际存在的文件时返回 None，由调用方判定为验证失败。
    """
    record_dir = os.path.dirname(os.path.abspath(record_path))
    rel = rec.get("frozen_path_rel")
    if rel:
        candidate = os.path.normpath(os.path.join(record_dir, rel))
        if os.path.exists(candidate):
            return candidate
    abs_path = rec.get("frozen_path")
    if abs_path and os.path.exists(abs_path):
        return abs_path
    return None


def verify_frozen(record_path):
    """重算冻结副本的哈希，与存证记录比对。

    路径解析见 `_resolve_frozen_path`：优先按记录文件所在目录 + 相对路径定位，
    这样即便存证目录被整体搬到新路径（换机器、重新 clone），只要内容没被改，
    仍然返回 True；内容被真的改了，无论是否搬过家，哈希不一致，返回 False。
    """
    with open(record_path) as f:
        rec = json.load(f)
    path = _resolve_frozen_path(rec, record_path)
    if path is None:
        return False
    return _sha256(path) == rec["sha256"]
