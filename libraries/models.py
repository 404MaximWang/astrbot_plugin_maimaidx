from typing import Dict, List, Any, Optional
from .maimaidx_music import total_list

diffs = ["Basic", "Advanced", "Expert", "Master", "Re:Master"]

class ChartInfo(object):
    def __init__(
        self,
        idNum: str,
        diff: int,
        tp: str,
        achievement: float,
        ra: int,
        comboId: int,
        scoreId: int,
        title: str,
        ds: float,
        lv: str,
    ):
        self.idNum = idNum
        self.diff = diff
        self.tp = tp
        self.achievement = achievement
        self.ra = ra
        self.comboId = comboId
        self.scoreId = scoreId
        self.title = title
        self.ds = ds
        self.lv = lv

    def __str__(self):
        return (
            "%-50s" % f"{self.title} [{self.tp}]"
            + f"{self.ds}\t{diffs[self.diff]}\t{self.ra}"
        )

    def __eq__(self, other):
        return self.ra == other.ra

    def __lt__(self, other):
        return self.ra < other.ra

    @classmethod
    async def from_json(cls, data):
        rate = [
            "d", "c", "b", "bb", "bbb", "a", "aa", "aaa", "s", "sp", "ss", "ssp", "sss", "sssp",
        ]
        ri = rate.index(data["rate"])
        fc = ["", "fc", "fcp", "ap", "app"]
        fi = fc.index(data["fc"])
        music = await total_list.by_title(data["title"])
        return cls(
            idNum=music.id if music else "00000",
            title=data["title"],
            diff=data["level_index"],
            ra=data["ra"],
            ds=data["ds"],
            comboId=fi,
            scoreId=ri,
            lv=data["level"],
            achievement=data["achievements"],
            tp=data["type"],
        )


class BestList(object):
    def __init__(self, size: int):
        self.data = []
        self.size = size

    def push(self, elem: ChartInfo):
        if len(self.data) >= self.size and elem < self.data[-1]:
            return
        self.data.append(elem)
        self.data.sort()
        self.data.reverse()
        while len(self.data) > self.size:
            del self.data[-1]

    def pop(self):
        del self.data[-1]

    def __str__(self):
        return "[\n\t" + ", \n\t".join([str(ci) for ci in self.data]) + "\n]"

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data[index]