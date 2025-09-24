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
import re
import json
from pathlib import Path
from .libraries.image import *
from .libraries.maimai_best import generate
from .libraries.maimaidx_music import *
from .libraries.tool import hash_, STATIC
from .public import *
from .api import *
import asyncio

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
            
            img, success, text_result = await generate(payload, is_b50)
            
            if success == 400:
                yield event.plain_result("未找到此玩家，请确保此玩家的用户名和查分器中的用户名相同。")
            elif success == 403:
                yield event.plain_result("该用户禁止了其他人获取数据。")
            elif success == 0 and img and text_result:
                tmp_dir = STATIC / "tmp"
                tmp_dir.mkdir(exist_ok=True)
                tmp_path = tmp_dir / f"{uuid.uuid4()}.png"
                img.save(tmp_path)
                yield event.image_result(str(tmp_path))
                # yield event.plain_result(text_result)  # 注释掉此行，不再直接输出成绩文本
                ai_comment = await self.getAIComment(text_result, event)
                if isinstance(ai_comment, str) and ai_comment:
                    yield event.plain_result(ai_comment)
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

    @filter.command("checkmai", aliases={"检查mai资源"}, priority = 1)
    async def checkmai(self, event: AstrMessageEvent):
        """检查mai资源"""
        yield event.plain_result("正在检查资源，请稍等...")
        msg = await check_mai()
        yield event.plain_result(msg)

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
        
        # 加载prompt配置
        try:
            self.load_prompts()
            logger.info("AI prompt配置加载成功")
        except Exception as e:
            logger.error(f"AI prompt配置加载失败: {e}")
            
        self.update_task = asyncio.create_task(self.periodic_update())
    
    def load_prompts(self):
        """加载AI prompt配置"""
        prompt_path = Path(__file__).parent / "prompt_default.json"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompts = json.load(f)
        else:
            logger.warning("prompt_default.json不存在，将使用默认配置")
            self.prompts = {}

    async def periodic_update(self):
        while True:
            await asyncio.sleep(3600)  # 每小时更新一次
            await update_pl()
    
    async def getAIComment(self, score: str, event: AstrMessageEvent) -> str:
        prov = self.context.get_using_provider(umo=event.unified_msg_origin)
        if not prov:
            return "找不到可用的AI模型，主播今天罢工了。"
        
        try:
            # 从配置中获取prompt
            if hasattr(self, 'prompts') and 'maimai_comment' in self.prompts:
                prompt_config = self.prompts['maimai_comment']
                prompt = prompt_config['prompt'].format(score=score)
                context = prompt_config['context']
                system_prompt = prompt_config['system_prompt']
            else:
                # 如果没有配置或加载失败，使用默认值
                logger.warning("使用默认prompt配置")
                prompt = f"在直播中，一位观众发送了自己的舞萌成绩，希望你锐评一下。请将所有锐评内容放在一段话里，字数少于300，用最少的语言呈现最多的信息和最强的攻击性。语气要平静，不要使用语气词和感叹号。可以添加（停顿）（喝水）（吃东西）。不要使用换行符。不要在末尾使用\"总结：\"及类似的词。可以尽可能多地化用上下文中你的原句，尽可能多地直接使用上下文中你用过的词。观众的成绩为：\n{score}"
                context = [
                    {"role": "user", "content": "在一局LoL排位赛中，盲僧刷三狼来的比对面巨魔慢了一步导致你的佐伊被其击杀"},
                    {"role": "assistant", "content": "这打野的走位我就觉得NMB离谱！你老想着刷你那B三狼干什么玩意啊！"}
                ]
                system_prompt = "你是侯国玉，是中国的《英雄联盟》主播、职业选手（你觉得你是）。"
            
            llm_resp = await prov.text_chat(
                prompt=prompt,
                context=context,
                system_prompt=system_prompt
            )
            raw_text = str(llm_resp)
            match = re.search(r"Plain\(.*?text='(.*?)', convert=True\)", raw_text, re.DOTALL)
            if match:
                raw_text = str(llm_resp)
                match = re.search(r"text='(.*?)'", raw_text, re.DOTALL)
                if match:
                    llm_text = match.group(1)
                    # 再次保险，移除所有可能的换行符
                    llm_text = llm_text.replace('\\n', ' ').replace('\n', ' ')
                    logger.info(f"AI锐评原文: {llm_text}")
                    return llm_text
                else:
                    logger.error(f"无法从AI响应中提取文本: {raw_text}")
                    return "AI的回复格式不对，主播翻译不了了。"
        except Exception as e:
            logger.error(f"AI锐评时发生错误: {e}")
            return "哎呀，主播没吃够韭菜盒子，锐评不了了。"
