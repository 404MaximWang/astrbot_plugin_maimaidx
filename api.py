import asyncio
import json
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode

import httpx
from .libraries.path_config import STATIC

async def update_pl():
    async with httpx.AsyncClient() as client:
        urls = "http://wc.wahlap.net/maidx/rest/location"
        response = await client.get(urls)
        result = response.json()
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