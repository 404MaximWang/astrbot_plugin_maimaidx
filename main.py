from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import *
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
import uuid
import re
import json
from .libraries.image import DrawBest
from .libraries.image_generator import generate, handle_oneshot_command
from .libraries.maimaidx_music import *
from .libraries.utils import hash_
from .libraries.path_config import STATIC
from .libraries.models import *
from .public import *
from .api import *
import asyncio

@register("astrbot_plugin_maimaidx", "0xa7973908", "A maimaidx helper for Astrbot.", "1.1")
class MyPlugin(Star):
    @filter.command("b50", priority = 1)
    async def b50(self, event: AstrMessageEvent):
        logger.info("开始查询b50")
        
        # 提取用户信息
        user_id = event.get_sender_id()
        at_messages = [comp for comp in event.message_obj.message if isinstance(comp, At)]
        plain_text = event.message_str.strip()
        username = plain_text.split(" ", 1)[1] if " " in plain_text else ""
        at_id = at_messages[0].qq if at_messages else None

        # 构造 payload
        if at_id:
            payload = {"qq": at_id, "b50": 1}
        elif username:
            payload = {"username": username, "b50": 1}
        else:
            payload = {"qq": str(user_id), "b50": 1}
        logger.info(f"Payload: {payload}")

        use_web_generator = self.context._config.get('web_image_generator', True)
        if use_web_generator:
            try:
                logger.info("尝试使用OneShot逻辑生成B50图片")
                result = await handle_oneshot_command(payload, is_b50=True)
                if result:
                    oneshot_path, text_result = result
                    yield event.image_result(oneshot_path)
                    
                    ai_comment = await self.getAIComment(text_result, event)
                    if isinstance(ai_comment, str) and ai_comment:
                        yield event.plain_result(ai_comment)
                    return
                else:
                    logger.warning("OneShot生成失败，回退到本地生成")
            except Exception as e:
                logger.error(f"OneShot生成时发生错误，回退到本地生成: {e}")
        
        # B50本地生成逻辑 (回退)
        async for result in self._generate_local_image(event, payload, is_b50=True):
            yield result

    @filter.command("b40", priority = 1)
    async def b40(self, event: AstrMessageEvent):
        logger.info("开始查询b40")
        
        user_id = event.get_sender_id()
        at_messages = [comp for comp in event.message_obj.message if isinstance(comp, At)]
        plain_text = event.message_str.strip()
        username = plain_text.split(" ", 1)[1] if " " in plain_text else ""
        at_id = at_messages[0].qq if at_messages else None

        if at_id:
            payload = {"qq": at_id, "b50": 0}
        elif username:
            payload = {"username": username, "b50": 0}
        else:
            payload = {"qq": str(user_id), "b50": 0}
        logger.info(f"Payload: {payload}")
        
        async for result in self._generate_local_image(event, payload, is_b50=False):
            yield result
            
    async def _generate_local_image(self, event: AstrMessageEvent, payload: dict, is_b50: bool):
        """本地生成B40/B50图片"""
        tmp_path = None
        img = None
        try:
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
                
                ai_comment = await self.getAIComment(text_result, event)
                if isinstance(ai_comment, str) and ai_comment:
                    yield event.plain_result(ai_comment)
            else:
                yield event.plain_result(f"查询失败，错误代码：{success}")
        except FileNotFoundError:
            logger.error("资源文件未找到")
            yield event.plain_result("资源未下载，请超级管理员使用`检查mai资源`指令")
        except Exception as e:
            logger.error(f"本地图片生成过程中发生错误: {str(e)}")
            yield event.plain_result(f"查询过程中发生错误，请稍后再试或联系管理员。错误信息：{str(e)}")
        finally:
            if img:
                img.close()
            if tmp_path:
                # 使用 asyncio.run_in_executor 来检查文件是否存在
                loop = asyncio.get_event_loop()
                file_exists = await loop.run_in_executor(None, lambda: tmp_path.exists())
                if file_exists:
                    try:
                        # 使用 asyncio.run_in_executor 来删除文件
                        await loop.run_in_executor(None, lambda: tmp_path.unlink())
                    except Exception as e:
                        logger.error(f"删除临时文件失败: {str(e)}")

    @filter.command("maihelp", aliases={"舞萌帮助", "mai帮助"}, priority = 1)
    async def help_msg(self, event: AstrMessageEvent):
        help_str = """可用命令如下：
            b50 查看自己的B50
            b40 查看自己的B40"""
        yield event.plain_result(help_str)

    async def _update_pl_background(self):
        try:
            await asyncio.wait_for(update_pl(), timeout=60)  # 增加超时到60秒
            logger.info("后台更新机厅信息成功")
        except asyncio.TimeoutError:
            logger.warning("后台更新机厅信息超时")
        except Exception as e:
            logger.error(f"后台更新机厅信息失败: {e}")

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

        # 将机厅信息更新放入后台任务，防止阻塞初始化
        asyncio.create_task(self._update_pl_background())

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
            return "找不到可用的AI模型，主播今天先下播了。"
        
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
            # 更健壮的响应解析方式
            llm_text = self._extract_text_from_response(llm_resp)
            if llm_text:
                # 移除所有可能的换行符
                llm_text = llm_text.replace('\\n', ' ').replace('\n', ' ')
                logger.info(f"AI锐评原文: {llm_text}")
                return llm_text
            else:
                logger.error(f"无法从AI响应中提取文本")
                return "AI的回复格式不对，主播翻译不了了。"
        except Exception as e:
            logger.error(f"AI锐评时发生错误: {e}")
            return "哎呀，主播没吃够韭菜盒子，锐评不了了。"
    
    def _extract_text_from_response(self, response: Any) -> Optional[str]:
        """从AI响应中提取文本，使用更健壮的方式"""
        try:
            # 尝试直接访问属性
            if hasattr(response, 'text'):
                return response.text
            
            # 如果是Plain对象
            if hasattr(response, '__class__') and response.__class__.__name__ == 'Plain':
                if hasattr(response, 'text'):
                    return response.text
            
            # 如果是字典或类似字典的对象
            if hasattr(response, 'get'):
                if 'text' in response:
                    return response['text']
            
            # 最后尝试字符串解析（作为后备方案）
            raw_text = str(response)
            match = re.search(r"text='(.*?)'", raw_text, re.DOTALL)
            if match:
                return match.group(1)
            
            # 如果所有方法都失败
            return None
        except Exception as e:
            logger.error(f"提取AI响应文本时发生错误: {e}")
            return None
