#!/usr/bin/env python3
"""
持仓分析工具 - 生成 TradingView 链接和技术分析

功能:
1. 生成 TradingView 图表链接
2. 批量打开持仓股票图表
3. 生成持仓分析报告
"""

import argparse
import os
import webbrowser
from datetime import datetime

from db_schema import ensure_db, get_positions, get_position


def convert_to_tv_symbol(ts_code: str) -> str:
    """
    将统一代码转换为 TradingView 格式

    Examples:
        AAPL.US -> NASDAQ:AAPL
        0700.HK -> HKEX:0700
        600519.SH -> SSE:600519
        000001.SZ -> SZSE:000001
        2603.HK -> HKEX:2603
    """
    parts = ts_code.rsplit('.', 1)
    if len(parts) != 2:
        return ts_code

    symbol, market = parts

    market_map = {
        'US': 'NASDAQ',  # 默认用 NASDAQ，也可能是 NYSE
        'HK': 'HKEX',
        'SH': 'SSE',
        'SZ': 'SZSE',
    }

    exchange = market_map.get(market.upper(), market)

    # 港股需要补零到4位
    if market.upper() == 'HK':
        symbol = symbol.zfill(4)

    return f"{exchange}:{symbol}"


def get_tradingview_url(ts_code: str, interval: str = "D") -> str:
    """
    生成 TradingView 图表 URL

    Args:
        ts_code: 股票代码
        interval: 时间周期 (1, 5, 15, 30, 60, 240, D, W, M)

    Returns:
        TradingView URL
    """
    tv_symbol = convert_to_tv_symbol(ts_code)
    return f"https://www.tradingview.com/chart/?symbol={tv_symbol}&interval={interval}"


def get_tradingview_widget_config(ts_code: str) -> dict:
    """生成 TradingView Widget 配置"""
    tv_symbol = convert_to_tv_symbol(ts_code)
    return {
        "symbol": tv_symbol,
        "width": "100%",
        "height": 400,
        "timezone": "Asia/Shanghai",
        "theme": "dark",
        "style": "1",  # Candles
        "locale": "zh_CN",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": False,
        "hide_side_toolbar": False,
        "allow_symbol_change": True,
        "save_image": False,
        "studies": [
            "MASimple@tv-basicstudies",
            "Volume@tv-basicstudies",
        ],
    }


def generate_analysis_report(positions: list) -> str:
    """生成持仓分析报告"""
    report = []
    report.append("# 持仓分析报告")
    report.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 统计概览
    total_cost = sum(p.get('total_cost', 0) or 0 for p in positions)
    total_pnl = sum(p.get('realized_pnl', 0) or 0 for p in positions)

    report.append("## 概览\n")
    report.append(f"- 持仓股票数: {len(positions)}")
    report.append(f"- 总成本: {total_cost:,.2f}")
    report.append(f"- 已实现盈亏: {total_pnl:+,.2f}")
    report.append("")

    # 按市场分组
    markets = {}
    for pos in positions:
        ts_code = pos['ts_code']
        market = ts_code.rsplit('.', 1)[-1] if '.' in ts_code else 'OTHER'
        if market not in markets:
            markets[market] = []
        markets[market].append(pos)

    market_names = {
        'US': '🇺🇸 美股',
        'HK': '🇭🇰 港股',
        'SH': '🇨🇳 沪市',
        'SZ': '🇨🇳 深市',
    }

    report.append("## 按市场分布\n")
    for market, pos_list in markets.items():
        market_name = market_names.get(market, market)
        market_cost = sum(p.get('total_cost', 0) or 0 for p in pos_list)
        report.append(f"- {market_name}: {len(pos_list)} 只，成本 {market_cost:,.2f}")
    report.append("")

    # 持仓详情
    report.append("## 持仓详情\n")
    report.append("| 代码 | 数量 | 均价 | 成本 | 已实现盈亏 | TradingView |")
    report.append("|------|------|------|------|------------|-------------|")

    for pos in positions:
        ts_code = pos['ts_code']
        qty = pos.get('quantity', 0)
        avg_cost = pos.get('avg_cost', 0) or 0
        total_cost = pos.get('total_cost', 0) or 0
        pnl = pos.get('realized_pnl', 0) or 0
        tv_url = get_tradingview_url(ts_code)

        pnl_str = f"{pnl:+,.2f}" if pnl else "-"
        report.append(f"| {ts_code} | {qty:,} | {avg_cost:.2f} | {total_cost:,.2f} | {pnl_str} | [📈 图表]({tv_url}) |")

    report.append("")

    # TradingView 链接汇总
    report.append("## TradingView 快捷链接\n")
    for pos in positions:
        ts_code = pos['ts_code']
        tv_symbol = convert_to_tv_symbol(ts_code)
        tv_url = get_tradingview_url(ts_code)
        report.append(f"- [{ts_code}]({tv_url}) → `{tv_symbol}`")

    return "\n".join(report)


