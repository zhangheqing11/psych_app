import sys
import os
import json
sys.path.append('.')

try:
    from app import SYSTEM_PROMPT_INTERVIEW
    print("✅ 成功导入SYSTEM_PROMPT_INTERVIEW")
    
    print("\n=== SYSTEM_PROMPT_INTERVIEW 结构 ===")
    print(json.dumps(SYSTEM_PROMPT_INTERVIEW, indent=2, ensure_ascii=False))
    
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc() 