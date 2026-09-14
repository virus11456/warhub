"""Read-only receipt diagnostics. No credentials, network, or notification imports."""
import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from collection_guard import MIN_INTERVAL_SECONDS


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except (AttributeError, ValueError, TypeError):
        return None


def last_success(previous, now):
    value = timestamp(previous.get('digest_success_at'))
    delivery = previous.get('delivery') or {}
    if value is None and isinstance(delivery, dict):
        results = delivery.get('digest')
        if isinstance(results, dict) and results and all(v is True for v in results.values()):
            value = timestamp(delivery.get('checked_at'))
    return value.isoformat() if value is not None and value <= now else None


def snapshot_reason(snapshot, now):
    if not isinstance(snapshot, dict):
        return 'invalid_snapshot'
    observed = timestamp(snapshot.get('updated_at'))
    if observed is None:
        return 'invalid_observation_time'
    age = (now - observed).total_seconds()
    if age < 0:
        return 'future_observation'
    if age >= MIN_INTERVAL_SECONDS:
        return 'stale_snapshot'
    previous = snapshot.get('_notify') or {}
    if not isinstance(previous, dict):
        return 'invalid_receipts'
    delivered = timestamp(previous.get('digest_snapshot_at'))
    if delivered is None:
        delivery = previous.get('delivery') or {}
        if not isinstance(delivery, dict) or not isinstance(delivery.get('digest') or {}, dict):
            return 'invalid_receipts'
        results = delivery.get('digest') or {}
        if results and all(v is True for v in results.values()):
            delivered = timestamp(delivery.get('checked_at'))
    return 'already_delivered' if delivered and observed <= delivered else 'ready'


LABELS = {
    'invalid_snapshot': '快照格式無效', 'invalid_observation_time': '觀測時間缺少或無效',
    'future_observation': '觀測時間在未來', 'stale_snapshot': '快照已滿 110 分鐘，不補送舊摘要',
    'invalid_receipts': '回條格式無效', 'already_delivered': '同一份快照已成功通知',
    'ready': '快照可供摘要判斷；不代表已發送',
}


def report(snapshot, now, quiet=False, hours=1):
    reason = snapshot_reason(snapshot, now)
    data = snapshot if isinstance(snapshot, dict) else {}
    previous = data.get('_notify') or {}
    previous = previous if isinstance(previous, dict) else {}
    observed = timestamp(data.get('updated_at'))
    success = last_success(previous, now)
    delivery = previous.get('delivery') or {}
    delivery = delivery if isinstance(delivery, dict) else {}
    results = delivery.get('digest') or {}
    results = results if isinstance(results, dict) else {}
    checked = timestamp(delivery.get('checked_at'))
    retry = previous.get('telegram_retry_at')
    limited = type(retry) in (int, float) and math.isfinite(retry) and retry > now.timestamp()
    bucket = int(now.timestamp() // 3600) // max(1, hours)
    dedup = previous.get('bucket') == bucket and previous.get('delivery_version') == 1
    outcome = ('全部成功' if all(v is True for v in results.values()) else
               '部分成功' if any(v is True for v in results.values()) else '未成功') if results else '沒有發送結果；不能視為成功'
    lines = ['### 通知狀態（現有回條，唯讀）',
             '- 檢查時間：' + now.isoformat(),
             '- 原觀測時間：' + (observed.isoformat() if observed else '未知'),
             '- 最後可核實的摘要全部成功時間：' + (success or '未知；不補造'),
             '- 距最後成功：' + (str(int((now - timestamp(success)).total_seconds() // 60)) + ' 分鐘' if success else '未知'),
             '- 快照判斷：' + LABELS[reason],
             '- 本輪安靜模式：' + ('啟用' if quiet else '未啟用'),
             '- 摘要去重時段：' + str(hours) + ' 小時；本時段' + ('已完成' if dedup else '尚無完成紀錄'),
             '- Telegram 冷卻：' + ('尚餘約 ' + str(math.ceil(retry - now.timestamp())) + ' 秒' if limited else '無有效的等待中紀錄'),
             '- 最近回條檢查：' + (checked.isoformat() if checked else '未知') + '；' + outcome,
             '- 成功／未成功目的地數：' + str(sum(v is True for v in results.values())) + '／' + str(sum(v is not True for v in results.values())),
             '\n以上為目前檔案的回條，不代表本次工作流程已送達或回條已提交成功。未成功不等於已被 Telegram 封鎖。',
             '去重時段不是定時器；排程延遲時不保證每小時送達。收集與通知備援需另查工作流程執行紀錄。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='data/data.json')
    args = parser.parse_args()
    try:
        snapshot = json.loads(Path(args.data).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        snapshot = None
    try:
        hours = max(1, int(os.environ.get('DIGEST_EVERY_HOURS') or 1))
    except ValueError:
        hours = 1
    content = report(snapshot, datetime.now(timezone.utc), os.environ.get('WARHUB_NO_NOTIFY') == '1', hours)
    print(content)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write(content)


if __name__ == '__main__':
    main()
