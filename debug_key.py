import akshare as ak
import pandas as pd
import pprint  # 让打印出来的字典好看一点

print("🔍 正在把红利低波 (H30269) 扒个精光...")

try:
    # 1. 获取数据
    df = ak.stock_zh_index_value_csindex(symbol="000510")
    
    # 2. 强制清洗日期 (确保我们看的是真正的最后一行)
    if '日期' in df.columns:
        df['日期'] = pd.to_datetime(df['日期'])
        df.sort_values('日期', inplace=True)
    
    # 3. 提取最后一行
    latest = df.iloc[-1]
    
    # 4. 打印列名列表
    print("\n📋 [1] 所有的 Key (列名):")
    print(df.columns.tolist())

    # 5. 打印完整字典
    print("\n🗝️ [2] 最新一行数据的完整字典 (Raw Data):")
    print("-" * 40)
    pprint.pprint(latest.to_dict())
    print("-" * 40)

    # 6. 对比 PE1 和 PE2 (看看差距有多大)
    p1 = latest.get('市盈率1', 'N/A')
    p2 = latest.get('市盈率2', 'N/A')
    print(f"\n⚖️ 关键对比:")
    print(f"• 市盈率1 (总股本): {p1}  <-- 代码里目前用的是这个")
    print(f"• 市盈率2 (流通盘): {p2}  <-- 很多App默认用这个")
    
except Exception as e:
    print(f"❌ 爆炸了: {e}")