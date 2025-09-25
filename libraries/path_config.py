from pathlib import Path

# 指向 /data/maimai
STATIC = Path(__file__).resolve().parents[3] / 'maimai'

STATIC.mkdir(parents=True, exist_ok=True)