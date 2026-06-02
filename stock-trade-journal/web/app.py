#!/usr/bin/env python3
"""
交易日志 Web 界面

启动方式:
  python3 web/app.py

然后访问: http://localhost:5000
"""

import argparse
import os
import sys
import json
from datetime import datetime

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from flask import Flask, render_template_string, jsonify, request
from db_schema import ensure_db, get_positions, get_position

app = Flask(__name__)
DB_PATH = None

# HTML 模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📒 交易日志</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            text-align: center;
            padding: 30px 0;
        }
        header h1 {
            font-size: 2.5em;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }
        header p {
            color: #888;
            font-size: 1.1em;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .stat-card .value {
            font-size: 2.2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .stat-card .label {
            color: #888;
            font-size: 0.9em;
        }
        .stat-card.positive .value { color: #00d26a; }
        .stat-card.negative .value { color: #ff6b6b; }
        .stat-card.neutral .value { color: #00d4ff; }

        .section {
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 30px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .section h2 {
            font-size: 1.5em;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section h2 .icon {
            font-size: 1.2em;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th {
            background: rgba(255,255,255,0.05);
            font-weight: 600;
            color: #00d4ff;
            position: sticky;
            top: 0;
        }
        tr:hover {
            background: rgba(255,255,255,0.03);
        }
        .positive { color: #00d26a; }
        .negative { color: #ff6b6b; }
        .buy-badge {
            background: linear-gradient(135deg, #00d26a, #00a854);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }
        .sell-badge {
            background: linear-gradient(135deg, #ff6b6b, #ee5a5a);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }

        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab {
            padding: 12px 24px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 1em;
            color: #888;
        }
        .tab:hover {
            background: rgba(255,255,255,0.1);
        }
        .tab.active {
            background: linear-gradient(135deg, #00d4ff, #7b2cbf);
            color: white;
            border-color: transparent;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }

        .refresh-btn {
            position: fixed;
            bottom: 30px;
            right: 30px;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, #00d4ff, #7b2cbf);
            border: none;
            color: white;
            font-size: 1.5em;
            cursor: pointer;
            box-shadow: 0 5px 20px rgba(0,212,255,0.4);
            transition: transform 0.3s;
        }
        .refresh-btn:hover {
            transform: scale(1.1);
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        .empty-state .icon {
            font-size: 4em;
            margin-bottom: 20px;
        }

        .chart-container {
            height: 300px;
            background: rgba(0,0,0,0.2);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #666;
        }

        @media (max-width: 768px) {
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            th, td {
                padding: 10px 8px;
                font-size: 0.9em;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📒 交易日志</h1>
            <p>实时查看持仓和交易记录</p>
        </header>

        <div class="stats-grid" id="stats-grid">
            <!-- 动态加载 -->
        </div>

        <div class="tabs">
            <button class="tab active" onclick="switchTab('positions')">📊 持仓</button>
            <button class="tab" onclick="switchTab('trades')">📝 交易记录</button>
        </div>

        <div id="positions" class="tab-content active">
            <div class="section">
                <h2><span class="icon">📊</span> 当前持仓</h2>
                <div id="positions-table"></div>
            </div>
        </div>

        <div id="trades" class="tab-content">
            <div class="section">
                <h2><span class="icon">📝</span> 交易记录</h2>
                <div id="trades-table"></div>
            </div>
        </div>
    </div>

    <button class="refresh-btn" onclick="loadData()" title="刷新数据">🔄</button>

    <script>
        function formatNumber(num, decimals = 2) {
            if (num === null || num === undefined) return '-';
            return Number(num).toLocaleString('zh-CN', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            });
        }

        function formatPnL(num) {
            if (num === null || num === undefined || num === 0) return '-';
            const formatted = formatNumber(Math.abs(num));
            return num >= 0 ? `+${formatted}` : `-${formatted}`;
        }

        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
            document.getElementById(tabName).classList.add('active');
        }

        async function loadData() {
            try {
                // 加载统计数据
                const statsRes = await fetch('/api/stats');
                const stats = await statsRes.json();
                renderStats(stats);

                // 加载持仓
                const posRes = await fetch('/api/positions');
                const positions = await posRes.json();
                renderPositions(positions);

                // 加载交易记录
                const tradesRes = await fetch('/api/trades?limit=50');
                const trades = await tradesRes.json();
                renderTrades(trades);
            } catch (e) {
                console.error('加载数据失败:', e);
            }
        }

        function renderStats(stats) {
            const grid = document.getElementById('stats-grid');
            const pnlClass = stats.total_realized_pnl >= 0 ? 'positive' : 'negative';

            grid.innerHTML = `
                <div class="stat-card neutral">
                    <div class="value">${stats.position_count}</div>
                    <div class="label">持仓股票数</div>
                </div>
                <div class="stat-card neutral">
                    <div class="value">${formatNumber(stats.total_cost, 0)}</div>
                    <div class="label">总成本</div>
                </div>
                <div class="stat-card ${pnlClass}">
                    <div class="value">${formatPnL(stats.total_realized_pnl)}</div>
                    <div class="label">已实现盈亏</div>
                </div>
                <div class="stat-card neutral">
                    <div class="value">${stats.trade_count}</div>
                    <div class="label">交易笔数</div>
                </div>
            `;
        }

        function renderPositions(positions) {
            const container = document.getElementById('positions-table');

            if (!positions || positions.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">📭</div>
                        <p>暂无持仓数据</p>
                    </div>
                `;
                return;
            }

            let html = `
                <table>
                    <thead>
                        <tr>
                            <th>代码</th>
                            <th>交易所</th>
                            <th>持仓</th>
                            <th>均价</th>
                            <th>总成本</th>
                            <th>已实现盈亏</th>
                            <th>最后交易</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            for (const pos of positions) {
                const pnlClass = (pos.realized_pnl || 0) >= 0 ? 'positive' : 'negative';
                const lastDate = pos.last_trade_date ? pos.last_trade_date.substring(0, 10) : '-';

                html += `
                    <tr>
                        <td><strong>${pos.ts_code}</strong></td>
                        <td>${pos.exchange || '-'}</td>
                        <td>${formatNumber(pos.quantity, 0)}</td>
                        <td>${formatNumber(pos.avg_cost, 4)}</td>
                        <td>${formatNumber(pos.total_cost, 2)}</td>
                        <td class="${pnlClass}">${formatPnL(pos.realized_pnl)}</td>
                        <td>${lastDate}</td>
                    </tr>
                `;
            }

            html += '</tbody></table>';
            container.innerHTML = html;
        }

        function renderTrades(trades) {
            const container = document.getElementById('trades-table');

            if (!trades || trades.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">📭</div>
                        <p>暂无交易记录</p>
                    </div>
                `;
                return;
            }

            let html = `
                <table>
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>代码</th>
                            <th>交易所</th>
                            <th>方向</th>
                            <th>价格</th>
                            <th>数量</th>
                            <th>金额</th>
                            <th>来源</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            for (const trade of trades) {
                const badgeClass = trade.side === 'BUY' ? 'buy-badge' : 'sell-badge';
                const sideText = trade.side === 'BUY' ? '买入' : '卖出';
                const time = trade.timestamp ? trade.timestamp.substring(0, 16).replace('T', ' ') : '-';
                const amount = trade.amount || (trade.price * trade.quantity);
                const source = trade.source === 'ibkr' ? 'IBKR' : '手动';

                html += `
                    <tr>
                        <td>${time}</td>
                        <td><strong>${trade.ts_code}</strong></td>
                        <td>${trade.exchange || '-'}</td>
                        <td><span class="${badgeClass}">${sideText}</span></td>
                        <td>${formatNumber(trade.price, 4)}</td>
                        <td>${formatNumber(trade.quantity, 0)}</td>
                        <td>${formatNumber(amount, 2)}</td>
                        <td>${source}</td>
                    </tr>
                `;
            }

            html += '</tbody></table>';
            container.innerHTML = html;
        }

        // 初始加载
        loadData();

        // 每30秒自动刷新
        setInterval(loadData, 30000);
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/stats')
def api_stats():
    conn = ensure_db(DB_PATH)

    # 持仓统计
    cursor = conn.execute("""
        SELECT
            COUNT(*) as position_count,
            COALESCE(SUM(total_cost), 0) as total_cost,
            COALESCE(SUM(realized_pnl), 0) as total_realized_pnl
        FROM positions WHERE quantity != 0
    """)
    pos_stats = cursor.fetchone()

    # 交易统计
    cursor = conn.execute("SELECT COUNT(*) FROM trades")
    trade_count = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        'position_count': pos_stats[0],
        'total_cost': pos_stats[1],
        'total_realized_pnl': pos_stats[2],
        'trade_count': trade_count
    })


@app.route('/api/positions')
def api_positions():
    conn = ensure_db(DB_PATH)
    include_zero = request.args.get('all', 'false').lower() == 'true'
    positions = get_positions(conn, include_zero=include_zero)
    conn.close()
    return jsonify(positions)


@app.route('/api/trades')
def api_trades():
    conn = ensure_db(DB_PATH)
    limit = request.args.get('limit', 50, type=int)
    ts_code = request.args.get('ts_code')

    if ts_code:
        cursor = conn.execute(
            "SELECT * FROM trades WHERE ts_code = ? ORDER BY timestamp DESC LIMIT ?",
            (ts_code, limit)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )

    columns = [description[0] for description in cursor.description]
    trades = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    return jsonify(trades)


@app.route('/api/position/<ts_code>')
def api_position_detail(ts_code):
    conn = ensure_db(DB_PATH)
    position = get_position(conn, ts_code)
    conn.close()

    if position:
        return jsonify(position)
    else:
        return jsonify({'error': 'Not found'}), 404


def main():
    global DB_PATH

    parser = argparse.ArgumentParser(description="交易日志 Web 界面")
    parser.add_argument(
        "--workspace",
        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal")),
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )
    parser.add_argument("--port", type=int, default=5000, help="端口号 (默认: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="主机 (默认: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    DB_PATH = os.path.join(args.workspace, "results", "trade-journal", "db", "trades.db")

    if not os.path.exists(DB_PATH):
        print(f"数据库不存在: {DB_PATH}")
        print("请先记录交易或同步 IBKR 数据")
        return

    print(f"📒 交易日志 Web 界面")
    print(f"   数据库: {DB_PATH}")
    print(f"   访问: http://{args.host}:{args.port}")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
