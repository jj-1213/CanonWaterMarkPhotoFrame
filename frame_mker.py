# _*_ coding utf-8 -*-
# @time     :2025/8/16    20:27
# @Author   :NB.jiang
# @filename :frame_maker.py

"""
给照片添加水印相框
看网上说依赖：pillow
用法示例：

"""
# -----------------           导入依赖             -----------------  #

import os
import math
import argparse
import exifread
from PIL import Image, ImageDraw, ImageFont, ExifTags
from typing import Dict, Any, Optional, Tuple


# -----------------           EXIF 相关工具函数             -----------------  #
def _get_exif_dict(img: Image.Image) -> Dict[str, Any]:
    """
    获取图片的EXIF信息, 并把tag 数字映射为小姜可读得名字
    但所有照片都有EXIF吗？没有的话返回空字典
    :param img: PIL Image对象
    """
    exif = {}
    try:
        raw = img.getexif()
        if not raw:
            return {}

        tag_map = {v:k for k, v in ExifTags.TAGS.items()}

        for tag_id, value in raw.items():
            tag_name = ExifTags.TAGS.get(tag_id, tag_id)
            exif[tag_name] = value
    except Exception as e:
        return {}
    return exif


def _rational_to_float(val: Any) -> Optional[float]:
    """
    把EXIF中所有数字信息转换为浮点数
    :param val: EXIF中表示经纬度的分数
    :return: 浮点数
    """
    try:
        # 先将照片 IFDRational 支持直接转 flaot

        return float(val)
    except Exception as e:
        pass

    if isinstance(val, (tuple, list)) and len(val) == 2:
        num, den  = val
        try:
            return float(num) / float(den)
        except Exception as e:
            return None

    # 当上面转换不成功时，尝试强转 (但可能会出错）
    try:
        return float(val)
    except Exception as e:
        return None


def _format_exposure_time(val: Any) -> Optional[str]:
    """
    格式化曝光时间
    - 小于1秒的，显示为分数形式，如1 / n s （但当不是近似 1 / n 时，显示为小数形式，如0.3s）
    - 大于等于1秒的，显示为整数形式，如 n s(n为整数或一位小数）)
    :param val: EXIF中表示曝光时间的值
    :return: 格式化后的字符串
    """
    t = _rational_to_float(val)
    if t is None or t <= 0:
        return None

    if t < 1.0:
        # 试图把t表示为1/n的形式
        denom = round(1.0 / t)
        if denom > 0 and abs(1.0 / denom -t) < 0.02 *  t:
            return f"1/{denom}s"
        # 否则显示为小数形式
        return f"{t:.3f}s"
    else:
        # 大于等于1秒的，显示为整数形式，如 n s(n为整数或一位小数）)
        if abs(t - round(t)) < 0.05:
            return f"{int(round(t))}s"
    
        return f"{t:.1f}s"


def _format_fnumber(val:Any) -> Optional[str]:
  """
  Fnumber (光圈) 格式化 为 F1.8 或者 F2.8 的形式
  :param val: EXIF中表示光圈的值
  :return: 格式化后的字符串
  """
  f = _rational_to_float(val)
  if f is None or f <= 0:
    return None
  # 如果小于10，保留一位小数，否则保留整数
  return f"F{f:.1f}".rstrip('0').rstrip('.')

def _format_focal(val:Any) -> Optional[str]:
    """
    焦距格式化为 50mm 或者 50.0mm 的形式
    :param val: EXIF中表示焦距的值
    :return: 格式化后的字符串
    """
    fl = _rational_to_float(val)
    if fl is None or fl <= 0:
        return None
    # 如果小于10，保留一位小数，否则保留整数
    return f"{f:.1f}mm".rstrip('0').rstrip('.')

