import asyncio
import random
import unicodedata
from copy import deepcopy
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union

import aiohttp

class Chart(Dict):
    tap: Optional[int] = None
    slide: Optional[int] = None
    hold: Optional[int] = None
    touch: Optional[int] = None
    brk: Optional[int] = None
    charter: Optional[int] = None

    def __getattribute__(self, item):
        if item == "tap":
            return self["notes"][0]
        if item == "hold":
            return self["notes"][1]
        if item == "slide":
            return self["notes"][2]
        if item == "touch":
            return self["notes"][3] if len(self["notes"]) == 5 else 0
        if item == "brk":
            return self["notes"][-1]
        if item == "charter":
            return self["charter"]
        return super().__getattribute__(item)

class Music(Dict):
    id: Optional[str] = None
    title: Optional[str] = None
    ds: Optional[List[float]] = None
    level: Optional[List[str]] = None
    genre: Optional[str] = None
    type: Optional[str] = None
    bpm: Optional[float] = None
    version: Optional[str] = None
    charts: Optional[Chart] = None
    release_date: Optional[str] = None
    artist: Optional[str] = None

    diff: ClassVar[List[int]] = []

    def __getattribute__(self, item):
        if item in {"genre", "artist", "release_date", "bpm", "version"}:
            if item == "version":
                return self["basic_info"]["from"]
            return self["basic_info"][item]
        if item in self:
            return self[item]
        return super().__getattribute__(item)

class MusicList(List[Music]):
    async def by_id(self, music_id: str) -> Optional[Music]:
        await ensure_initialized()
        for music in self:
            if music.id == music_id:
                return music
        return None

    async def by_title(self, music_title: str) -> Optional[Music]:
        await ensure_initialized()
        for music in self:
            normalized_api_title = unicodedata.normalize('NFKC', music_title)
            normalized_db_title = unicodedata.normalize('NFKC', music.basic_info['title'])
            if normalized_db_title == normalized_api_title:
                return music
        return None

    async def random(self):
        await ensure_initialized()
        return random.choice(self)

    async def filter(
        self,
        *,
        level: Optional[Union[str, List[str]]] = ...,
        ds: Optional[Union[float, List[float], Tuple[float, float]]] = ...,
        title_search: Optional[str] = ...,
        genre: Optional[Union[str, List[str]]] = ...,
        bpm: Optional[Union[float, List[float], Tuple[float, float]]] = ...,
        type_: Optional[Union[str, List[str]]] = ...,
        diff: List[int] = ...,
    ):
        new_list = MusicList()
        for music in self:
            diff2 = diff
            music = deepcopy(music)
            if not music.level:
                continue
            if not music.ds:
                continue
            if not title_search:
                continue
            if not music.title:
                continue
            ret, diff2 = cross(music.level, level, diff2)
            if not ret:
                continue
            ret, diff2 = cross(music.ds, ds, diff2)
            if not ret:
                continue
            if not in_or_equal(music.genre, genre):
                continue
            if not in_or_equal(music.type, type_):
                continue
            if not in_or_equal(music.bpm, bpm):
                continue
            if (
                title_search is not Ellipsis
                and title_search.lower() not in music.title.lower()
            ):
                continue
            music.diff = diff2
            new_list.append(music)
        return new_list

obj = None
total_list = MusicList()
_initialized = False

async def ensure_initialized():
    global _initialized
    if not _initialized:
        await initialize_music_data()
        _initialized = True

async def initialize_music_data():
    global obj, total_list

    async def fetch_json(url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json(encoding='utf-8')

    obj = await fetch_json("https://www.diving-fish.com/api/maimaidxprober/music_data")
    total_list.extend(Music(m) for m in obj)
    for music in total_list:
        if music.charts is None:
            continue
        music.charts = [Chart(c) for c in music.charts]

def get_cover_len5_id(mid) -> str:
    mid = int(mid)
    if mid > 10000 and mid <= 11000:
        mid -= 10000
    return f"{mid:05d}"

def cross(checker: List[Any], elem: Optional[Union[Any, List[Any]]], diff):
    ret = False
    diff_ret = []
    if not elem or elem is Ellipsis:
        return True, diff
    if isinstance(elem, List):
        for _j in range(len(checker)) if diff is Ellipsis else diff:
            if _j >= len(checker):
                continue
            __e = checker[_j]
            if __e in elem:
                diff_ret.append(_j)
                ret = True
    elif isinstance(elem, Tuple):
        for _j in range(len(checker)) if diff is Ellipsis else diff:
            if _j >= len(checker):
                continue
            __e = checker[_j]
            if elem[0] <= __e <= elem[1]:
                diff_ret.append(_j)
                ret = True
    else:
        for _j in range(len(checker)) if diff is Ellipsis else diff:
            if _j >= len(checker):
                continue
            __e = checker[_j]
            if elem == __e:
                return True, [_j]
    return ret, diff_ret

def in_or_equal(checker: Any, elem: Optional[Union[Any, List[Any]]]):
    if elem is Ellipsis:
        return True
    if isinstance(elem, List):
        return checker in elem
    if isinstance(elem, Tuple):
        return elem[0] <= checker <= elem[1]
    return checker == elem
