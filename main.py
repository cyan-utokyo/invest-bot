import akshare as ak
import pandas as pd
import requests
import os
from datetime import datetime

TG_TOKEN = os.getenv("TG_TOKEN", "你的TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "你的CHAT_ID")

# ================= 辅助：格式化变动 =================
def format_change(current, prev):
    if prev == 0: return ""
    diff = current - prev
    sign = "+" if diff > 0 else ""
    arrow = "⬆️" if diff > 0 else "⬇️"
    if abs(diff) < 0.001: return "(持平)"
    return f"({arrow}{sign}{round(diff, 2)})"

def get_data():
    report = {}
    print("🚀 开始抓取数据 (v10.0 全参数透明版)...")
    
    # --- 1. 汇率 ---
    try:
        df_fx = ak.forex_spot_em()
        target = df_fx[df_fx['名称'] == '美元兑人民币']
        if target.empty: target = df_fx[df_fx['名称'] == '美元兑离岸人民币']
        if not target.empty:
            report['usd_cny'] = float(target.iloc[0]['最新价'])
        else: report['usd_cny'] = 0
    except: report['usd_cny'] = 0

    # --- 2. 国债 ---
    try:
        bond_df = ak.bond_zh_us_rate()
        target_col = '中国国债收益率10年'
        if target_col not in bond_df.columns:
            target_col = [c for c in bond_df.columns if '中国' in c and '10年' in c][0]
        if '日期' in bond_df.columns:
            bond_df['日期'] = pd.to_datetime(bond_df['日期'])
            bond_df.sort_values('日期', inplace=True)
        
        cn_10y = float(bond_df.iloc[-1][target_col])
        cn_10y_prev = float(bond_df.iloc[-6][target_col]) if len(bond_df) > 5 else cn_10y
        
        report['bond_10y'] = cn_10y
        report['bond_change'] = format_change(cn_10y, cn_10y_prev)
    except: 
        report['bond_10y'] = 0
        report['bond_change'] = ""

    # --- 3. 指数估值 (全参数抓取) ---
    indices = {"000510": "a500", "H30269": "low"}
    
    for code, name in indices.items():
        try:
            print(f"正在获取 {name}...")
            df = ak.stock_zh_index_value_csindex(symbol=code)
            if df.empty: continue
            
            if '日期' in df.columns:
                df['日期'] = pd.to_datetime(df['日期'])
                df.sort_values('日期', inplace=True)
            
            # 切片：今天 vs 上周
            latest = df.iloc[-1]
            prev = df.iloc[-6] if len(df) > 6 else latest

            # 📥 【核心修改】全部抓取，一个不漏
            # 1. 股息率 (Div)
            div1 = float(latest.get('股息率1', 0)) # 全市值
            div2 = float(latest.get('股息率2', 0)) # 流通
            div2_prev = float(prev.get('股息率2', 0)) # 用于算趋势
            
            # 2. 市盈率 (PE)
            pe1 = float(latest.get('市盈率1', 0)) # 全市值
            pe2 = float(latest.get('市盈率2', 0)) # 流通

            # 存入字典
            report[f'{name}_div1'] = div1
            report[f'{name}_div2'] = div2
            report[f'{name}_pe1'] = pe1
            report[f'{name}_pe2'] = pe2
            
            # 计算主要指标的周变化 (红利看div2变化，A500看div1变化)
            if name == "low":
                report[f'{name}_trend'] = format_change(div2, div2_prev)
            else:
                div1_prev = float(prev.get('股息率1', 0))
                report[f'{name}_trend'] = format_change(div1, div1_prev)
            
            # 3. 算分位 (红利低波算 PE2 的分位)
            if name == "low":
                target_pe_col = '市盈率2' if '市盈率2' in df.columns else '市盈率1'
                target_pe_val = pe2 if pe2 > 0 else pe1
                if target_pe_col in df.columns:
                    all_pes = df[target_pe_col].astype(float).dropna().sort_values().values
                    rank = pd.Series(all_pes).searchsorted(target_pe_val)
                    report[f'{name}_pe_rank'] = round((rank / len(all_pes)) * 100, 2)
            
        except Exception as e:
            print(f"❌ {name} 失败: {e}")

    return report

def generate_message(data):
    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"📅 *投资早报 {today}*\n"
    msg += "------------------------\n"
    
    # 1. 基准
    bond = data.get('bond_10y', 0)
    bond_chg = data.get('bond_change', '')
    fx = data.get('usd_cny', 0)
    
    msg += f"🏦 *宏观基准锚点*\n"
    msg += f"• 10年期国债：`{bond}%` {bond_chg}\n"
    msg += f"• 美元兑人民币：`{fx}`\n\n"

    # 2. A500
    if 'a500_div1' in data:
        div1 = data['a500_div1']
        div2 = data['a500_div2']
        pe1 = data['a500_pe1']
        trend = data.get('a500_trend', '')
        spread = round(div1 - bond, 2)
        
        # 🟢 明确的操作指令转化
        if spread >= 1.0:
            action = "🟢 【建议买入/定投】股息显著跑赢国债，加仓性价比高"
        elif spread >= 0:
            action = "🟡 【安心持有】处于相对舒适区，维持现有仓位"
        else:
            action = "🔴 【暂缓买入/观望】股息不及无风险利率，吸引力偏低"
        
        msg += f"🛡️ *中证A500 (000510)*\n"
        msg += f"• 股息(全)：`{div1}%` {trend}\n"
        msg += f"• PE(全)：`{pe1}`\n"
        msg += f"• 股债利差：`{spread}%`\n"
        msg += f"• 💡 核心策略：*{action}*\n\n"

    # 3. 红利低波
    if 'low_div2' in data:
        div1 = data['low_div1'] 
        div2 = data['low_div2'] 
        pe1 = data['low_pe1']
        pe2 = data['low_pe2']
        trend = data.get('low_trend', '')
        pe_rank = data.get('low_pe_rank', 0)
        
        # 🟢 明确的操作指令转化
        if div2 >= 5.0 and pe_rank < 50: 
            action = "🟢 【积极买入】高分红且未拥挤，安全垫极厚"
        elif div2 >= 4.5: 
            action = "🟡 【安心持有】分红回报正常，适合继续拿分红"
        elif div2 < 4.5 and pe_rank > 70:
            action = "🔴 【暂停买入】赛道拥挤，PE分位过高，停止加仓"
        else: 
            action = "🟡 【维持持有】处于历史均值附近，多看少动"

        msg += f"💰 *红利低波 (H30269)*\n"
        msg += f"• 股息(流)：`{div2}%` {trend} 👈真实回报\n"
        msg += f"• PE(流)：`{pe2}` (历史分位 `{pe_rank}%`)\n"
        msg += f"• 💡 核心策略：*{action}*\n"

    return msg

def send_telegram(text):
    if not TG_TOKEN: return
    print(f"🤖 准备推送... (Token长度: {len(TG_TOKEN)})")
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try: 
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"❌ 发送失败: {resp.text}")
    except Exception as e: 
        print(f"💥 网络错误: {e}")

if __name__ == "__main__":
    data = get_data()
    msg = generate_message(data)
    print("\n" + "="*20)
    print(msg)
    print("="*20 + "\n")
    send_telegram(msg)