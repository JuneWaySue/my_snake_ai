from zipfile import ZipFile,ZIP_DEFLATED
from os import environ,makedirs
from os.path import basename
from random import seed as random_seed
from time import time
from torch import manual_seed
from torch.cuda import manual_seed as cuda_manual_seed,manual_seed_all
from numpy import sin as np_sin
from numpy.random import seed as np_seed,randint as np_randint
from torch.backends import cudnn
from PyQt5.QtGui import QLinearGradient,QColor

def seed_everything(seed):
    random_seed(seed)
    environ['PYTHONHASHSEED'] = str(seed)
    np_seed(seed)
    manual_seed(seed)
    cuda_manual_seed(seed)
    manual_seed_all(seed)
    cudnn.deterministic = True # some cudnn methods can be random even after fixing the seed unless you tell it to be deterministic
    cudnn.benchmark = False # 提升速度，主要对input shape是固定时有效，如果是动态的，耗时反而慢
    # cudnn.enabled = True # cuDNN使用的非确定性算法就会自动寻找最适合当前配置的高效算法，来达到优化运行效率的问题

class Struct:
    def __init__(self, **entries):
        self.__dict__.update(entries)

def neon_gradient_colors(steps, base_color=(0, 255, 150)):
    """赛博朋克风格霓虹渐变"""
    colors = []
    pulse_speed = 0.1  # 光脉动速度
    
    for i in range(steps):
        # 基础颜色
        r,g,b = base_color
        
        # 动态光效（模拟电压不稳定效果）
        flicker = 0.9 + 0.1*np_sin(i*0.3 + time()*5)
        wave = 0.8 + 0.2*np_sin(i*pulse_speed)
        
        # 颜色增强
        r = int(r * flicker * wave)
        g = int(g * flicker * wave)
        b = int(b * flicker * (wave**2))
        
        # 限制最大值
        r = min(r, 255)
        g = min(g, 255)
        b = min(b, 255)
        
        colors.append((r,g,b))
    
    return colors


def random_xy(args):
    x = np_randint(0, args.grid_width)
    y = np_randint(0, args.grid_height)

    return [x,y]

# 压缩文件
def zip_files(files_to_zip,zip_name="snake.zip"):
    with ZipFile(zip_name, "w",compression=ZIP_DEFLATED) as zipf:
        for file in files_to_zip:
            # 使用arcname参数去掉父目录路径
            zipf.write(file, arcname=basename(file))

# 解压文件
def unzip_files(extract_dir,zip_name="snake.zip"):
    makedirs(extract_dir, exist_ok=True)
    with ZipFile(zip_name, "r") as zipf:
        zipf.extractall(extract_dir)

def rgb_to_hex(rgb):
    """将RGB元组转换为十六进制颜色代码"""
    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])

def get_rect_size(args):
    for rect_size in range(1,10000):
        if (args.grid_width * rect_size + args.info_width) < (args.screen_width * 0.95) \
            and (args.grid_height * rect_size) < (args.screen_height * 0.9):
            pass
        else:
            break
    else:
        rect_size = 1
    
    return rect_size

def get_gradient_colors(num_samples=100):
    gradient = QLinearGradient(0, 10, 20, 20)
    gradient.setColorAt(0, QColor(255, 0, 0))      # 红色
    gradient.setColorAt(0.2, QColor(255, 69, 0))    # 橙色
    gradient.setColorAt(0.35, QColor(222, 150, 0))    # 黄色
    gradient.setColorAt(0.5, QColor(0, 200, 0))      # 绿色
    gradient.setColorAt(0.65, QColor(30, 144, 255))     # 蓝色
    gradient.setColorAt(0.8, QColor(255, 105, 180))     # 粉色
    gradient.setColorAt(1, QColor(148, 0, 211))     # 紫色

    # 获取渐变停止点并排序
    stops = sorted(gradient.stops(), key=lambda s: s[0])
    
    colors = []
    for i in range(num_samples):
        # 计算当前采样位置 (0.0 - 1.0)
        pos = i / (num_samples - 1)
        
        # 找到相邻的停止点
        left_stop = None
        right_stop = None
        for j in range(len(stops)):
            if stops[j][0] >= pos:
                right_stop = stops[j]
                left_stop = stops[j-1] if j > 0 else stops[j]
                break
        else:
            left_stop = stops[-1]
            right_stop = stops[-1]
        
        # 计算插值比例
        if left_stop[0] == right_stop[0]:
            ratio = 0.0
        else:
            ratio = (pos - left_stop[0]) / (right_stop[0] - left_stop[0])
        
        # 插值颜色分量
        left_color = left_stop[1]
        right_color = right_stop[1]
        
        r = left_color.red() + ratio * (right_color.red() - left_color.red())
        g = left_color.green() + ratio * (right_color.green() - left_color.green())
        b = left_color.blue() + ratio * (right_color.blue() - left_color.blue())
        a = left_color.alpha() + ratio * (right_color.alpha() - left_color.alpha())
        
        colors.append((int(r), int(g), int(b), int(a)))
    
    return colors