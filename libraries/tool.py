import time
from pathlib import Path

# 修改 STATIC 路径指向 astrbot 主目录下的 /data/maimai
STATIC = Path(__file__).resolve().parents[3] / 'maimai'

STATIC.mkdir(parents=True, exist_ok=True)


def hash_(qq: int):
    days = (
        int(time.strftime("%d", time.localtime(time.time())))
        + 31 * int(time.strftime("%m", time.localtime(time.time())))
        + 77
    )
    return (days * qq) >> 8
