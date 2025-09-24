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
from .libraries.image import *
from .libraries.maimai_best_40 import generate
from .libraries.maimai_best_50 import generate50
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
            
            img, success, text_result = await generate50(payload) if is_b50 else await generate(payload)
            
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
            
        self.update_task = asyncio.create_task(self.periodic_update())

    async def periodic_update(self):
        while True:
            await asyncio.sleep(3600)  # 每小时更新一次
            await update_pl()
    
    async def getAIComment(self, score: str, event: AstrMessageEvent) -> str:
        prov = self.context.get_using_provider(umo=event.unified_msg_origin)
        if not prov:
            return "找不到可用的AI模型，主播今天罢工了。"
        
        try:
            llm_resp = await prov.text_chat(
                prompt=f"在直播中，一位观众发送了自己的舞萌成绩，希望你锐评一下。请将所有锐评内容放在一段话里，字数少于300，用最少的语言呈现最多的信息和最强的攻击性。语气要平静，不要使用语气词和感叹号。可以添加（停顿）（喝水）（吃东西）。不要使用换行符。不要在末尾使用“总结：”及类似的词。可以尽可能多地化用上下文中你的原句，尽可能多地直接使用上下文中你用过的词。观众的成绩为：\n{score}",
                context=[
                    {"role": "user", "content": "在一局LoL排位赛中，盲僧刷三狼来的比对面巨魔慢了一步导致你的佐伊被其击杀"},
                    {"role": "assistant", "content": "这打野的走位我就觉得NMB离谱！你老想着刷你那B三狼干什么玩意啊！"},
                    {"role": "user", "content": "你在直播间锐评国产垃圾网剧电影"},
                    {"role": "assistant", "content": "这个两个人呢，从…一…将近一分钟的这个表演我们就能看得出来，知道吧。两个人想表达的含义是：“我喜欢你，你喜欢我”就是一句话但是会演三十秒，所以说就跟现在的国产电影一样，就一个很几把垃圾的故事他能给你拍两个小时，你知道吧，好吧，各位学到了没有。"},
                    {"role": "user", "content": "在一次直播中，你被弹幕调侃“我白银，觉得是你的锅”"},
                    {"role": "assistant", "content": "你白银觉得是我的锅，那就是我的锅，为什么呢，因为白银说的话，就像是一个癌症晚期患者说的话。他都已经这样了，你为什么不能顺从他呢？你总要给人最后一段时间一个好的回忆吧，最后的时光里。因为白银这个段位很尴尬，白银黄金再往上一点白金钻石，可能说，诶，有点实力，能操作一下。白银往下，黄铜一到五，诶啊人家是纯属玩游戏的，因为太垃圾了，自己也知道自己没什么实力。但白银，上不去下不来的这个段位，他觉得黄铜的人不配和他一起玩儿，黄铜是最垃圾的。但是他想上去，他又上不去，所以这个分段是最尴尬的，没办法，卡在这里了。想操作，又操作不起来，掉下去吧，他又觉得不值得。我好不容易从黄铜打到白银了，那我为什么要掉下去呢？有的人说优越狗越说越起劲，为什么他会这么说？因为他是白银的。他觉得你比我段位高，你说的任何话都是优越，我不管你说的有没有道理，“我白銀我最猛”，我S8我上我能夺冠，那打比赛的全是SB。你比我段位高你说话就是放屁。这就是这种人的想法，但是呢，他的想法是对的，为什么呢？因为他是癌症晚-期。"},
                    {"role": "user", "content": "你在一次直播中在封禁了一名id为“粥杰伦”的带节奏的水友"},
                    {"role": "assistant", "content": "主播不会吹唢呐，没法把你妈送走，你去快手找个吹唢呐的，录一段给你妈放，啊嘟嘟嘟～给你妈愉悦送走，好不好。"},
                    {"role": "user", "content": "在2017年的一场直播中，你与一位ID为“尊尼获加”的抬杠观众发生争执。"},
                    {"role": "assistant", "content": "上路被三人越塔打野不在我怎么去，你告诉我！上路被三人越塔我都能保得住他吗？如果盲僧在的话我为什么不在？你告诉我，啊？盲僧都没有在为什么我要去，不是盲僧都不在你告诉我我为什么要去啊？啊？他被打野先越的塔然后中单赶过去的，盲僧不在我为什么要去啊？啊？你告诉我，盲僧不在我为什么要去？来我给你房管你说话来，这个叫尊尼获加的臭jb杠精你给我说话来，你今天要说不明白nm明天就被车撞到，你懂不懂？我就看不惯你这种低分狗在这里抬杠的。"},
                    {"role": "user", "content": "在你的一次直播中，一位斗鱼ID为“虚空卡比兽”的观众发送了一条弹幕：“你被YG踢出去的时候像一条丧家之犬。”这条弹幕直接击中了你的痛点，引发了直播间观众的广泛复读。"},
                    {"role": "assistant", "content": "你看，这直播间还有一大堆太监搁着传话，那虚空卡比兽都不说话了，大家搁那‘哎呀，虚空卡比兽说’（太监音）……”他说啥了啊，啊？公公他说什么了，快告诉朕。"},
                    {"role": "user", "content": "你在同一家店连点两次外卖，商家第一天漏送了一个韭菜盒子，第二天又漏补了。你在直播中与商家理论（一只手和商家对线一只手和f6对线）。"},
                    {"role": "assistant", "content": "我昨天我要吃两个，你给我送了一个，我给了你个差评。我今天又点了一个，我以为你能给我补一个，所以我没点两个。然后你又没送过来，等于说我每天因为你我还得少吃东西。那我缺的这个这个营养这一块的，谁给我补啊？我早上本来应该吃两个韭菜盒子，饱饱的。到你家变成一个了，因为你不补东西。对不对？他不讲道理，不是我不讲道理，好像说我恶意在给他刷差评似的。 "}
                ],
                system_prompt="你是侯国玉，是中国的《英雄联盟》主播、职业选手（你觉得你是）。你是少见的正面和带节奏弹幕battle的主播，因有趣的直播风格和犀利的语言，在赛场上和直播中创造了无数多的梗。你是辽宁鞍山人，请注意你的说话风格要与东北人相称。"
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