def extract_camera_params(img: Image.Image) -> Dict[str, str]:
  """
  从图片 EXIF 中提取相机参数， 返回可直接用于渲染的字符串字典
  可能除了光圈快门感光度外，还会有其他信息 Key: brand model lens focal fnumber shutter ios
  :param img: PIL Image对象
  :return: 相机参数字典
  """
  exif = _get_exif_dict(img)
  out = {}

  # 提取品牌和型号
  brand = str(exif.get("Make", "")).strip()
  model = str(exif.get("Model", "")).strip()
  if brand :
    out["brand"] = brand
  if model:
    out["model"] = model

  # 提取镜头信息(如果有的话)
  lens = exif.get("LensModel") or exif.get("LensMake")
  if lens:
    out["lens"] = str(lens).strip()

  # 提取焦距 光圈 快门 感光度
  focal = exif.get("FocalLength")
  fnumber = exif.get("FNumber") or exif.get("ApertureValue")
  shutter = exif.get("ExposureTime") or exif.get("ShutterSpeedValue")

  iso = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity")

  focal_s = _format_focal(focal) if focal is not None else None
  fnum_s = _format_fnumber(fnumber) if fnumber is not None else None
  shutter_s = _format_exposure_time(shutter) if shutter is not None else None


  # iso 直接转换成字符串
  try :
    if isinstance(iso, (list, tuple)) and len(iso) > 0:
      iso_val = iso[0]
    else:
      iso_val = int(iso)
    iso_s = f"ISO{iso_val}"
  except Exception as e:
    iso_s = None

  # 添加到输出字典
  if focal_s:
    out["focal"] = focal_s
  if fnum_s:
    out["fnumber"] = fnum_s
  if shutter_s:
    out["shutter"] = shutter_s
  if iso_s:
    out["iso"] = iso_s
  return out



#  -------------           水印相框样式配置             -----------------  #

DeFAULT_TEMPLATE: Dict[str, Dict[str, Any]] = {
  # 眼红阿哲的尼康水印边框（好吧，承认没有好的相框样式点子） 
  # “Nikon_Style” 上下边距小、底部大留白、相机logo居中第一行、下面几行合理排布照片参数
  "Nikon_like":{
    "border_px": 20,  # 图片四周细边框边框宽度
    "bottom_band_ratio": 0.18, # 底部留白占整个图片高度的比例  底部留白高度 = radio * 图片高度
    "bg_color": (255, 255, 255),  # 背景颜色 RGB (白色)
    "border_color": (0, 0, 0),  # 边框颜色 RGB (黑色)
    "text_color": (0, 0, 0),  # 文本颜色 RGB (黑色)
    "brand_font_size_ratio": 0.06, # 品牌型号字体大小占图片高度的比例  logo字号 = ratio * 图片高度
    "meta_font_size_ratio": 0.026, # 相机参数字体大小占图片高度的比例  参数字号 = ratio * 图片高度
    "logo_max_height_ratio": 0.08, # 相机logo最大高度占图片高度的比例 logo高度 = ratio * 图片高度
    "gap_ratio": 0.015,  # 相机logo和品牌型号之间的间距占图片高度的比例
    "use_logo": True,  # 是否使用相机logo
    "show_brand_text": True,  # 是否显示品牌型号文本
    "show_meta_text": True,  # 是否显示相机参数文本
  },

  # 配置二： 那就是著名的反转黑白颜色了,顺便不显示参数了 （再次承认没点子） 
  "minimal_black":{
    "border_px": 0,
    "bottom_band_ratio": 0.14,  # 底部留白占整个图片高度的比例
    "bg_color": (0, 0, 0),  # 背景颜色 RGB (黑色)
    "border_color": (255, 255, 255),  # 边框颜色 RGB (白色)
    "text_color": (255, 255, 255),  # 文本颜色 RGB (白色)
    "brand_font_size_ratio": 0.055,  # 品牌型号字体大小占图片高度的比例
    "logo_max_height_ratio": 0.08,  # 相机logo最大高度占图片高度的比例
    "gap_ratio": 0.012,  # 相机logo和品牌型号之间的间距占图片高度的比例
    "use_logo": True,  # 是否使用相机logo
    "show_brand_text": False,  # 是否显示品牌型号文本
  },

}


# -----------------           绘制工具： 字体 文本 logo             -----------------  #
def load_font(preferred_paths, size: int) -> ImageFont.FreeTypeFont:
    """
    尝试加载指定路径的字体文件
    :param preferred_paths: 字体文件路径列表
    :param size: 字体大小
    :return: PIL ImageFont对象 或 None
    """
    for p in preferred_paths:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size = size)
            except Exception as e:
                print(f"加载字体失败: {path}, 错误: {e}")
    return ImageFont.load_default()

def draw_centered_text(draw: ImageDraw.ImageDraw,
                      text: str,
                      font: ImageFont.FreeTypeFont,
                      canvas_w: int,
                      y: int,
                      color=(0, 0, 0)) -> int:
  """
  在指定的y坐标处水平居中绘制文本; 返回文本底部 y坐标
  :param draw: PIL ImageDraw对象
  :param text: 要绘制的文本
  :param font: PIL ImageFont对象
  :param canvas_w: 画布宽度
  :param y: 文本顶部y坐标
  :param color: 文本颜色
  :return: 文本底部y坐标
  """

  text_w, text_h = draw.textbbox((0, 0), text, font = font)[2 : ]
  x = (canvas_w - text_w) // 2
  draw.text((x, y), text, font = font, fill = color)
  return y + text_h

