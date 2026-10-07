import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"C:\Users\HariPriya M\.gemini\antigravity-ide\brain\d577c164-ed43-4820-8ae2-d0ceb27f5ea0\.system_generated\logs\transcript.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        idx = d.get("step_index", 0)
        if 154 <= idx <= 165:
            print(f"=== STEP {idx} ({d.get('type')}, {d.get('source')}) ===")
            content = d.get('content')
            if content:
                print(str(content)[:1000])
            if 'tool_calls' in d:
                for tc in d['tool_calls']:
                    print(f"Tool call: {tc.get('name')}")
                    print(f"Args: {str(tc.get('args'))[:500]}")
