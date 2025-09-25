# Author: xyb, Diving_Fish
# rewrite Anges Digital

import math
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import uuid
from io import BytesIO

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from astrbot.api import logger

from .maimaidx_music import get_cover_len5_id, total_list
from .path_config import STATIC
from .models import BestList, ChartInfo, diffs

scoreRank = [
    "D", "C", "B", "BB", "BBB", "A", "AA", "AAA", "S", "S+", "SS", "SS+", "SSS", "SSS+",
]
combo = ["", "FC", "FC+", "AP", "AP+"]


async def convert_chart_info_to_api_format(chart_info: ChartInfo) -> Dict[str, Any]:
    """
    将ChartInfo对象转换为API所需的格式
    """
    difficulty_map = {
        0: "basic",
        1: "advanced",
        2: "expert",
        3: "master",
        4: "re:master"
    }
    difficulty_str = difficulty_map.get(chart_info.diff, "expert")
    return {
        "sheetId": f"{chart_info.title}__dxrt__{chart_info.tp.lower()}__dxrt__{difficulty_str}",
        "achievementRate": chart_info.achievement
    }


async def send_oneshot_request(
    version: str,
    region: str,
    b15_entries: List[Dict[str, Any]],
    b35_entries: List[Dict[str, Any]]
) -> Optional[bytes]:
    """
    向远程API发送OneShot图片生成请求并返回图片数据
    """
    payload = {
        "version": version,
        "region": region,
        "calculatedEntries": {
            "b15": b15_entries,
            "b35": b35_entries
        }
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://miruku.dxrating.net/functions/render-oneshot/v0?pixelated=1',
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            if response.status_code == 200:
                return response.content
            else:
                logger.info(f"OneShot图片生成失败: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"OneShot图片生成异常: {e}")
        return None


async def generate_oneshot_data(
    sd_best: BestList,
    dx_best: BestList,
    version: str = "PRiSM",
    region: str = "cn"
) -> Optional[bytes]:
    """
    生成OneShot图片数据并发送请求
    """
    b15_data = [await convert_chart_info_to_api_format(chart) for chart in dx_best]
    b35_data = [await convert_chart_info_to_api_format(chart) for chart in sd_best]
    return await send_oneshot_request(version, region, b15_data, b35_data)


async def save_oneshot_image_to_tmp(oneshot_data: bytes) -> Optional[str]:
    """
    将oneshot图片数据保存到临时文件并返回路径
    """
    if not oneshot_data:
        return None
    try:
        tmp_dir = STATIC / "tmp"
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"{uuid.uuid4()}.png"
        with open(tmp_path, "wb") as f:
            f.write(oneshot_data)
        return str(tmp_path)
    except Exception as e:
        logger.error(f"保存OneShot图片到临时文件失败: {e}")
        return None


async def handle_oneshot_command(payload: Dict, is_b50: bool = False) -> Optional[Tuple[str, str]]:
    """
    处理oneshot命令，生成并返回oneshot图片路径和成绩文本
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://www.diving-fish.com/api/maimaidxprober/query/player",
                json=payload,
            )
            if resp.status_code != 200:
                return None
            obj = resp.json()

        nickname = obj["nickname"]

        if is_b50:
            sd_best = BestList(35)
            dx_best = BestList(15)
        else:
            sd_best = BestList(25)
            dx_best = BestList(15)

        dx: List[Dict] = obj["charts"]["dx"]
        sd: List[Dict] = obj["charts"]["sd"]
        for c in sd:
            sd_best.push(await ChartInfo.from_json(c))
        for c in dx:
            dx_best.push(await ChartInfo.from_json(c))

        if is_b50:
            sd_rating = sum(computeRa(c.ds, c.achievement, is_b50) for c in sd_best)
            dx_rating = sum(computeRa(c.ds, c.achievement, is_b50) for c in dx_best)
            total_rating = sd_rating + dx_rating
            text_result = f"玩家: {nickname}\n"
            text_result += f"Rating: {total_rating} (SD: {sd_rating} + DX: {dx_rating})\n\n"
            text_result += "--- SD Best (B35) ---\n"
            for i, chart in enumerate(sd_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {computeRa(chart.ds, chart.achievement, is_b50)}\n"
            text_result += "\n--- DX Best (B15) ---\n"
            for i, chart in enumerate(dx_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {computeRa(chart.ds, chart.achievement, is_b50)}\n"
        else:
            rating = obj["rating"]
            additional_rating = obj["additional_rating"]
            total_rating = rating + additional_rating
            text_result = f"玩家: {nickname}\n"
            text_result += f"Rating: {total_rating} (底分: {rating} + 段位分: {additional_rating})\n\n"
            text_result += "--- SD Best (B25) ---\n"
            for i, chart in enumerate(sd_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {chart.ra}\n"
            text_result += "\n--- DX Best (B15) ---\n"
            for i, chart in enumerate(dx_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {chart.ra}\n"
        
        oneshot_data = await generate_oneshot_data(sd_best, dx_best, "PRiSM", "cn")
        if oneshot_data:
            tmp_path = await save_oneshot_image_to_tmp(oneshot_data)
            if tmp_path:
                return tmp_path, text_result
    except Exception as e:
        logger.error(f"处理oneshot命令时出错: {e}")
        raise e
    return None


class DrawBest(object):
    def __init__(
        self,
        sdBest: BestList,
        dxBest: BestList,
        userName: str,
        playerRating: int,
        musicRating: int,
        is_b50: bool = False,
    ):
        self.sdBest = sdBest
        self.dxBest = dxBest
        self.userName = self._stringQ2B(userName)
        self.playerRating = playerRating
        self.musicRating = musicRating
        self.rankRating = self.playerRating - self.musicRating
        self.is_b50 = is_b50
        if is_b50:
            self.sdRating = 0
            self.dxRating = 0
            for sd in sdBest:
                self.sdRating += computeRa(sd.ds, sd.achievement, is_b50)
            for dx in dxBest:
                self.dxRating += computeRa(dx.ds, dx.achievement, is_b50)
            self.playerRating = self.sdRating + self.dxRating
        self.pic_dir = STATIC / "mai" / "pic"
        self.cover_dir = STATIC / "mai" / "cover"
        self.img = Image.open(self.pic_dir / "UI_TTR_BG_Base_Plus.png").convert("RGBA")
        self.ROWS_IMG = [2]
        for i in range(6):
            self.ROWS_IMG.append(116 + 96 * i)
        self.COLOUMS_IMG = []
        if is_b50:
            for i in range(8):
                self.COLOUMS_IMG.append(2 + 138 * i)
            for i in range(4):
                self.COLOUMS_IMG.append(988 + 138 * i)
        else:
            for i in range(6):
                self.COLOUMS_IMG.append(2 + 172 * i)
            for i in range(4):
                self.COLOUMS_IMG.append(888 + 172 * i)
        self.draw()

    def _Q2B(self, uchar):
        inside_code = ord(uchar)
        if inside_code == 0x3000:
            inside_code = 0x0020
        else:
            inside_code -= 0xFEE0
        if (inside_code < 0x0020 or inside_code > 0x7E):
            return uchar
        return chr(inside_code)

    def _stringQ2B(self, ustring):
        return "".join([self._Q2B(uchar) for uchar in ustring])

    def _getCharWidth(self, o) -> int:
        widths = [
            (126, 1), (159, 0), (687, 1), (710, 0), (711, 1), (727, 0), (733, 1), (879, 0), (1154, 1), (1161, 0), (4347, 1), (4447, 2), (7467, 1), (7521, 0), (8369, 1), (8426, 0), (9000, 1), (9002, 2), (11021, 1), (12350, 2), (12351, 1), (12438, 2), (12442, 0), (19893, 2), (19967, 1), (55203, 2), (63743, 1), (64106, 2), (65039, 1), (65059, 0), (65131, 2), (65279, 1), (65376, 2), (65500, 1), (65510, 2), (120831, 1), (262141, 2), (1114109, 1),
        ]
        if o == 0xE or o == 0xF:
            return 0
        for num, wid in widths:
            if o <= num:
                return wid
        return 1

    def _coloumWidth(self, s: str):
        res = 0
        for ch in s:
            res += self._getCharWidth(ord(ch))
        return res

    def _changeColumnWidth(self, s: str, lens: int) -> str:
        res = 0
        sList = []
        for ch in s:
            res += self._getCharWidth(ord(ch))
            if res <= lens:
                sList.append(ch)
        return "".join(sList)

    def _resizePic(self, img: Image.Image, time: float):
        return img.resize((int(img.size[0] * time), int(img.size[1] * time)))

    def _findRaPic(self) -> str:
        if self.is_b50:
            num = "10"
            if self.playerRating < 1000: num = "01"
            elif self.playerRating < 2000: num = "02"
            elif self.playerRating < 4000: num = "03"
            elif self.playerRating < 7000: num = "04"
            elif self.playerRating < 10000: num = "05"
            elif self.playerRating < 12000: num = "06"
            elif self.playerRating < 13000: num = "07"
            elif self.playerRating < 14000: num = "08"
            elif self.playerRating < 15000: num = "09"
            return f"UI_CMN_DXRating_S_{num}.png"
        else:
            num = "10"
            if self.playerRating < 1000: num = "01"
            elif self.playerRating < 2000: num = "02"
            elif self.playerRating < 3000: num = "03"
            elif self.playerRating < 4000: num = "04"
            elif self.playerRating < 5000: num = "05"
            elif self.playerRating < 6000: num = "06"
            elif self.playerRating < 7000: num = "07"
            elif self.playerRating < 8000: num = "08"
            elif self.playerRating < 8500: num = "09"
            return f"UI_CMN_DXRating_S_{num}.png"

    def _drawRating(self, ratingBaseImg: Image.Image):
        COLOUMS_RATING = [86, 100, 115, 130, 145]
        theRa = self.playerRating
        i = 4
        while theRa:
            digit = theRa % 10
            theRa = theRa // 10
            digitImg = Image.open(self.pic_dir / f"UI_NUM_Drating_{digit}.png").convert("RGBA")
            digitImg = self._resizePic(digitImg, 0.6)
            ratingBaseImg.paste(digitImg, (COLOUMS_RATING[i] - 2, 9), mask=digitImg.split()[3])
            i = i - 1
        return ratingBaseImg

    def _drawBestList(self, img: Image.Image, sdBest: BestList, dxBest: BestList):
        if self.is_b50: itemW, itemH = 131, 88
        else: itemW, itemH = 164, 88
        Color = [(69, 193, 36), (255, 186, 1), (255, 90, 102), (134, 49, 200), (217, 197, 233)]
        levelTriagle = [(itemW, 0), (itemW - 27, 0), (itemW, 27)]
        rankPic = ["D", "C", "B", "BB", "BBB", "A", "AA", "AAA", "S", "Sp", "SS", "SSp", "SSS", "SSSp"]
        comboPic = ["", "FC", "FCp", "AP", "APp"]
        titleFontName = str(STATIC / "adobe_simhei.otf")

        for num, chartInfo in enumerate(sdBest):
            if self.is_b50: i, j = num // 7, num % 7
            else: i, j = num // 5, num % 5
            
            pngPath = self.cover_dir / f"{get_cover_len5_id(chartInfo.idNum)}.png"
            if not pngPath.is_file(): pngPath = self.cover_dir / "01000.png"
            
            with Image.open(pngPath).convert("RGB") as temp:
                temp = self._resizePic(temp, itemW / temp.size[0])
                temp = temp.crop((0, (temp.size[1] - itemH) / 2, itemW, (temp.size[1] + itemH) / 2))
                temp = temp.filter(ImageFilter.GaussianBlur(3)).point(lambda p: int(p * 0.72))
                tempDraw = ImageDraw.Draw(temp)
                tempDraw.polygon(levelTriagle, Color[chartInfo.diff])
                
                title = chartInfo.title
                if self.is_b50:
                    font = ImageFont.truetype(titleFontName, 16, encoding="utf-8")
                    if self._coloumWidth(title) > 15: title = self._changeColumnWidth(title, 12) + "..."
                    tempDraw.text((8, 8), title, "white", font)
                    font = ImageFont.truetype(titleFontName, 12, encoding="utf-8")
                else:
                    font = ImageFont.truetype(titleFontName, 16, encoding="utf-8")
                    if self._coloumWidth(title) > 15: title = self._changeColumnWidth(title, 14) + "..."
                    tempDraw.text((8, 8), title, "white", font)
                    font = ImageFont.truetype(titleFontName, 14, encoding="utf-8")

                tempDraw.text((7, 28), f'{"%.4f" % chartInfo.achievement}%', "white", font)
                
                with Image.open(self.pic_dir / f"UI_GAM_Rank_{rankPic[chartInfo.scoreId]}.png").convert("RGBA") as rankImg:
                    rankImg = self._resizePic(rankImg, 0.3)
                    temp.paste(rankImg, (88 if not self.is_b50 else 72, 28), rankImg.split()[3])

                if chartInfo.comboId:
                    with Image.open(self.pic_dir / f"UI_MSS_MBase_Icon_{comboPic[chartInfo.comboId]}_S.png").convert("RGBA") as comboImg:
                        comboImg = self._resizePic(comboImg, 0.45)
                        temp.paste(comboImg, (119 if not self.is_b50 else 103, 27), comboImg.split()[3])

                font = ImageFont.truetype(str(STATIC / "adobe_simhei.otf"), 12, encoding="utf-8")
                ra_text = f"Base: {chartInfo.ds} -> {computeRa(chartInfo.ds, chartInfo.achievement, self.is_b50)}" if self.is_b50 else f"Base: {chartInfo.ds} -> {chartInfo.ra}"
                tempDraw.text((8, 44), ra_text, "white", font)
                
                font = ImageFont.truetype(str(STATIC / "adobe_simhei.otf"), 18, encoding="utf-8")
                tempDraw.text((8, 60), f"#{num + 1}", "white", font)

                recBase = Image.new("RGBA", (itemW, itemH), "black").point(lambda p: int(p * 0.8))
                img.paste(recBase, (self.COLOUMS_IMG[j] + 5, self.ROWS_IMG[i + 1] + 5))
                img.paste(temp, (self.COLOUMS_IMG[j] + 4, self.ROWS_IMG[i + 1] + 4))

        for num in range(len(sdBest), sdBest.size):
            if self.is_b50: i, j = num // 7, num % 7
            else: i, j = num // 5, num % 5
            with Image.open(self.cover_dir / "01000.png").convert("RGB") as temp:
                temp = self._resizePic(temp, itemW / temp.size[0])
                temp = temp.crop((0, (temp.size[1] - itemH) / 2, itemW, (temp.size[1] + itemH) / 2))
                temp = temp.filter(ImageFilter.GaussianBlur(1))
                img.paste(temp, (self.COLOUMS_IMG[j] + 4, self.ROWS_IMG[i + 1] + 4))

        for num, chartInfo in enumerate(dxBest):
            if self.is_b50: i, j = num // 3, num % 3
            else: i, j = num // 3, num % 3
            
            pngPath = self.cover_dir / f"{get_cover_len5_id(chartInfo.idNum)}.png"
            if not pngPath.is_file(): pngPath = self.cover_dir / "01000.png"
            
            with Image.open(pngPath).convert("RGB") as temp:
                temp = self._resizePic(temp, itemW / temp.size[0])
                temp = temp.crop((0, (temp.size[1] - itemH) / 2, itemW, (temp.size[1] + itemH) / 2))
                temp = temp.filter(ImageFilter.GaussianBlur(3)).point(lambda p: int(p * 0.72))
                tempDraw = ImageDraw.Draw(temp)
                tempDraw.polygon(levelTriagle, Color[chartInfo.diff])
                
                title = chartInfo.title
                if self.is_b50:
                    font = ImageFont.truetype(titleFontName, 16, encoding="utf-8")
                    if self._coloumWidth(title) > 13: title = self._changeColumnWidth(title, 12) + "..."
                else:
                    font = ImageFont.truetype(titleFontName, 16, encoding="utf-8")
                    if self._coloumWidth(title) > 15: title = self._changeColumnWidth(title, 14) + "..."
                tempDraw.text((8, 8), title, "white", font)
                
                if self.is_b50: font = ImageFont.truetype(titleFontName, 12, encoding="utf-8")
                else: font = ImageFont.truetype(titleFontName, 14, encoding="utf-8")
                
                tempDraw.text((7, 28), f'{"%.4f" % chartInfo.achievement}%', "white", font)
                
                with Image.open(self.pic_dir / f"UI_GAM_Rank_{rankPic[chartInfo.scoreId]}.png").convert("RGBA") as rankImg:
                    rankImg = self._resizePic(rankImg, 0.3)
                    temp.paste(rankImg, (88 if not self.is_b50 else 72, 28), rankImg.split()[3])

                if chartInfo.comboId:
                    with Image.open(self.pic_dir / f"UI_MSS_MBase_Icon_{comboPic[chartInfo.comboId]}_S.png").convert("RGBA") as comboImg:
                        comboImg = self._resizePic(comboImg, 0.45)
                        temp.paste(comboImg, (119 if not self.is_b50 else 103, 27), comboImg.split()[3])

                font = ImageFont.truetype(str(STATIC / "adobe_simhei.otf"), 12, encoding="utf-8")
                tempDraw.text((8, 44), f"Base: {chartInfo.ds} -> {chartInfo.ra}", "white", font)
                
                font = ImageFont.truetype(str(STATIC / "adobe_simhei.otf"), 18, encoding="utf-8")
                tempDraw.text((8, 60), f"#{num + 1}", "white", font)

                recBase = Image.new("RGBA", (itemW, itemH), "black").point(lambda p: int(p * 0.8))
                if self.is_b50:
                    img.paste(recBase, (self.COLOUMS_IMG[j + 8] + 5, self.ROWS_IMG[i + 1] + 5))
                    img.paste(temp, (self.COLOUMS_IMG[j + 8] + 4, self.ROWS_IMG[i + 1] + 4))
                else:
                    img.paste(recBase, (self.COLOUMS_IMG[j + 6] + 5, self.ROWS_IMG[i + 1] + 5))
                    img.paste(temp, (self.COLOUMS_IMG[j + 6] + 4, self.ROWS_IMG[i + 1] + 4))
        
        for num in range(len(dxBest), dxBest.size):
            if self.is_b50: i, j = num // 3, num % 3
            else: i, j = num // 3, num % 3
            with Image.open(self.cover_dir / "01000.png").convert("RGB") as temp:
                temp = self._resizePic(temp, itemW / temp.size[0])
                temp = temp.crop((0, (temp.size[1] - itemH) / 2, itemW, (temp.size[1] + itemH) / 2))
                temp = temp.filter(ImageFilter.GaussianBlur(1))
                if self.is_b50:
                    img.paste(temp, (self.COLOUMS_IMG[j + 8] + 4, self.ROWS_IMG[i + 1] + 4))
                else:
                    img.paste(temp, (self.COLOUMS_IMG[j + 6] + 4, self.ROWS_IMG[i + 1] + 4))

    def draw(self):
        splashLogo = Image.open(self.pic_dir / "UI_CMN_TabTitle_MaimaiTitle_Ver214.png").convert("RGBA")
        splashLogo = self._resizePic(splashLogo, 0.65)
        self.img.paste(splashLogo, (10, 10), mask=splashLogo.split()[3])

        ratingBaseImg = Image.open(self.pic_dir / self._findRaPic()).convert("RGBA")
        ratingBaseImg = self._drawRating(ratingBaseImg)
        ratingBaseImg = self._resizePic(ratingBaseImg, 0.85)
        self.img.paste(ratingBaseImg, (240, 8), mask=ratingBaseImg.split()[3])

        namePlateImg = Image.open(self.pic_dir / "UI_TST_PlateMask.png").convert("RGBA")
        namePlateImg = namePlateImg.resize((285, 40))
        namePlateDraw = ImageDraw.Draw(namePlateImg)
        font1 = ImageFont.truetype(str(STATIC / "msyh.ttc"), 28, encoding="unic")
        namePlateDraw.text((12, 4), " ".join(list(self.userName)), "black", font1)
        nameDxImg = Image.open(self.pic_dir / "UI_CMN_Name_DX.png").convert("RGBA")
        nameDxImg = self._resizePic(nameDxImg, 0.9)
        namePlateImg.paste(nameDxImg, (230, 4), mask=nameDxImg.split()[3])
        self.img.paste(namePlateImg, (240, 40), mask=namePlateImg.split()[3])

        shougouImg = Image.open(self.pic_dir / "UI_CMN_Shougou_Rainbow.png").convert("RGBA")
        shougouDraw = ImageDraw.Draw(shougouImg)
        font2 = ImageFont.truetype(str(STATIC / "adobe_simhei.otf"), 14, encoding="utf-8")
        if self.is_b50:
            playCountInfo = f"SD: {self.sdRating} + DX: {self.dxRating} = {self.playerRating}"
        else:
            playCountInfo = f"底分: {self.musicRating} + 段位分: {self.rankRating}"
        shougouImgW, shougouImgH = shougouImg.size
        bbox = shougouDraw.textbbox((0, 0), playCountInfo, font2)
        playCountInfoW, _ = bbox[2] - bbox[0], bbox[3] - bbox[1]
        textPos = ((shougouImgW - playCountInfoW) / 2, 5)
        shougouDraw.text((textPos[0] - 1, textPos[1]), playCountInfo, "black", font2)
        shougouDraw.text((textPos[0] + 1, textPos[1]), playCountInfo, "black", font2)
        shougouDraw.text((textPos[0], textPos[1] - 1), playCountInfo, "black", font2)
        shougouDraw.text((textPos[0], textPos[1] + 1), playCountInfo, "black", font2)
        shougouDraw.text((textPos[0] - 1, textPos[1] - 1), playCountInfo, "black", font2)
        shougouDraw.text((textPos[0] + 1, textPos[1] - 1), playCountInfo, "black", font2)
        shougouDraw.text((textPos[0] - 1, textPos[1] + 1), playCountInfo, "black", font2)
        shougouDraw.text((textPos[0] + 1, textPos[1] + 1), playCountInfo, "black", font2)
        shougouDraw.text(textPos, playCountInfo, "white", font2)
        shougouImg = self._resizePic(shougouImg, 1.05)
        self.img.paste(shougouImg, (240, 83), mask=shougouImg.split()[3])

        self._drawBestList(self.img, self.sdBest, self.dxBest)

        authorBoardImg = Image.open(self.pic_dir / "UI_CMN_MiniDialog_01.png").convert("RGBA")
        authorBoardImg = self._resizePic(authorBoardImg, 0.35)
        authorBoardDraw = ImageDraw.Draw(authorBoardImg)
        authorBoardDraw.text((31, 28), "   Generated By\nXybBot & Chiyuki", "black", font2)
        self.img.paste(authorBoardImg, (1224, 19), mask=authorBoardImg.split()[3])

        dxImg = Image.open(self.pic_dir / "UI_RSL_MBase_Parts_01.png").convert("RGBA")
        if self.is_b50:
            self.img.paste(dxImg, (988, 65), mask=dxImg.split()[3])
            sdImg = Image.open(self.pic_dir / "UI_RSL_MBase_Parts_02.png").convert("RGBA")
            self.img.paste(sdImg, (865, 65), mask=sdImg.split()[3])
        else:
            self.img.paste(dxImg, (890, 65), mask=dxImg.split()[3])
            sdImg = Image.open(self.pic_dir / "UI_RSL_MBase_Parts_02.png").convert("RGBA")
            self.img.paste(sdImg, (758, 65), mask=sdImg.split()[3])

    def getDir(self):
        return self.img


def computeRa(ds: float, achievement: float, is_b50: bool = False) -> int:
    if is_b50:
        baseRa = 22.4
        if achievement < 50: baseRa = 7.0
        elif achievement < 60: baseRa = 8.0
        elif achievement < 70: baseRa = 9.6
        elif achievement < 75: baseRa = 11.2
        elif achievement < 80: baseRa = 12.0
        elif achievement < 90: baseRa = 13.6
        elif achievement < 94: baseRa = 15.2
        elif achievement < 97: baseRa = 16.8
        elif achievement < 98: baseRa = 20.0
        elif achievement < 99: baseRa = 20.3
        elif achievement < 99.5: baseRa = 20.8
        elif achievement < 100: baseRa = 21.1
        elif achievement < 100.5: baseRa = 21.6
    else:
        baseRa = 15.0
        if achievement >= 50 and achievement < 60: baseRa = 5.0
        elif achievement < 70: baseRa = 6.0
        elif achievement < 75: baseRa = 7.0
        elif achievement < 80: baseRa = 7.5
        elif achievement < 90: baseRa = 8.0
        elif achievement < 94: baseRa = 9.0
        elif achievement < 97: baseRa = 9.4
        elif achievement < 98: baseRa = 10.0
        elif achievement < 99: baseRa = 11.0
        elif achievement < 99.5: baseRa = 12.0
        elif achievement < 99.99: baseRa = 13.0
        elif achievement < 100: baseRa = 13.5
        elif achievement < 100.5: baseRa = 14.0

    return math.floor(ds * (min(100.5, achievement) / 100) * baseRa)


async def generate(payload: Dict, is_b50: bool = False) -> Tuple[Optional[Image.Image], int, Optional[str]]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://www.diving-fish.com/api/maimaidxprober/query/player",
            json=payload,
        )
        if resp.status_code == 400: return None, 400, None
        if resp.status_code == 403: return None, 403, None
        
        obj = resp.json()
        if is_b50:
            sd_best = BestList(35)
            dx_best = BestList(15)
        else:
            sd_best = BestList(25)
            dx_best = BestList(15)

        dx: List[Dict] = obj["charts"]["dx"]
        sd: List[Dict] = obj["charts"]["sd"]
        for c in sd:
            sd_best.push(await ChartInfo.from_json(c))
        for c in dx:
            dx_best.push(await ChartInfo.from_json(c))

        nickname = obj["nickname"]
        
        if is_b50:
            sd_rating = sum(computeRa(c.ds, c.achievement, is_b50) for c in sd_best)
            dx_rating = sum(computeRa(c.ds, c.achievement, is_b50) for c in dx_best)
            total_rating = sd_rating + dx_rating
            text_result = f"玩家: {nickname}\n"
            text_result += f"Rating: {total_rating} (SD: {sd_rating} + DX: {dx_rating})\n\n"
            text_result += "--- SD Best (B35) ---\n"
            for i, chart in enumerate(sd_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {computeRa(chart.ds, chart.achievement, is_b50)}\n"
            
            text_result += "\n--- DX Best (B15) ---\n"
            for i, chart in enumerate(dx_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {computeRa(chart.ds, chart.achievement, is_b50)}\n"

            pic = DrawBest(sd_best, dx_best, nickname, total_rating, 0, is_b50=True).getDir()
            
            return pic, 0, text_result
        else:
            rating = obj["rating"]
            additional_rating = obj["additional_rating"]
            total_rating = rating + additional_rating
            text_result = f"玩家: {nickname}\n"
            text_result += f"Rating: {total_rating} (底分: {rating} + 段位分: {additional_rating})\n\n"
            text_result += "--- SD Best (B25) ---\n"
            for i, chart in enumerate(sd_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {chart.ra}\n"
            
            text_result += "\n--- DX Best (B15) ---\n"
            for i, chart in enumerate(dx_best):
                text_result += f"#{i+1}: {chart.title} [{diffs[chart.diff]}] | DS: {chart.ds:.1f}, Ach: {chart.achievement:.4f}%, RA: {chart.ra}\n"

            pic = DrawBest(sd_best, dx_best, nickname, total_rating, rating, is_b50=False).getDir()
            
            return pic, 0, text_result