def paste_logo_center(canvas: Image.Image,
                      logo_path: str,
                      max_height: int,
                      y: int) -> Tuple[int, int]:
  """
  在画布上居中粘贴logo图片 按 max_height 等比缩放水平居中粘贴到 canvas 的y坐标处
  :param canvas: PIL Image对象
  :param logo_path: logo图片路径
  :param max_height: logo最大高度
  :param y: logo顶部y坐标
  :return: logo的实际宽度和高度
  """ 
  try:
    # 确保logo是RGBA模式
    logo = Image.open(logo_path)
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')
  except Exception as e:
    print(f"加载logo失败: {logo_path}, 错误: {e}")
    return y, 0

  # 等比缩放logo (不放大超过 max_height)
  w, h = logo.size
  if h > max_height:
    scale = max_height / float(h)
    logo = logo.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    w, h = logo

  x = ( canvas.width - w ) // 2
  # 粘贴logo到画布
  canvas.alpha_composite(logo, dest = (x, y))
  return y + h, h


# -----------------           主函数：添加水印相框             -----------------  #
def make_framed_image(img_path: str,
                      out_path: str,
                      logo_path: Optional[str] = None,
                      template_name: str = "Nikon_like",
                      preferred_fonts = None,) -> None:
  """
  给照片添加水印相框
  读取原图 ——> 提取EXIF信息 ——> 创建留白相框 ——> 绘制相机参数文本 ——> 粘贴logo ——> 保存新图
  :param img_path: 原图路径
  :param out_path: 输出图片路径
  :param logo_path: 相机logo路径 (可选)
  :param template_name: 相框模板名称
  :param preferred_fonts: 字体文件路径列表  （期望 可以实现多个字体路径以便跨平台）
  """
  if preferred_fonts is None:
    preferred_fonts = [
      # 把常用字体路径加在最前面
        "arial.ttf",  # Windows
        "SimHei.ttf",  # Windows
        "SourceHanSansCN-Regular.otf",  # Adobe Source Han Sans
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "/Library/Fonts/Arial.ttf"  # macOS
    ]

  # 载入配置
  tpl = DeFAULT_TEMPLATE.get(template_name, DeFAULT_TEMPLATE["Nikon_like"])
  # 打开原图并确保是RGB
  try:
    src = Image.open(img_path).convert("RGB")
  except Exception as e:
    print(f"打开图片失败: {img_path}, 错误: {e}")
    return
  w,h = src.size

  # 提取 EXIF 信息
  params = extract_camera_params(src)

  # 参数进行组装 粘入文本
  pieces = []
  for key in ['focal', 'fnumber', 'shutter', 'iso']:
    if params.get(key):
      pieces.append(params[key])
  meta_line = "  ".join(pieces) if pieces else "No EXIF Data"

  brand_text = params.get("brand") or "Canon"

  # 计算画布尺寸： 左右细边框 + 底部留白

  border_px = int(tpl["border_px"])
  bang_h = int(tpl["bottom_band_ratio"] * w)
  canvas_w = w + 2 * border_px
  canvas_h = h + bang_h + border_px * 2
  # 创建RGBA画布以支持透明通道
  canvas = Image.new("RGBA", (canvas_w, canvas_h), color=tpl["bg_color"] + (255,))
  draw = ImageDraw.Draw(canvas)

  # 绘制细边框
  if border_px > 0:
    draw.rectangle(
      [0, 0, canvas_w - 1, canvas_h - 1],
      outline=tpl["border_color"],
      width=1
    )
  # 粘贴原图到画布中间位置
  canvas.paste(src, (border_px, border_px))
  # 绘制底部留白区域
  band_top = border_px + h
  band_bottom = canvas_h - border_px
  band_height = band_bottom - band_top

  # 字号基于画布进行自适应 （比例计算）
  brand_font_size = max(12, int(tpl["brand_font_size_ratio"] * canvas_w))
  meta_font_size = max(10, int(tpl["meta_font_size_ratio"] * canvas_w))
  gap = int(tpl["gap_ratio"] * canvas_w)
  logo_max_h = int(tpl["logo_max_height_ratio"] * canvas_w)

  brand_font = load_font(preferred_fonts, brand_font_size)
  meta_font = load_font(preferred_fonts, meta_font_size)  

  # 在留白区域垂直居中排布： logo -> 品牌型号 -> 相机参数
  cur_y = band_top + max(4, (band_height - (logo_max_h + brand_font_size + meta_font_size + gap)) // 2)

  # 1) Logo 
  if tpl["use_logo"] and logo_path and os.path.exists(logo_path):
    cur_y, logo_h = paste_logo_center(canvas, logo_path, logo_max_h, cur_y)
    cur_y += gap // 2 # logo和品牌型号之间的间距
  else:
    logo_h = 0

  # 2) 品牌型号
  if tpl.get("show_brand_text", True) and brand_text:
    cur_y = draw_centered_text(
      draw, brand_text, brand_font, canvas_w, cur_y, color=tpl["text_color"]
    )
    cur_y += gap # 品牌型号和相机参数之间的间距

  # 3) 相机参数
  if meta_line:
    cur_y  =draw_centered_text(
      draw, meta_line, meta_font, canvas_w, cur_y, color=tpl["text_color"]
    )

  # 保存新图
  # 如果out_path没有目录部分，保存到当前目录
  if not os.path.dirname(out_path):
      out_path = os.path.join(os.getcwd(), out_path)
  
  # 确保有.jpg扩展名
  if not out_path.lower().endswith('.jpg'):
      out_path += '.jpg'
  
  # 创建输出目录（如果需要）
  out_dir = os.path.dirname(out_path)
  if out_dir:
      os.makedirs(out_dir, exist_ok=True)
  
  canvas.convert("RGB").save(out_path, quality=95)
  print(f"已保存处理后的图片到: {os.path.abspath(out_path)}")

# -----------------           命令行接口:单张 / 批量             -----------------  #
def is_image_file(name: str) -> bool:
    """
    判断文件是否为图片
    :param name: 文件名
    :return: 是否为图片文件
    """
    ext = os.path.splitext(name)[1].lower()
    return ext in['.png', '.jpg', '.jpeg', '.bmp', '.gif']

# -----------------           主函数             -----------------  #
def main(): 
  parser = argparse.ArgumentParser(description="给照片添加相机Logo与参数相框")
  g = parser.add_mutually_exclusive_group(required=True)
  g.add_argument("--input", help="输入单张图片路径")
  g.add_argument("--input_dir", help="输入图片目录路径(批量处理)")

  parser.add_argument("--out", help="输出单张图片路径（不指定完整路径时将保存到当前目录）")
  parser.add_argument("--output_dir", help="输出目录路径(批量处理)")
  parser.add_argument("--logo", help="相机Logo图片路径 (可选)", default=None)
  parser.add_argument("--template", help="相框模板名称：Nikon_like / minimal_black", default="Nikon_like")
  parser.add_argument("--font", action = "append", default = [], help = "字体文件路径列表 (可多次指定，优先级从前到后)(可选, 多个路径用逗号分隔)")

  args = parser.parse_args()

  # 合并字体到搜索路径，用户传入的在最前

  preferred_fonts = (args.font or []) + [
      "arial.ttf",  # Windows
      "SimHei.ttf",  # Windows
      "SourceHanSansCN-Regular.otf",  # Adobe Source Han Sans
      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
      "/Library/Fonts/Arial.ttf"  # macOS
  ]

  if args.input:
    if not args.out:
      # 如果没有指定输出路径，使用输入文件名加上_framed后缀
      base_name = os.path.splitext(os.path.basename(args.input))[0]
      args.out = f"{base_name}_framed"
    
    make_framed_image(
      img_path = args.input,
      out_path = args.out,
      logo_path = args.logo,
      template_name = args.template,
      preferred_fonts = preferred_fonts
    )
  else:
    # 批量处理
    if not args.output_dir:
      raise SystemExit("批量处理需指定 --output_dir 参数")
    os.makedirs(args.out_dir, exist_ok=True)

    for name in os.listdir(args.input_dir):
      if not is_image_file(name):
        continue
      inp = os.path.join(args.input_dir, name)
      outp = os.path.join(args.out_dir, os.path.splitext(name)[0] + "_framed.jpg")
      try:
        make_framed_image(
          img_path = inp,
          out_path = outp,
          logo_path = args.logo,
          template_name = args.template,
          preferred_fonts = preferred_fonts
        )
      except Exception as e:
        print(f"处理图片失败: {inp}, 错误: {e}")


if __name__ == "__main__":
  main()
  # 仅在直接运行脚本时执行
  # 如果是被导入模块则不执行
  # 这样可以避免在导入时执行 main() 函数
  # 方便其他脚本导入此模块时不执行 main()




















