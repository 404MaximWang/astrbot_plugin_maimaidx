from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import *
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from io import BytesIO
import math
import os
import uuid
from .libraries.image import *
from .libraries.maimai_best_40 import generate
from .libraries.maimai_best_50 import generate50
from .libraries.maimaidx_music import *
from .libraries.tool import hash_, STATIC
from .public import *
from .api import *

@register("astrbot_plugin_maimaidx", "0xa7973908", "A maimaidx helper for Astrbot.", "0.1")
class MyPlugin(Star):
    async def _process_request(self, event: AstrMessageEvent, is_b50: bool):
        logger.info(f"开始查询{'b50' if is_b50 else 'b40'}")
        user_id = event.get_sender_id()
        at_messages = [comp for comp in event.message_obj.message if isinstance(comp, At)]
        plain_text = event.message_str.strip()
        if " " in plain_text:
            username = plain_text.split(" ", 1)[1]
        else:
            username = ""
        at_id = None
        if at_messages: at_id = at_messages[0].qq
        
        tmp_path = None
        try:
            # 构造 payload
            if at_id:
                payload = {"qq": at_id, "b50": 1}
            elif username:
                payload = {"username": username, "b50": 1}
            else:
                payload = {"qq": str(user_id), "b50": 1}
            # 优先级顺序：at大于文字用户名(仅b40)大于发送者ID
            logger.info(f"Payload: {payload}")
            
            img, success = await generate50(payload) if is_b50 else await generate(payload)
            
            if success == 400:
                yield event.plain_result("未找到此玩家，请确保此玩家的用户名和查分器中的用户名相同。")
            elif success == 403:
                yield event.plain_result("该用户禁止了其他人获取数据。")
            elif success == 0:
                tmp_dir = STATIC / "tmp"
                tmp_dir.mkdir(exist_ok=True)
                tmp_path = tmp_dir / f"{uuid.uuid4()}.png"
                img.save(tmp_path)
                yield event.image_result(str(tmp_path))
            else:
                yield event.plain_result(f"查询失败，错误代码：{success}")
        except FileNotFoundError:
            logger.error("资源文件未找到")
            yield event.plain_result("资源未下载，请超级管理员使用`检查mai资源`指令")
        except Exception as e:
            logger.error(f"查询过程中发生错误: {str(e)}")
            yield event.plain_result(f"查询过程中发生错误，请稍后再试或联系管理员。错误信息：{str(e)}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    @filter.command("b50", priority = 1)
    async def b50(self, event: AstrMessageEvent):
        async for result in self._process_request(event, True):
            yield result

    @filter.command("b40", priority = 1)
    async def b40(self, event: AstrMessageEvent):
        async for result in self._process_request(event, False):
            yield result

    @filter.command("maihelp", aliases={"舞萌帮助", "mai帮助"}, priority = 1)
    async def help_msg(self, event: AstrMessageEvent):
        help_str = """可用命令如下：
            b50 查看自己的B50
            b40 查看自己的B40"""
        yield event.plain_result(help_str)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        if hasattr(self, 'update_task'):
            self.update_task.cancel()
        logger.info("MaimaiDX插件已终止")
    
    async def initialize(self):
        """异步的插件初始化"""
        await check_mai()

        try:
            await asyncio.wait_for(update_pl(), timeout=30)  # 设置30秒超时
            logger.info("更新机厅信息成功")
        except asyncio.TimeoutError:
            logger.warning("更新机厅信息超时，将使用旧数据")
        except Exception as e:
            logger.error(f"更新机厅信息失败: {e}")

        # 音乐数据初始化
        try:
            await initialize_music_data()
            logger.info("音乐数据初始化成功")
        except Exception as e:
            logger.error(f"音乐数据初始化失败: {e}")
        
        try:
            await update_covers()
            logger.info("封面资源检查更新完成")
        except Exception as e:
            logger.error(f"封面资源更新失败: {e}")
            
        self.update_task = asyncio.create_task(self.periodic_update())

    async def periodic_update(self):
        while True:
            await asyncio.sleep(3600)  # 每小时更新一次
            await update_pl()
