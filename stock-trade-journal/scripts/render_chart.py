#!/usr/bin/env python3
"""
Generate an annotated stock chart HTML file.

The chart template is adapted from the baijuyi_fe ECharts stock component and
kept static so the skill can render charts without running a Next.js app.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from db_schema import ensure_db, parse_ts_code


RANGE_TO_INTERVAL = {
    "1d": "1m",
    "5d": "1h",
    "1w": "1d",
    "1mo": "1d",
    "3mo": "1d",
    "6mo": "1d",
    "1y": "1d",
    "2y": "1d",
    "3y": "1d",
    "5y": "1wk",
    "10y": "1wk",
    "ytd": "1d",
    "max": "1wk",
    "trade": "1d",
}

PERIOD_ALIASES = {
    "week": "1w",
    "1week": "1w",
    "近一周": "1w",
    "一周": "1w",
    "一个月": "1mo",
    "近一个月": "1mo",
    "近一月": "1mo",
    "一月": "1mo",
    "半年": "6mo",
    "近半年": "6mo",
    "一年": "1y",
    "近一年": "1y",
    "三年": "3y",
    "近三年": "3y",
    "交易以来": "trade",
    "持仓以来": "trade",
    "since-trade": "trade",
    "since_trade": "trade",
}


def default_workspace() -> str:
    return os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal"))


def db_path_for(workspace: str) -> str:
    return os.path.join(workspace, "results", "trade-journal", "db", "trades.db")


def output_path_for(workspace: str, ts_code: str) -> str:
    safe_name = ts_code.replace("/", "_").replace(":", "_")
    return os.path.join(workspace, "results", "trade-journal", "charts", f"{safe_name}.html")


def latest_path_for(workspace: str) -> str:
    return os.path.join(workspace, "results", "trade-journal", "charts", "latest.html")


def template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "stock-chart.html"


def asset_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "echarts.min.js"


def copy_chart_assets(output: str) -> None:
    src = asset_path()
    if not src.exists():
        raise RuntimeError(f"缺少图表资源: {src}")
    assets_dir = Path(output).resolve().parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, assets_dir / "echarts.min.js")


def normalize_period(period: str) -> str:
    value = period.strip()
    normalized = PERIOD_ALIASES.get(value.lower(), PERIOD_ALIASES.get(value, value))
    if normalized not in RANGE_TO_INTERVAL:
        allowed = ", ".join(sorted(RANGE_TO_INTERVAL))
        raise RuntimeError(f"不支持的时间范围: {period}，可选: {allowed}")
    return normalized


def to_yahoo_symbol(ts_code: str, exchange: str | None = None) -> str:
    symbol, market, _ = parse_ts_code(ts_code)
    market = market.upper()
    exchange = (exchange or "").upper()

    if market == "US":
        return symbol
    if market == "HK":
        return f"{symbol.zfill(4)}.HK"
    if market == "SH":
        return f"{symbol}.SS"
    if market == "SZ":
        return f"{symbol}.SZ"
    if exchange in {"SEHK", "HKEX"}:
        return f"{symbol.zfill(4)}.HK"
    if exchange in {"SSE", "SH"}:
        return f"{symbol}.SS"
    if exchange in {"SZSE", "SZ"}:
        return f"{symbol}.SZ"
    return symbol


def parse_timestamp(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    value = value.strip()
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return value


def fetch_yahoo_ohlc(yf_symbol: str, period: str, interval: str, start: datetime | None = None) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(yf_symbol, safe="")
    query_params = {
        "interval": interval,
        "events": "history",
        "includeAdjustedClose": "true",
    }
    if start:
        query_params["period1"] = str(int(start.astimezone(timezone.utc).timestamp()))
        query_params["period2"] = str(int(datetime.now(timezone.utc).timestamp()))
    else:
        query_params["range"] = period
    query = urllib.parse.urlencode(query_params)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) stock-trade-journal/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法获取价格数据: {exc}") from exc

    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        error = data.get("chart", {}).get("error")
        raise RuntimeError(f"Yahoo 返回空数据: {error}")

    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    records: list[dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        close = closes[idx] if idx < len(closes) else None
        if close is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        records.append(
            {
                "date": dt.isoformat(),
                "open": opens[idx] if idx < len(opens) else close,
                "high": highs[idx] if idx < len(highs) else close,
                "low": lows[idx] if idx < len(lows) else close,
                "close": close,
                "volume": volumes[idx] if idx < len(volumes) else None,
            }
        )
    return records


def period_begin(period: str, start: datetime | None = None) -> str:
    if start:
        return start.strftime("%Y%m%d")
    if period == "max":
        return "19900101"
    now = datetime.now()
    days = {
        "1d": 3,
        "5d": 10,
        "1w": 10,
        "1mo": 35,
        "3mo": 100,
        "6mo": 190,
        "1y": 370,
        "2y": 740,
        "3y": 1110,
        "5y": 1850,
        "10y": 3700,
        "ytd": max(1, (now - datetime(now.year, 1, 1)).days + 5),
        "trade": 370,
    }.get(period, 190)
    return (now - timedelta(days=days)).strftime("%Y%m%d")


def period_start(period: str, local: dict[str, Any]) -> datetime | None:
    now = datetime.now(timezone.utc)
    days = {
        "1w": 10,
        "3y": 1110,
    }
    if period in days:
        return now - timedelta(days=days[period])
    if period == "trade":
        timestamps = [trade.get("timestamp") for trade in local.get("trades", []) if trade.get("timestamp")]
        parsed: list[datetime] = []
        for value in timestamps:
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed.append(dt.astimezone(timezone.utc))
            except ValueError:
                continue
        if parsed:
            return min(parsed) - timedelta(days=5)
        return now - timedelta(days=370)
    return None


def eastmoney_klt(interval: str) -> str:
    return {
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "60m": "60",
        "1h": "60",
        "1d": "101",
        "1wk": "102",
        "1mo": "103",
    }.get(interval, "101")


def fetch_eastmoney_ohlc(ts_code: str, period: str, interval: str, start: datetime | None = None) -> list[dict[str, Any]]:
    symbol, market, _ = parse_ts_code(ts_code)
    if market == "SZ":
        secid = f"0.{symbol}"
    elif market == "SH":
        secid = f"1.{symbol}"
    elif market == "HK":
        secid = f"116.{symbol.zfill(5)}"
    elif market == "US":
        secid = f"105.{symbol.upper()}"
    else:
        secid = f"105.{symbol.upper()}"

    query = urllib.parse.urlencode(
        {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": eastmoney_klt(interval),
            "fqt": "1",
            "beg": period_begin(period, start),
            "end": datetime.now().strftime("%Y%m%d"),
        }
    )
    url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) stock-trade-journal/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法获取东方财富价格数据: {exc}") from exc

    result = data.get("data") or {}
    klines = result.get("klines") or []
    if not klines:
        error = data.get("rc")
        raise RuntimeError(f"东方财富返回空数据: secid={secid}, rc={error}")
    records: list[dict[str, Any]] = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        date, open_, close, high, low, volume = parts[:6]
        records.append(
            {
                "date": datetime.fromisoformat(date).replace(tzinfo=timezone.utc).isoformat(),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": int(float(volume)),
            }
        )
    return records


def load_ohlc_json(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not isinstance(data, list):
        raise RuntimeError("OHLC JSON 必须是数组，或包含 data 数组")
    return data


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def clean_note_part(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    import_markers = ("截图导入", "导入截图", "source_images=", "raw_code=")
    if any(marker in lowered for marker in import_markers) or "导入" in text:
        pieces = []
        for piece in text.split(";"):
            item = piece.strip()
            item_lower = item.lower()
            if not item:
                continue
            if item_lower.startswith(("source_images=", "raw_code=", "name=", "source=")):
                continue
            if "截图导入" in item or "导入" in item:
                continue
            pieces.append(item)
        return "；".join(pieces)
    return text


def combine_trade_memo(note: Any, stop_loss: Any = None, take_profit: Any = None) -> str:
    parts = []
    triggers = []
    if stop_loss not in (None, ""):
        triggers.append(f"止损 {stop_loss}")
    if take_profit not in (None, ""):
        triggers.append(f"止盈 {take_profit}")
    if triggers:
        parts.append("；".join(triggers))
    parts.append(clean_note_part(note))
    return "；".join(part for part in parts if part)


def load_local_context(db_path: str, ts_code: str) -> dict[str, Any]:
    context: dict[str, Any] = {"position": None, "trades": [], "watch": None, "watchNotes": []}
    if not os.path.exists(db_path):
        return context

    conn = ensure_db(db_path)
    try:
        pos = row_to_dict(conn.execute("SELECT * FROM positions WHERE ts_code = ?", (ts_code,)).fetchone())
        if pos:
            context["position"] = {
                "exchange": pos["exchange"],
                "quantity": pos["quantity"],
                "avgCost": pos["avg_cost"],
                "totalCost": pos["total_cost"],
                "realizedPnl": pos["realized_pnl"],
                "currency": pos["currency"],
            }

        trade_rows = conn.execute(
            """
            SELECT timestamp, side, price, quantity, stop_loss, take_profit, note, source, position_after
            FROM trades
            WHERE ts_code = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (ts_code,),
        ).fetchall()
        context["trades"] = [
            {
                "timestamp": parse_timestamp(row["timestamp"]),
                "side": str(row["side"]).upper(),
                "price": row["price"],
                "quantity": row["quantity"],
                "stopLoss": row["stop_loss"],
                "takeProfit": row["take_profit"] or "",
                "note": row["note"] or "",
                "memo": combine_trade_memo(row["note"], row["stop_loss"], row["take_profit"]),
                "source": row["source"] or "",
                "positionAfter": row["position_after"],
            }
            for row in trade_rows
        ]

        watch = row_to_dict(
            conn.execute(
                "SELECT * FROM watchlist WHERE ts_code = ? AND status != 'removed'",
                (ts_code,),
            ).fetchone()
        )
        if watch:
            context["watch"] = {
                "name": watch["name"],
                "category": watch["category"],
                "targetPrice": watch["target_price"],
                "stopLoss": watch["stop_loss"],
                "priority": watch["priority"],
                "status": watch["status"],
                "note": "",
                "memo": "",
                "addedAt": parse_timestamp(watch["added_at"]),
                "updatedAt": parse_timestamp(watch["updated_at"]),
            }

        note_rows = conn.execute(
            """
            SELECT timestamp, note, source
            FROM watch_notes
            WHERE ts_code = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (ts_code,),
        ).fetchall()
        context["watchNotes"] = [
            {
                "timestamp": parse_timestamp(row["timestamp"]),
                "note": clean_note_part(row["note"]),
                "source": row["source"] or "",
            }
            for row in note_rows
            if clean_note_part(row["note"])
        ]
    finally:
        conn.close()
    return context


def render_html(payload: dict[str, Any]) -> str:
    template = template_path().read_text(encoding="utf-8")
    return (
        template.replace("{{TITLE}}", f"{payload['tsCode']} chart")
        .replace("{{PAYLOAD_JSON}}", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    )


def enrich_position_metrics(payload: dict[str, Any]) -> None:
    records = payload.get("ohlc") or []
    position = payload.get("position") or {}
    last = records[-1].get("close") if records else None
    quantity = float(position.get("quantity") or 0)
    avg_cost = position.get("avgCost")
    metrics = {
        "lastPrice": last,
        "marketValue": None,
        "unrealizedPnl": None,
        "unrealizedPnlPct": None,
    }
    if last is not None and quantity and avg_cost:
        avg = float(avg_cost)
        metrics["marketValue"] = float(last) * quantity
        metrics["unrealizedPnl"] = (float(last) - avg) * quantity
        metrics["unrealizedPnlPct"] = (float(last) / avg - 1) * 100 if avg else None
    payload["metrics"] = metrics


def write_html(output: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(render_html(payload))
    copy_chart_assets(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成带交易/关注标注的股票图表 HTML")
    parser.add_argument("ts_code", help="股票代码，如 AAPL.US, 0700.HK, 600519.SH")
    parser.add_argument("--workspace", default=default_workspace(), help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)")
    parser.add_argument("--period", default="6mo", help="价格区间: 1w/1mo/6mo/1y/3y/trade/交易以来 等")
    parser.add_argument("--interval", help="价格间隔，默认按 period 自动选择")
    parser.add_argument("--chart-type", default="area", choices=["area", "candlestick"], help="默认图表类型")
    parser.add_argument("--price-json", help="使用本地 OHLC JSON，跳过网络拉取")
    parser.add_argument("--output", "-o", help="输出 HTML 路径")
    parser.add_argument("--no-latest", action="store_true", help="不更新 charts/latest.html 固定入口")
    parser.add_argument("--name", default="", help="图表显示名称")
    args = parser.parse_args()

    workspace = os.path.expanduser(args.workspace)
    period = normalize_period(args.period)
    interval = args.interval or RANGE_TO_INTERVAL[period]
    db_path = db_path_for(workspace)
    local = load_local_context(db_path, args.ts_code)
    start = period_start(period, local)

    symbol, market, fallback_exchange = parse_ts_code(args.ts_code)
    exchange = (local["position"] or {}).get("exchange") or fallback_exchange or market
    yf_symbol = to_yahoo_symbol(args.ts_code, exchange)
    if args.price_json:
        ohlc = load_ohlc_json(args.price_json)
    else:
        ohlc = fetch_eastmoney_ohlc(args.ts_code, period, interval, start)
    if not ohlc:
        raise RuntimeError("没有可绘制的价格数据")

    output = os.path.expanduser(args.output or output_path_for(workspace, args.ts_code))

    payload = {
        "tsCode": args.ts_code,
        "symbol": symbol,
        "exchange": exchange,
        "yfSymbol": yf_symbol,
        "name": args.name or (local["watch"] or {}).get("name") or symbol,
        "period": period,
        "interval": interval,
        "chartType": args.chart_type,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ohlc": ohlc,
        "position": local["position"] or {"exchange": exchange, "quantity": 0, "avgCost": None, "totalCost": None, "realizedPnl": None, "currency": None},
        "trades": local["trades"],
        "watch": local["watch"],
        "watchNotes": local["watchNotes"],
    }
    enrich_position_metrics(payload)

    write_html(output, payload)
    if not args.no_latest:
        latest = latest_path_for(workspace)
        if Path(output).resolve() != Path(latest).resolve():
            write_html(latest, payload)

    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"生成图表失败: {exc}", file=sys.stderr)
        raise SystemExit(1)