def open_tradingview_charts(positions: list, interval: str = "D", max_tabs: int = 5):
    """批量打开 TradingView 图表"""
    print(f"打开 TradingView 图表 (最多 {max_tabs} 个)...\n")

    opened = 0
    for pos in positions[:max_tabs]:
        ts_code = pos['ts_code']
        url = get_tradingview_url(ts_code, interval)
        tv_symbol = convert_to_tv_symbol(ts_code)

        print(f"  📈 {ts_code} → {tv_symbol}")
        webbrowser.open(url)
        opened += 1

    if len(positions) > max_tabs:
        print(f"\n  (还有 {len(positions) - max_tabs} 只股票未打开，使用 --max-tabs 增加)")

    print(f"\n✅ 已打开 {opened} 个图表")


def main():
    parser = argparse.ArgumentParser(description="持仓分析工具")
    parser.add_argument("--workspace", required=True, help="工作目录")

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # tradingview 命令
    tv_parser = subparsers.add_parser("tradingview", aliases=["tv"], help="打开 TradingView 图表")
    tv_parser.add_argument("--ts-code", help="指定股票代码")
    tv_parser.add_argument("--interval", default="D", help="时间周期 (1,5,15,30,60,240,D,W,M)")
    tv_parser.add_argument("--max-tabs", type=int, default=5, help="最多打开标签数")
    tv_parser.add_argument("--all", action="store_true", help="打开所有持仓")

    # report 命令
    report_parser = subparsers.add_parser("report", help="生成分析报告")
    report_parser.add_argument("--output", "-o", help="输出文件路径")

    # link 命令
    link_parser = subparsers.add_parser("link", help="显示 TradingView 链接")
    link_parser.add_argument("--ts-code", help="指定股票代码")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 连接数据库
    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")

    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        return

    conn = ensure_db(db_path)
    positions = get_positions(conn)
    conn.close()

    if not positions:
        print("无持仓数据")
        return

    # 执行命令
    if args.command in ("tradingview", "tv"):
        if args.ts_code:
            # 打开单个股票
            url = get_tradingview_url(args.ts_code, args.interval)
            print(f"打开: {args.ts_code} → {convert_to_tv_symbol(args.ts_code)}")
            webbrowser.open(url)
        else:
            # 打开持仓股票
            max_tabs = len(positions) if args.all else args.max_tabs
            open_tradingview_charts(positions, args.interval, max_tabs)

    elif args.command == "report":
        report = generate_analysis_report(positions)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"报告已保存: {args.output}")
        else:
            print(report)

    elif args.command == "link":
        if args.ts_code:
            url = get_tradingview_url(args.ts_code)
            tv_symbol = convert_to_tv_symbol(args.ts_code)
            print(f"{args.ts_code} → {tv_symbol}")
            print(f"URL: {url}")
        else:
            print("TradingView 链接:\n")
            for pos in positions:
                ts_code = pos['ts_code']
                tv_symbol = convert_to_tv_symbol(ts_code)
                url = get_tradingview_url(ts_code)
                print(f"  {ts_code:<12} → {tv_symbol:<15} {url}")


if __name__ == "__main__":
    main()
