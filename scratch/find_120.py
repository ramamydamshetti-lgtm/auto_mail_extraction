import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

transcript_path = r"C:\Users\HariPriya M\.gemini\antigravity-ide\brain\f3e2fe1a-57ea-4866-ae34-0c6f3adc3cb7\.system_generated\logs\transcript_full.jsonl"
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        c = str(d.get('content', ''))
        if '203529-1' in c or '203514-1' in c or '203528-1' in c:
            idx = d.get('step_index')
            print(f"Step {idx}:")
            print(c[:500])
            print("="*50)
