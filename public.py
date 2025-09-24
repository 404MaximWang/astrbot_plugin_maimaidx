import time
import zipfile
from pathlib import Path
from typing import List, Set, Union
from astrbot.api import logger
import aiofiles
import httpx
from .api import update_pl
from .libraries.image import *
import aiohttp



async def check_mai(force: bool = False):  # noqa: FBT001
    """检查mai资源"""
    await update_pl()  # 获取json文件
    if not Path(STATIC).joinpath("mai/pic").exists() or force:
        logger.info("初次使用，正在尝试自动下载资源\n资源包大小预计90M")
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", "https://www.diving-fish.com/maibot/static.zip") as response:
                    total_size = int(response.headers["Content-Length"])
                    downloaded_size = 0
                    last_update_time = time.time()
                    async with aiofiles.open("static.zip", "wb") as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            downloaded_size += len(chunk)
                            current_time = time.time()
                            if current_time - last_update_time >= 1:
                                progress = downloaded_size / total_size * 100
                                logger.info(f"下载进度: {progress:.2f}%")
                                last_update_time = current_time
            
            logger.info("已成功下载，正在尝试解压mai资源")
            with zipfile.ZipFile("static.zip", "r") as zip_file:
                zip_file.extractall(Path("data/maimai"))
            logger.info("mai资源已完整，尝试删除缓存")
            Path("static.zip").unlink()  # 删除下载的压缩文件
            msg = "mai资源下载成功，请使用【mai帮助】获取指令"

        except Exception as e:
            logger.warning(f"自动下载出错\n{e}\n请自行尝试手动下载")
            msg = f"自动下载出错\n{e}\n请自行尝试手动下载"
        return msg
    logger.info("已经成功下载，无需下载")
    return "已经成功下载，无需下载"
import asyncio
from bs4 import BeautifulSoup

COVER_URL = "https://www.diving-fish.com/covers/"

async def download_cover(session, url, path):
    """下载单个封面文件"""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                async with aiofiles.open(path, "wb") as f:
                    await f.write(content)
                return True
            return False
    except Exception as e:
        logger.error(f"下载封面失败: {url}, 错误: {e}")
        return False

async def update_covers():
    """检查并更新缺失的封面图片"""
    cover_dir = Path("data/maimai/mai/cover")
    if not cover_dir.exists():
        cover_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建封面目录: {cover_dir}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(COVER_URL)
            if response.status_code != 200:
                logger.error(f"无法访问封面索引页面: {COVER_URL}")
                return

            soup = BeautifulSoup(response.text, 'html.parser')
            remote_files = {a['href'] for a in soup.find_all('a') if a['href'].endswith('.png')}
            
            local_files = {f.name for f in cover_dir.glob('*.png')}
            
            missing_files = remote_files - local_files
            
            if not missing_files:
                logger.info("所有封面文件均已为最新，无需更新。")
                return

            logger.info(f"发现 {len(missing_files)} 个缺失的封面，开始下载...")

            tasks = []
            async with aiohttp.ClientSession() as session:
                for filename in missing_files:
                    url = f"{COVER_URL}{filename}"
                    path = cover_dir / filename
                    tasks.append(download_cover(session, url, path))
                
                results = await asyncio.gather(*tasks)
            
            successful_downloads = sum(1 for r in results if r)
            logger.info(f"封面更新完成。成功下载 {successful_downloads} / {len(missing_files)} 个文件。")

    except Exception as e:
        logger.error(f"更新封面时发生未知错误: {e}")