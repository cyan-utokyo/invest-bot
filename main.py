import akshare as ak
import pandas as pd
import requests
import os
from datetime import datetime

TG_TOKEN = os.getenv("TG_TOKEN", "你的TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "你的CHAT_ID")

# TG_TOKEN = "8326935411:AAGaZYUCPo-LhyGADq5_dG0ylENi8ZYgkIs"          # Replace with your bot token
# CHAT_ID = "8269128724"                       # Replace with your chat ID

def get_data():
    report = {}
    print("🚀 开始抓取数据 (v7.0 混合双打版)...")
    
    # --- 1. 汇率 ---
    try:
        print("正在获取汇率...")
        df_fx = ak.forex_spot_em()
        target = df_fx[df_fx['名称'] == '美元兑人民币']
        if target.empty: target = df_fx[df_fx['名称'] == '美元兑离岸人民币']
        
        if not target.empty:
            price = float(target.iloc[0]['最新价'])
            report['usd_cny'] = price
            print(f"✅ 汇率: {price}")
        else: raise ValueError("未找到美元兑人民币")
    except Exception as e:
        print(f"❌ 汇率失败: {e}")
        report['usd_cny'] = 0

    # --- 2. 国债 ---
    try:
        print("正在获取国债...")
        bond_df = ak.bond_zh_us_rate()
        target_col = '中国国债收益率10年'
        if target_col not in bond_df.columns:
            target_col = [c for c in bond_df.columns if '中国' in c and '10年' in c][0]
        if '日期' in bond_df.columns:
            bond_df['日期'] = pd.to_datetime(bond_df['日期'])
            bond_df.sort_values('日期', inplace=True)
        cn_10y = bond_df.iloc[-1][target_col]
        report['bond_10y'] = float(cn_10y)
        print(f"✅ 国债: {cn_10y}%")
    except Exception as e:
        print(f"❌ 国债失败: {e}")
        report['bond_10y'] = 0

    # --- 3. 指数估值 (核心逻辑分叉) ---
    indices = {
        "000510": "a500", 
        "H30269": "low"
    }
    
    for code, name in indices.items():
        try:
            print(f"正在获取 {name} ({code})...")
            df = ak.stock_zh_index_value_csindex(symbol=code)
            if df.empty: continue
            
            if '日期' in df.columns:
                df['日期'] = pd.to_datetime(df['日期'])
                df.sort_values('日期', inplace=True)
            
            latest = df.iloc[-1]
            
            # ==========================================
            # 🧠 智能决策区：根据指数特性选择口径
            # ==========================================
            if name == "low": 
                # 红利低波：看重流通盘交易价值，优先用 '2'
                div_key = '股息率2' if '股息率2' in latest else '股息率1'
                pe_key = '市盈率2' if '市盈率2' in latest else '市盈率1'
                print(f"   👉 {name} 策略: 采用流通口径 (Suffix 2)")
            else:
                # A500：看重宏观整体回报，优先用 '1' (总股本)
                div_key = '股息率1'
                pe_key = '市盈率1'
                print(f"   👉 {name} 策略: 采用全市值口径 (Suffix 1)")
            # ==========================================

            div = float(latest.get(div_key, 0))
            pe = float(latest.get(pe_key, 0))
            
            report[f'{name}_div'] = div
            report[f'{name}_pe'] = pe
            
            # 算 PE 分位 (用相同的 key 对比历史)
            if name == "low":
                if pe_key in df.columns:
                    all_pes = df[pe_key].astype(float).dropna().sort_values().values
                    rank = pd.Series(all_pes).searchsorted(pe)
                    percentile = (rank / len(all_pes)) * 100
                    report[f'{name}_pe_rank'] = round(percentile, 2)
            
            print(f"✅ {name} 入库: {div}% (Key:{div_key})")
            
        except Exception as e:
            print(f"❌ {name} 失败: {e}")
            report[f'{name}_error'] = str(e)

    return report

def generate_message(data):
    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"📅 *投资早报 {today}*\n"
    msg += "------------------------\n"
    
    # 1. 基准
    bond = data.get('bond_10y', 0)
    fx = data.get('usd_cny', 0)
    msg += f"🏦 *基准锚点*\n"
    msg += f"• 国债收益：`{bond}%`\n"
    msg += f"• 汇率 (东财)：`{fx}`\n\n"

    # 2. A500
    if 'a500_div' in data:
        div = round(data['a500_div'], 2)
        spread = round(div - bond, 2)
        icon = "🟢" if spread > 0 else "🔴"
        advice = "舒适区" if spread > 0 else "性价比低"
        msg += f"🛡️ *中证A500 (000510)*\n"
        msg += f"• 股息率：`{div}%` (全市值)\n"
        msg += f"• 股债利差：`{spread}%` {icon}\n"
        msg += f"• 评价：{advice}\n\n"
    else:
        msg += f"⚠️ A500 缺失\n\n"

    # 3. 红利低波
    if 'low_div' in data:
        div = round(data['low_div'], 2)
        pe_rank = data.get('low_pe_rank', 0)
        
        if div >= 5.0: status = "🟢 极佳买点"
        elif div >= 4.8 and pe_rank < 60: status = "🟢 准买入区"
        elif div > 4.5: status = "🟡 正常定投"
        else: status = "🔴 拥挤/太贵"

        msg += f"💰 *红利低波 (H30269)*\n"
        msg += f"• 股息率：`{div}%` (流通盘)\n"
        msg += f"• PE分位：`{pe_rank}%`\n"
        msg += f"• 状态：{status}\n"
    else:
        msg += f"⚠️ 红利 缺失\n"

    return msg

def send_telegram(text):
    if not TG_TOKEN or "你的TOKEN" in TG_TOKEN:
        print("🚫 未配置 Token")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=10)
    except Exception as e: print("推送失败", e)

if __name__ == "__main__":
    data = get_data()
    msg = generate_message(data)
    print(msg)
    send_telegram(msg)