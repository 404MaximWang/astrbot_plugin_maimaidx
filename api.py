import asyncio
import json
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode

import aiohttp
from .libraries.tool import STATIC

async def update_pl():
    async with aiohttp.ClientSession() as session:
        urls = "http://wc.wahlap.net/maidx/rest/location"
        async with session.get(urls) as response:
            result = await response.json()
    if result:
        with (
            Path(STATIC)
            .parent.joinpath("site.json")
            .open(
                mode="w",
                encoding="utf-8",
            ) as f
        ):
            json.dump(result, f, ensure_ascii=False)