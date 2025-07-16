import sys
from time import time
from datetime import datetime
from math import sin as math_sin,cos as math_cos,radians as math_radians
from random import random as random_random, choice as random_choice,randint as random_randint,uniform as random_uniform
from os.path import dirname,abspath,join,exists
from os import listdir
from copy import deepcopy
from collections import OrderedDict,defaultdict
from itertools import permutations

from numpy.random import choice as np_choice,shuffle as np_shuffle
from numpy import array as np_array,sin as np_sin,cos as np_cos,\
    pi as np_pi,argmax as np_argmax,inf as np_inf

from PyQt5.QtGui import QLinearGradient,QRadialGradient,QFont,\
    QPainterPath,QConicalGradient,QPixmap,QIcon,\
    QFontMetricsF,QFontDatabase,QBrush,QPainter,\
    QColor, QPen, QFontMetrics,QKeySequence
from PyQt5.QtCore import Qt, QTimer, QTime, pyqtSignal,\
    QPropertyAnimation,QEasingCurve,QPoint,pyqtProperty,\
    QRect,QSize,QEvent,QUrl,QParallelAnimationGroup,QAbstractAnimation
from PyQt5.QtWidgets import QWidget, QMainWindow, \
    QMessageBox, QPushButton, QVBoxLayout, QHBoxLayout,\
    QComboBox,QLabel,QStackedWidget,QGroupBox,QDialog,\
    QSlider,QTabWidget,QColorDialog,QScrollArea,QApplication,QShortcut
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist,\
    QAudioDeviceInfo,QAudio
from concurrent.futures import ThreadPoolExecutor

from utils import random_xy,neon_gradient_colors,rgb_to_hex,\
    get_gradient_colors,get_rect_size

class Food():
    def __init__(self, args):
        self.args = args
        self.max_score = args.grid_width * args.grid_height
        self.foods = []  # 存储多个食物
        self.eated = [] # 存储已经吃掉的食物，用于绘画吃掉时的特效

    def remove(self, food):
        """移除指定的食物"""
        self.foods.remove(food)
        self.eated.append(food)

    def respawn(self, snakes):
        """确保食物不生成在任意蛇身上"""
        score = sum([len(snake.body) for snake in snakes])
        while len(self.foods) < min(len(snakes),self.max_score-score) and score < self.max_score:  # 确保至少有len(snakes)个食物
            new_food = random_xy(self.args)
            if not any([new_food in snake.body for snake in snakes]):
                if new_food not in self.foods:  # 检查新食物是否在食物列表中
                    self.foods.append(new_food)

class Snake():
    def __init__(self,args,number=1,loc=0):
        assert number in [1,2]
        assert loc in [0,1,2,3,4] # 初始位置
        self.args = args
        self.number = number
        self.loc = loc
        self.loc_map = {
            0: [[self.args.grid_width//2,self.args.grid_height//2]], # center
            1: [[self.args.grid_width//4,self.args.grid_height//4]], # upper left
            2: [[self.args.grid_width-self.args.grid_width//4,self.args.grid_height//4]], # upper right
            3: [[self.args.grid_width//4,self.args.grid_height-self.args.grid_height//4]],# lower left
            4: [[self.args.grid_width-self.args.grid_width//4,self.args.grid_height-self.args.grid_height//4]], # lower right
        }
        self.d_map = {
            'right': [1, 0],
            'left': [-1, 0],
            'down': [0, 1],
            'up': [0, -1],
            'none': [0, 0],
        }

        # 初始化
        self.reset()

    def reset(self):
        self.body = self.loc_map[self.loc]
        self.direction = self.args.first_direction if hasattr(self.args,'first_direction') else 'none'
        self.tail = self.body[-1] # 记录移动前的蛇尾

    def move(self):
        new_head = (np_array(self.body[0])+np_array(self.d_map[self.direction])).tolist()
        self.body.insert(0, new_head)
        self.tail = self.body.pop() # 记录移动前的蛇尾

    def changeDirection(self, key):
        if key == Qt.Key_Up and self.direction != 'down':
            self.direction = 'up'
        elif key == Qt.Key_Right and self.direction != 'left':
            self.direction = 'right'
        elif key == Qt.Key_Down and self.direction != 'up':
            self.direction = 'down'
        elif key == Qt.Key_Left and self.direction != 'right':
            self.direction = 'left'

    def grow(self):
        self.body.append(self.tail) # 增添移动前的蛇尾

    def isCollidingWithSelf(self):
        if len(self.body) > 1:
            return self.body[0] in self.body[1:]
        else:
            return False

    def isCollidingWithFood(self, food):
        return tuple(self.body[0]) == tuple(food)
    
    def isOutOfBounds(self):
        head = self.body[0]
        return (
            head[0] < 0 or 
            head[1] < 0 or 
            head[0] >= self.args.grid_width or 
            head[1] >= self.args.grid_height
        )
    
    def isCollidingWithOther(self, another):
        """检查是否与其他蛇发生碰撞"""
        # 头撞对方身体的判定
        head_collision = [
            self.body[0] in another.body[1:],  # 我方头撞对方身
            another.body[0] in self.body[1:]    # 对方头撞我方身
        ]
        
        # 头对头碰撞
        head_to_head = self.body[0] == another.body[0]
        
        return head_collision + [head_to_head]

class GameConfigManager:
    def __init__(self):
        self.colors_map = {
            (222, 0, 0):'红色',
            (30, 144, 255):'蓝色',
            (255, 69, 0):'橙色',
            (222, 150, 0):'黄色',
            (0, 200, 0):'绿色',
            # (75, 0, 130):'靛色',
            (255, 105, 180):'粉色',
            (148, 0, 211):'紫色',
            (50, 50, 50):'黑色',
            (200, 200, 200):'白色',
        }

        self.all_presets = list(permutations(list(self.colors_map.keys()),2))
        self.color_presets = random_choice(self.all_presets)
        self.cur_color_idx = self.all_presets.index(self.color_presets)

        self.configs = {
            "单人游戏": {
                'fps':60,
                1: {"player": "Human", "ctrl": "default","color": self.color_presets[0]},
                2: {}
            },
            "单机游戏": {
                'fps':1,
                1: {"player": "AI-DQN1", "agent": "AI-DQN1","color": self.color_presets[0]},
                2: {}
            },
            "双人对战": {
                'fps':60,
                1: {"player": "Human", "ctrl": "wsad","color": self.color_presets[0]},
                2: {"player": "Human", "ctrl": "default","color": self.color_presets[1]}
            },
            "人机对战": {
                'fps':60,
                1: {"player": "Human", "ctrl": "default","color": self.color_presets[0]},
                2: {"player": "AI-DQN1", "agent": "AI-DQN1","color": self.color_presets[1]}
            },
            "双机对战": {
                'fps':1,
                1: {"player": "AI-DQN1", "agent": "AI-DQN1","color": self.color_presets[0]},
                2: {"player": "AI-DQN2", "agent": "AI-DQN2","color": self.color_presets[1]}
            }
        }

        for mode,number in zip(['单机游戏','人机对战','双机对战','双机对战'],[1,2,1,2]):
            self.configs[mode][number]['player'] = np_choice(['AI-DQN1','AI-DQN2','Rule-BFS'])
            self.configs[mode][number]['agent'] = self.configs[mode][number]['player']

        # 添加网格尺寸预设
        self.sizes = {
            '10x10': (10, 10),
            '20x20': (20, 20),
            '30x30': (30, 30),
            '40x40': (40, 40),
            '50x40': (50, 40),
        }
        self.current_size = '50x40'  # 默认尺寸

class RotateMenuWidget(QWidget):
    def __init__(self, title, width, height, rect_size):
        super().__init__()
        self.title = title
        self.neon_colors = {
            "border": QColor(0, 255, 255),
            "hover_border": QColor(255, 0, 255),
            "text": QColor(200, 220, 255),
            "glow": QColor(100, 255, 255, 50)
        }

        self.tooltips = {
            "单人游戏": ["玩家控制蛇，独自挑战",'👤'],
            "单机游戏": ["AI自动控制蛇，观看AI表演",'🤖'],
            "双人对战": ["两名玩家分别控制两条蛇进行对战",'👤👤'],
            "人机对战": ["玩家与AI分别控制两条蛇进行对战",'👤🤖'],
            "双机对战": ["两个AI分别控制两条蛇进行对战",'🤖🤖']
        }

        self.init_size(width, height, rect_size)
        self.angle = 0

        # 动画设置（更快更流畅）
        self.anim = QPropertyAnimation(self, b"angle")
        self.anim.setDuration(10000)
        self.anim.setStartValue(0)
        self.anim.setEndValue(360)
        self.anim.setEasingCurve(QEasingCurve.Linear)
        self.anim.setLoopCount(-1)
        self.anim.start()

    def init_size(self, width, height, rect_size):
        self.rect_size = rect_size
        self.base_size = min(width, height)  # 基础尺寸参考值

        # 自适应计算尺寸
        self.button_size = int(self.base_size * 0.18)  # 按钮大小占屏幕30%
        self.font_size = int(self.button_size * 0.15)  # 字体大小与按钮成比例
        self.radius = int(self.button_size * 2)  # 旋转半径

        if not hasattr(self,'buttons'):
            self.buttons = []
        self.setFixedSize(width, height)
        self.center = QPoint(width//2, height//2)

        btn_style = f"""
            QPushButton {{
                font: bold {self.font_size}px "Arial Black";
                color: {self.neon_colors['text'].name()};
                min-width: {self.button_size}px;
                min-height: {self.button_size}px;
                border: 2px solid {self.neon_colors['border'].name()};  /* 变细的边框 */
                border-radius: {self.button_size//2}px;
                background-color: rgba(30, 30, 50, 0);  /* 透明背景 */
                /*text-shadow: 0 0 5px {self.neon_colors['text'].name()};*/  /* 减少阴影强度 */
                padding: 15px;
            }}
            QPushButton:hover {{
                background-color: rgba(50, 50, 70, 220);
                border: 2px solid {self.neon_colors['hover_border'].name()};  /* 悬停时变色 */
                /*box-shadow: 0 0 10px {self.neon_colors['glow'].name()};*/  /* 减少发光范围 */
            }}
            QToolTip {{
                color: #e0e0e0;
                background-color: rgba(50, 50, 70, 220);
                border: 1px solid {self.neon_colors['border'].name()};
                border-radius: 5px;
                padding: 5px;
                font: bold {self.font_size}px "Arial";
            }}
        """

        if len(self.buttons) == 0:
            # 创建按钮
            modes = ["👤\n单人游戏", "🤖\n单机游戏", "👤👤\n双人对战", "👤🤖\n人机对战", "🤖🤖\n双机对战"]
            for mode in modes:
                mode_name = mode.split('\n')[1]
                btn = QPushButton(mode, self)
                btn.setFixedSize(self.button_size, self.button_size)
                btn.setProperty("mode", mode_name)
                btn.setStyleSheet(btn_style)
                btn.setMouseTracking(True)
                btn.installEventFilter(self)
                self.buttons.append(btn)
        else:
            for btn in self.buttons:
                btn.setFixedSize(self.button_size, self.button_size)
                btn.setStyleSheet(btn_style)

    def _update_button_tooltip(self,config_manager,volume,audio_available):
        """更新按钮的提示"""
        size = config_manager.current_size
        configs = config_manager.configs
        colors_map = config_manager.colors_map
        for btn in self.buttons:
            # 获取当前配置信息
            mode_name = btn.property("mode")
            config = configs[mode_name]
            # 构建HTML格式的配置描述（支持颜色显示）
            config_desc = f"<b>大小：</b>{size}<br><b>FPS：</b>{config['fps']}<br><br>"
            ctrl_map = {'default': '⬆️⬇️⬅️➡️', 'wsad': 'WSAD'}
            if mode_name == "单人游戏":
                ctrl_type = ctrl_map[config[1].get('ctrl', config[2].get('ctrl'))]
                color = rgb_to_hex(config[1].get('color', config[2].get('color')))
                color_text = colors_map[config[1].get('color', config[2].get('color'))]
                config_desc += f"<b>控制方式：</b>{ctrl_type}<br><b>蛇的颜色：</b><font color='{color}'>{color_text} ■■■■■</font>"
            
            elif mode_name == "单机游戏":
                agent_type = config[1].get('agent', config[2].get('agent'))
                color = rgb_to_hex(config[1].get('color', config[2].get('color')))
                color_text = colors_map[config[1].get('color', config[2].get('color'))]
                config_desc += f"<b>智能体：</b>{agent_type}<br><b>蛇的颜色：</b><font color='{color}'>{color_text} ■■■■■</font>"
            
            elif mode_name == "双人对战":
                ctrl_type1 = ctrl_map[config[1]['ctrl']]
                ctrl_type2 = ctrl_map[config[2]['ctrl']]
                color1 = rgb_to_hex(config[1]['color'])
                color2 = rgb_to_hex(config[2]['color'])
                color_text1 = colors_map[config[1]['color']]
                color_text2 = colors_map[config[2]['color']]
                
                config_desc += "<b>玩家1：</b><br>"
                config_desc += f"<b>控制方式：</b>{ctrl_type1}<br>"
                config_desc += f"<b>蛇的颜色：</b><font color='{color1}'>{color_text1} ■■■■■</font><br><br>"
                
                config_desc += "<b>玩家2：</b><br>"
                config_desc += f"<b>控制方式：</b>{ctrl_type2}<br>"
                config_desc += f"<b>蛇的颜色：</b><font color='{color2}'>{color_text2} ■■■■■</font>"
            
            elif mode_name == "人机对战":
                ctrl_type = ctrl_map[config[1]['ctrl']]
                agent_type = config[2]['agent']
                ctrl_color = rgb_to_hex(config[1]['color'])
                agent_color = rgb_to_hex(config[2]['color'])
                ctrl_color_text = colors_map[config[1]['color']]
                agent_color_text = colors_map[config[2]['color']]
                
                config_desc += "<b>玩家：</b><br>"
                config_desc += f"<b>控制方式：</b>{ctrl_type}<br>"
                config_desc += f"<b>蛇的颜色：</b><font color='{ctrl_color}'>{ctrl_color_text} ■■■■■</font><br><br>"
                
                config_desc += "<b>AI：</b><br>"
                config_desc += f"<b>智能体：</b>{agent_type}<br>"
                config_desc += f"<b>蛇的颜色：</b><font color='{agent_color}'>{agent_color_text} ■■■■■</font>"
            
            elif mode_name == "双机对战":
                agent_type1 = config[1]['agent']
                agent_type2 = config[2]['agent']
                agent_color1 = rgb_to_hex(config[1]['color'])
                agent_color2 = rgb_to_hex(config[2]['color'])
                agent_color_text1 = colors_map[config[1]['color']]
                agent_color_text2 = colors_map[config[2]['color']]
                
                config_desc += "<b>AI1：</b><br>"
                config_desc += f"<b>智能体：</b>{agent_type1}<br>"
                config_desc += f"<b>蛇的颜色：</b><font color='{agent_color1}'>{agent_color_text1} ■■■■■</font><br><br>"
                
                config_desc += "<b>AI2：</b><br>"
                config_desc += f"<b>智能体：</b>{agent_type2}<br>"
                config_desc += f"<b>蛇的颜色：</b><font color='{agent_color2}'>{agent_color_text2} ■■■■■</font>"
            
            # 更新 tooltip 包含配置信息
            full_tooltip = f"<b>{self.tooltips[mode_name][1]}{mode_name}（{self.tooltips[mode_name][0]}）</b><br><br><b>当前配置：</b><br><br>{config_desc}"
            btn.setToolTip(full_tooltip)

    def keyPressEvent(self, event):
        """处理ESC按键事件"""
        if event.key() == Qt.Key_Escape:
            # 获取顶层窗口(MainWindow)并调用其closeEvent方法
            main_window = self.window()
            if isinstance(main_window, MainWindow):
                main_window.closeEvent(event)  # 触发关闭流程
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """处理按钮的鼠标事件"""
        if event.type() == event.Enter:
            # 鼠标进入按钮时暂停动画
            self.anim.pause()
        elif event.type() == event.Leave:
            # 鼠标离开按钮时恢复动画
            self.anim.resume()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        # 绘制全屏深色渐变背景
        self.draw_cyber_background(painter)
        # 绘制赛博朋克标题
        self.draw_cyber_title(painter)

        # 绘制动态连接线（霓虹光轨效果）
        self.draw_neon_connections(painter)

    def draw_cyber_background(self, painter):
        """绘制与游戏一致的背景"""
        # 渐变背景
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(40, 40, 50))
        gradient.setColorAt(1, QColor(25, 25, 35))
        painter.fillRect(self.rect(), gradient)

        # 绘制网格线
        painter.setPen(QPen(QColor(80, 80, 100, 50), 1))
        grid_size = self.rect_size
        for x in range(0, self.width(), grid_size):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), grid_size):
            painter.drawLine(0, y, self.width(), y)

    def draw_cyber_title(self, painter):
        """颜色波浪传递效果的赛博朋克风格标题"""
        title_text = self.title
        
        # 设置字体
        title_font_size = int(self.base_size * 0.04)  # 根据基础尺寸计算
        title_font = QFont("Impact", title_font_size)
        painter.setFont(title_font)
        
        # 计算居中位置
        metrics = QFontMetrics(title_font)
        total_width = metrics.width(title_text)
        x = (self.width() - total_width) // 2
        y = int(self.height() * 0.1)
        
        # 定义颜色序列
        color_sequence = [
            QColor(0, 255, 255),    # 青色
            QColor(255, 0, 255),    # 品红
            QColor(0, 255, 255),    # 青色
        ]
        
        # 计算当前时间相位
        current_time = time()
        cycle_time = 2.5  # 完整循环时间(秒)
        wave_speed = 0.5  # 波浪传播速度(0-1之间)
        phase = (current_time % cycle_time) / cycle_time
        
        # 绘制每个字符
        char_spacing = 10  # 字符间距
        for i, char in enumerate(title_text):
            # 计算字符位置
            char_width = metrics.width(char)
            char_x = x + sum(metrics.width(title_text[j]) for j in range(i)) + i * char_spacing
            
            # 计算当前字符的颜色相位(波浪效果)
            # 从左到右传播的波浪效果
            wave_pos = (phase + (1 - i/len(title_text)) * wave_speed) % 1.0
            
            # 平滑过渡参数(使用正弦函数)
            smooth_t = (np_sin(wave_pos * 2 * np_pi - np_pi/2) + 1) / 2
            
            # 选择当前颜色
            color_index = int(smooth_t * (len(color_sequence)-1))
            t = (smooth_t * (len(color_sequence)-1)) % 1.0
            start_color = color_sequence[color_index]
            end_color = color_sequence[(color_index + 1) % len(color_sequence)]
            
            # 插值计算当前颜色
            current_color = QColor(
                int(start_color.red() + t * (end_color.red() - start_color.red())),
                int(start_color.green() + t * (end_color.green() - start_color.green())),
                int(start_color.blue() + t * (end_color.blue() - start_color.blue()))
            )
            
            # 创建横向渐变(单个字符)
            gradient = QLinearGradient(char_x, y, char_x + char_width, y)
            gradient.setColorAt(0, current_color)
            gradient.setColorAt(0.5, current_color.darker(150))
            gradient.setColorAt(1, current_color)
            
            # 绘制主体字符
            painter.setPen(QPen(gradient, 3))
            painter.drawText(char_x, y, char)

    def draw_neon_connections(self, painter):
        centers = [btn.geometry().center() for btn in self.buttons]
        path = QPainterPath()
        
        for i in range(len(centers)):
            start = centers[i]
            end = centers[(i+2)%5]
            
            # 动态渐变色
            gradient = QLinearGradient(start, end)
            phase = time() % 1
            gradient.setColorAt(phase, self.neon_colors["border"])
            gradient.setColorAt((phase+0.5)%1, self.neon_colors["hover_border"])
            
            # 光轨效果
            pen = QPen(gradient, 4)
            pen.setDashPattern([10, 5])
            painter.setPen(pen)
            
            # 绘制流动光点
            t = time() % 1
            flow_pos = start + (end - start) * t
            painter.setBrush(QColor(255, 255, 255, 200))
            painter.drawEllipse(flow_pos, 3, 3)
            
            path.moveTo(start)
            path.lineTo(end)
        
        painter.drawPath(path)

    def update_button_positions(self):
        button_radius = self.button_size // 2
        ellipse_ratio = 0.7  # 椭圆变形系数
        
        for i, btn in enumerate(self.buttons):
            current_angle = self._angle + i * 72
            rad = math_radians(current_angle)
            
            # 椭圆轨迹参数
            x = self.radius * math_cos(rad) * 0.9
            y = self.radius * math_sin(rad) * ellipse_ratio
            
            # 添加抖动效果
            jitter = 5 * math_sin(time()*3 + i)
            x += jitter * math_cos(rad)
            y += jitter * math_sin(rad)
            
            btn_x = self.center.x() + x - button_radius
            btn_y = self.center.y() + y - button_radius
            btn.move(int(btn_x), int(btn_y))

    @pyqtProperty(float)
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, value):
        self._angle = value
        self.update_button_positions()
        self.update()

class MainWindow(QMainWindow):
    def __init__(self, args, env=None, info_map=None):
        super().__init__()
        self.args = args
        self.dpi_gt96 = args.dpi > 96
        self.env = env
        self.info_map = info_map
        self.easter_egg = 'star' # star,heart
        self.setWindowTitle(self.args.window_title)
        # 获取资源路径
        if hasattr(sys, '_MEIPASS'):
            self.base_path = getattr(sys, '_MEIPASS', dirname(abspath(__file__)))
        else:
            self.base_path = dirname(abspath(__file__))
        self.window_icon = self.create_emoji_icon('🐍') if not exists(join(self.base_path,'icon.ico')) else QIcon(join(self.base_path,'icon.ico'))
        self.setWindowIcon(self.window_icon)  # 设置 Emoji 图标

        self.setStyleSheet(f"""
            QMessageBox {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3a, stop:1 #1a1a2a);
                border: 3px solid #00ffff;
                min-width: {150 if self.dpi_gt96 else 75}px;
                min-height: {50 if self.dpi_gt96 else 25}px;
            }}
            QMessageBox QLabel {{
                font: bold {40 if self.dpi_gt96 else 20}px "Segoe UI";
                color: #e0e0e0;
            }}
            QMessageBox QPushButton {{
                font: bold {40 if self.dpi_gt96 else 20}px "Segoe UI";
                min-width: {200 if self.dpi_gt96 else 100}px;
                min-height: {50 if self.dpi_gt96 else 25}px;
                padding: 15px;
                margin: 15px;
                border: 2px solid #505070;
                border-radius: 8px;
                background-color: transparent;
                color: white;
            }}
            QMessageBox QPushButton:hover {{
                background-color: rgba(0, 255, 255, 30);
                border: 2px solid #00ffff;
            }}
        """)

        # 计算实际像素尺寸
        self.pixel_width = self.args.grid_width * self.args.rect_size
        self.pixel_height = self.args.grid_height * self.args.rect_size
        # 新的宽度 = 原游戏宽度 + 两侧信息面板各一半px
        self.setFixedSize(self.pixel_width + self.args.info_width, self.pixel_height)
        
        # 添加关闭状态标记
        self._force_close = False  # 新增属性

        # 创建堆叠窗口管理不同视图
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        if env is None:
            # 添加游戏界面容器
            self._setup_game_ui()
            self._force_close = True
        else:
            # 添加配置管理器
            self.config_manager = GameConfigManager()
            # 初始化音频系统
            self.setup_audio()
            # 添加菜单界面
            self._setup_menu_ui()
            # 添加游戏界面容器
            self._setup_game_ui()
            # 初始显示菜单
            self.show_menu()
            # 初始化音频系统与FPS的快捷键
            self._setup_audio_and_fps_shortcuts()

    def _setup_audio_and_fps_shortcuts(self):
        self.shortcuts = [
            QShortcut(QKeySequence("+"), self),       # FPS加速
            QShortcut(QKeySequence("-"), self),       # FPS减速
            QShortcut(QKeySequence("Ctrl++"), self),  # 增大音量
            QShortcut(QKeySequence("Ctrl+-"), self),  # 降低音量
            QShortcut(QKeySequence("Ctrl+N"), self),  # 下一首
            QShortcut(QKeySequence("Ctrl+M"), self),  # 换主题颜色
            QShortcut(QKeySequence("Ctrl+S"), self),  # 打开设置
        ]
        # 连接信号
        self.shortcuts[0].activated.connect(lambda: self.adjust_fps(1))
        self.shortcuts[1].activated.connect(lambda: self.adjust_fps(-1))
        self.shortcuts[2].activated.connect(lambda: self.adjust_volume(1))
        self.shortcuts[3].activated.connect(lambda: self.adjust_volume(-1))
        self.shortcuts[4].activated.connect(self.adjust_bgm)
        self.shortcuts[5].activated.connect(self.adjust_color)
        self.shortcuts[6].activated.connect(self.show_settings_dialog)
        for i,size in enumerate(self.config_manager.sizes.keys()):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)   # 换游戏大小
            shortcut.activated.connect(lambda s=size: self.adjust_size(s))
            self.shortcuts.append(shortcut)

        # FPS显示相关
        self.display_label = QLabel(self)
        self.display_label.setAlignment(Qt.AlignCenter)
        self.display_label.hide()
        
        # 动画配置
        self.anim_group = QParallelAnimationGroup()
        
        # 大小动画
        self.size_anim = QPropertyAnimation(self.display_label, b"font")
        self.size_anim.setDuration(1500)  # 动画持续时间ms
        self.size_anim.setEasingCurve(QEasingCurve.OutQuad)
        
        # 透明度动画
        self.opacity_anim = QPropertyAnimation(self.display_label, b"windowOpacity")
        self.opacity_anim.setDuration(500)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(0.0)
        self.opacity_anim.setKeyValueAt(0.3, 1.0)  # 中间阶段完全不透明
        
        self.anim_group.addAnimation(self.size_anim)
        self.anim_group.addAnimation(self.opacity_anim)

    def adjust_size(self,size):
        if self.stacked_widget.currentIndex() != 0 or size == self.config_manager.current_size:
            return
        """重新计算窗口大小"""
        self.config_manager.current_size = size
        # 计算像素尺寸
        self.args.grid_width,self.args.grid_height = self.config_manager.sizes[size]
        self.args.rect_size = get_rect_size(self.args)

        self.pixel_width = self.args.grid_width * self.args.rect_size
        self.pixel_height = self.args.grid_height * self.args.rect_size
        
        # 设置窗口大小
        self.setFixedSize(self.pixel_width + self.args.info_width, self.pixel_height)
        if self.dpi_gt96:
            self.settings_btn.move(self.width()-220, 10)
        else:
            self.settings_btn.move(self.width()-110, 10)
        self.stacked_widget.widget(0).init_size(self.pixel_width + self.args.info_width, self.pixel_height, self.args.rect_size)

        self.game_widget.update_init(self.args)
        self.left_info.setFixedSize(self.args.info_width // 2, self.pixel_height)
        self.right_info.setFixedSize(self.args.info_width // 2, self.pixel_height)

        x = (self.args.screen_width - self.width()) // 2
        y = (self.args.screen_height - self.height()) // 8
        self.move(x, y)

        text = f"<font color='red'><b>通关游戏需要{self.args.grid_width*self.args.grid_height:.0f}分！</b></font>"
        self.show_change(f"游戏大小: {size} {text}")

        self.stacked_widget.widget(0)._update_button_tooltip(self.config_manager,self.media_player.volume(),self.audio_available)

    def adjust_color(self):
        # 找出与当前颜色主题都不一样的主题
        if self.stacked_widget.currentIndex() == 0:
            cur_color_pairs = set(self.config_manager.all_presets[self.config_manager.cur_color_idx])
        else:
            game_config = deepcopy(self.config_manager.configs[self.mode])
            cur_color_pairs = set([game_config[number]['color'] for number in [1,2] if 'color' in game_config[number]])
        while True:
            random_idx = random_randint(0,len(self.config_manager.all_presets)-1)
            if set(self.config_manager.all_presets[random_idx]) & cur_color_pairs == set():
                break
        color_pair = self.config_manager.all_presets[random_idx]

        if self.stacked_widget.currentIndex() == 0:
            # 修改所有游戏模式的主题颜色
            self.config_manager.cur_color_idx = random_idx
            game_config = deepcopy(self.config_manager.configs)
            for mode,item in game_config.items():
                for number,v in item.items():
                    if number == 'fps' or 'color' not in v:
                        continue
                    self.config_manager.configs[mode][number]['color'] = color_pair[number-1]
            self.stacked_widget.widget(0)._update_button_tooltip(self.config_manager,self.media_player.volume(),self.audio_available)
        else:
            # 只修改当前游戏模式的主题颜色
            for number,v in game_config.items():
                if number == 'fps' or 'color' not in v:
                    continue
                self.config_manager.configs[self.mode][number]['color'] = color_pair[number-1]
                self.game_widget.value_map[number]['color'] = color_pair[number-1]
                self.game_widget.game_config[number]['color'] = color_pair[number-1]

        text = f"<font color='{rgb_to_hex(color_pair[0])}'>{self.config_manager.colors_map[color_pair[0]]} ■■■■■</font><b> VS </b><font color='{rgb_to_hex(color_pair[1])}'>{self.config_manager.colors_map[color_pair[1]]} ■■■■■</font>"
        self.show_change(f"主题{random_idx+1}: {text}")

    def adjust_bgm(self):
        if self.audio_available:  # 只在音频可用时切换
            self.playlist.next()

    def adjust_fps(self, delta):
        """通过快捷键调整FPS"""
        if not hasattr(self, 'mode') or self.stacked_widget.currentIndex() == 0:
            return
        # 获取当前配置中的FPS值
        current_fps = self.config_manager.configs[self.mode]['fps']

        # 计算新值并限制范围（1-100）
        new_fps = max(1, min(100, current_fps + delta))
        
        # 更新配置
        self.config_manager.configs[self.mode]['fps'] = new_fps
        
        # 实时调整游戏速度
        self.game_widget.timer.setInterval(new_fps)
        self.game_widget.game_config['fps'] = new_fps
        self.show_change(f"FPS: {new_fps}")

    def adjust_volume(self, delta):
        """通过快捷键调整音量"""
        current_volume = self.media_player.volume()
        new_volume = max(0, min(100, current_volume + delta))
        self.media_player.setVolume(new_volume)
        self.show_change(f"音量: {new_volume}")

        if self.stacked_widget.currentIndex() == 0:
            self.stacked_widget.widget(0)._update_button_tooltip(self.config_manager,self.media_player.volume(),self.audio_available)

    def show_change(self, value):
        """显示FPS变化动画"""
        # 停止正在进行的动画
        if self.anim_group.state() == QAbstractAnimation.Running:
            self.anim_group.stop()
        
        # 设置初始样式
        self.display_label.setText(value)
        self.display_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(0, 255, 255, 255);
                font: bold {40 if self.dpi_gt96 else 20}px "Arial";
                background: transparent;
            }}
        """)
        
        # 计算合适的大小范围（基于窗口尺寸）
        max_size = min(self.width(), self.height()) // 8
        self.size_anim.setStartValue(QFont("Arial", int(max_size/3), QFont.Bold))
        self.size_anim.setEndValue(QFont("Arial", max_size, QFont.Bold))
        
        # 定位到中心
        self.display_label.adjustSize()
        if "FPS" in value:
            # 左上角位置
            self.display_label.move(self.left_info.width(), 0)
        elif "音量" in value:
            if self.stacked_widget.currentIndex() == 0:
                # 中间位置
                self.display_label.move(self.width() // 2 - self.display_label.width() // 2, self.height() // 2)
            else:
                # 右上角位置
                self.display_label.move(self.width() - self.right_info.width() - self.display_label.width(), 0)
        elif '主题' in value or '游戏大小' in value:
            # 下方位置
            self.display_label.move(self.width() // 2 - self.display_label.width() // 2, self.height() - self.display_label.height())
        # 启动动画
        self.display_label.show()
        self.anim_group.start()
        
        # 动画结束后隐藏
        self.anim_group.finished.connect(lambda: self.display_label.hide())

    def setup_audio(self):
        """初始化音频系统"""
        # 创建媒体播放器
        self.bgm_index = None
        self.pre_volume = None
        self.media_player = QMediaPlayer(self)

        self.audio_available = len(QAudioDeviceInfo.availableDevices(QAudio.AudioOutput)) > 0
        self.playlist = QMediaPlaylist(self.media_player)
        self.playlist.currentIndexChanged.connect(self.handle_track_change)
        
        # 设置音量
        self.media_player.setVolume(50)  # 50% 音量
        
        bgm_path = join(self.base_path, 'bgm')
        if not exists(bgm_path):
            self.audio_available = False
            self.bgm_files_to_name = {}
        else:
            # 加载背景音乐
            self.bgm_files_to_name = {i:f"{i.split('.')[1]} - 周杰伦" for i in [i for i in listdir(bgm_path) if '.mp3' in i or '.wav' in i]}
            if len(self.bgm_files_to_name) == 0:
                self.audio_available = False

        self.bgm_name_to_files = {v:k for k,v in self.bgm_files_to_name.items()}
        self.bgm_index_to_files = {}
        self.bgm_files_to_index = {}
        for index,file in enumerate(self.bgm_files_to_name.keys()):
            self.playlist.addMedia(QMediaContent(QUrl.fromLocalFile(f'{bgm_path}/{file}')))
            self.bgm_index_to_files[index] = file
            self.bgm_files_to_index[file] = index
        self.media_player.setPlaylist(self.playlist)
        
        # 播放背景音乐
        if self.audio_available:
            self.playlist.setPlaybackMode(QMediaPlaylist.Loop)  # 循环播放
            self.media_player.play()

    def handle_track_change(self, index):
        """处理曲目切换事件"""
        if self.audio_available:
            title = self.windowTitle()
            if '「' not in title:
                title = f'{title} 「背景音乐：🎵 {self.bgm_files_to_name[self.bgm_index_to_files[index]]}」'
            else:
                title = title.split(' 「')[0]
                title = f'{title} 「背景音乐：🎵 {self.bgm_files_to_name[self.bgm_index_to_files[index]]}」'
            self.setWindowTitle(title)

    def setup_menu_buttons(self, parent):
        # 创建设置按钮
        self.settings_btn = QPushButton("⚙(Ctrl+S)", parent)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: {40 if self.dpi_gt96 else 20}px;
                color: white;
                background: transparent;
                border: none;
            }}
            QPushButton:hover {{
                color: #00ffff;
            }}
        """)
        if self.dpi_gt96:
            self.settings_btn.setFixedSize(200, 100)
            self.settings_btn.move(parent.width()-220, 10)
        else:
            self.settings_btn.setFixedSize(100, 50)
            self.settings_btn.move(parent.width()-110, 10)
        self.settings_btn.clicked.connect(self.show_settings_dialog)

    def show_settings_dialog(self):
        if self.stacked_widget.currentIndex() != 0:
            return
        # 创建配置对话框
        settings_dialog = QDialog(self)
        settings_dialog.setWindowTitle("游戏设置")
        settings_dialog.setWindowFlags(settings_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        settings_dialog.setMinimumSize(int(self.width()*0.8), int(self.height()*0.8))
        settings_dialog.setWindowIcon(self.create_emoji_icon('⚙'))  # 设置 Emoji 图标
        
        # 设置赛博朋克风格
        settings_dialog.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3a, stop:1 #1a1a2a);
                border: 3px solid #00ffff;
            }}
            QLabel {{
                font: bold {40 if self.dpi_gt96 else 20}px "Segoe UI";
                color: #e0e0e0;
            }}
            QTabWidget::pane {{
                border: 1px solid #404050;
                background-color: #202030;
            }}
            QTabBar::tab {{
                font: bold {40 if self.dpi_gt96 else 20}px "Segoe UI";
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #303040, stop:1 #202030);
                color: white;
                padding: {20 if self.dpi_gt96 else 10}px;
                margin: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                min-width: {200 if self.dpi_gt96 else 100}px;  /* 设置最小宽度 */
                min-height: {100 if self.dpi_gt96 else 50}px;  /* 设置最小高度 */
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #406080, stop:1 #305070);
                color: #00ffff;
                border-bottom: 2px solid #00ffff;
            }}
            QGroupBox {{
                font: bold {40 if self.dpi_gt96 else 20}px "Segoe UI";
                color: #ff80ff;
                border: 1px solid #505070;
                border-radius: 6px;
                padding: {50 if self.dpi_gt96 else 25}px;
                margin-top: 10px;
            }}
            QComboBox, QSlider, QPushButton {{
                font: {40 if self.dpi_gt96 else 20}px "Segoe UI";
                padding: 5px;
                border: 1px solid #505070;
                border-radius: 4px;
                background-color: #303040;
                color: white;
                min-height: {50 if self.dpi_gt96 else 25}px;
            }}
            QComboBox QAbstractItemView {{
                background: #1a1a2a;
                border: 2px solid #00ffff;
                selection-background-color: #505070;
                color: white;
                outline: none;
            }}
            QComboBox:hover, QSlider:hover, QPushButton:hover {{
                border: 1px solid #00ffff;
                background-color: #404050;
            }}
            QComboBox::drop-down {{
                width: {50 if self.dpi_gt96 else 25}px;  /* 增大下拉按钮宽度 */
                height: {50 if self.dpi_gt96 else 25}px; /* 增大下拉按钮高度 */
            }}
            QPushButton {{
                min-width: {100 if self.dpi_gt96 else 50}px;
                min-height: {50 if self.dpi_gt96 else 25}px;
            }}
            QDialog QPushButton#ok {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #40a040, stop:1 #208020);
            }}
            QDialog QPushButton#cancel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a04040, stop:1 #802020);
            }}
        """)

        # 使用选项卡组织不同模式的设置
        tab_widget = QTabWidget()
        
        # 为每种模式创建配置面板
        modes = ["单人游戏", "单机游戏", "双人对战", "人机对战", "双机对战","其他设置"]
        for mode in modes:
            tab = QWidget()
            self._create_mode_settings_tab(tab, mode)
            tab_widget.addTab(tab, mode)

        # 确定/取消按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(settings_dialog.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(settings_dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        
        # 主布局
        layout = QVBoxLayout(settings_dialog)
        layout.addWidget(tab_widget)
        layout.addLayout(btn_layout)
        
        if settings_dialog.exec_() == QDialog.Accepted:
            # 保存所有配置
            self._save_all_settings(tab_widget)

    def _change_bgm(self, index, manual_play=False):
        """切换背景音乐"""
        if self.audio_available:
            self.playlist.setCurrentIndex(index)
            self.media_player.play()

    def _create_mode_settings_tab(self, tab, mode):
        # 创建主滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用水平滚动
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)      # 垂直滚动按需显示
        
        # 保持原有样式
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollArea > QWidget > QWidget {{  /* 添加内容区域的背景色 */
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3a, stop:1 #1a1a2a);
            }}
            QScrollBar:vertical {{
                background: #303040;
                width: {40 if self.dpi_gt96 else 20}px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #505070;
                min-height: {20 if self.dpi_gt96 else 10}px;
                border-radius: 6px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        # 创建内容widget
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(15, 15, 15, 15)  # 添加适当边距
        
        if mode == "其他设置":
            # 音乐选择布局
            music_layout = QHBoxLayout()

            # 背景音乐音量
            bgm_layout = QHBoxLayout()
            bgm_layout.addWidget(QLabel("背景音量:"))
            bgm_slider = QSlider(Qt.Horizontal)
            bgm_slider.setRange(0, 100)
            bgm_slider.setValue(self.media_player.volume())
            bgm_layout.addWidget(bgm_slider)
            bgm_value_label = QLabel(str(self.media_player.volume()))
            bgm_value_label.setObjectName("bgm_value_label")
            bgm_slider.valueChanged.connect(lambda v: bgm_value_label.setText(str(v)))

            bgm_layout.addWidget(bgm_value_label)
            main_layout.addLayout(bgm_layout)
            music_layout.addWidget(QLabel("背景音乐:"), stretch=0)

            # 创建音乐下拉框
            music_combo = QComboBox()
            music_combo.setObjectName('music_combo')
            items = [self.bgm_files_to_name[f] for _,f in self.bgm_index_to_files.items()]
            if self.playlist.currentIndex() != len(items) - 1:
                items.pop()
            music_combo.addItems(items)
            cur_text = self.bgm_files_to_name[self.bgm_index_to_files[0]] if len(self.bgm_index_to_files) > 0 else '无'
            if self.audio_available:
                cur_text = self.bgm_files_to_name[self.bgm_index_to_files[self.playlist.currentIndex()]] if len(self.bgm_index_to_files) > 0 else '无'
            music_combo.setCurrentText(cur_text)
            music_layout.addWidget(music_combo, stretch=1)

            # 在 color_layout 定义后添加颜色选择器
            color_layout = QHBoxLayout()

            # 创建颜色选择标签
            color_label = QLabel("主题颜色:")
            color_layout.addWidget(color_label)
            # 创建颜色组合选择器
            color_combo = QComboBox()
            color_combo.setObjectName('color_combo')
            # 添加预设颜色组合
            for i, preset in enumerate(self.config_manager.all_presets):
                # 创建预览图标
                rect_size = self.args.rect_size
                gap = 10
                pixmap = QPixmap(rect_size*2+gap, rect_size)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                
                # 绘制双色预览
                color1 = QColor(*preset[0])
                color2 = QColor(*preset[1])
                painter.fillRect(0, 0, rect_size, rect_size, color1)
                painter.fillRect(rect_size+gap, 0, rect_size, rect_size, color2)
                painter.end()
                
                # 添加到下拉框
                color_combo.addItem(QIcon(pixmap), f"主题{i+1}: {self.config_manager.colors_map[preset[0]]} VS {self.config_manager.colors_map[preset[1]]}")
                color_combo.setItemData(i, preset)  # 存储原始颜色数据

            def update_preset_text(index):
                preset = self.config_manager.all_presets[index]
                text = f"<font color='{rgb_to_hex(preset[0])}'>{self.config_manager.colors_map[preset[0]]} ■■■■■</font><b> VS </b><font color='{rgb_to_hex(preset[1])}'>{self.config_manager.colors_map[preset[1]]} ■■■■■</font>"
                self.preset_text_label.setText(text)

            self.preset_text_label = QLabel()
            color_combo.currentIndexChanged.connect(lambda index: update_preset_text(index))
            color_combo.setCurrentIndex(self.config_manager.cur_color_idx)
            update_preset_text(self.config_manager.cur_color_idx) # 初次更新
            
            color_layout.addWidget(color_combo)
            color_layout.addSpacing(40 if self.dpi_gt96 else 20)
            color_layout.addWidget(self.preset_text_label)
            # 添加空白间隔
            color_layout.addStretch(1)

            # 定义游戏窗口大小配置
            size_layout = QHBoxLayout()
            size_label = QLabel("游戏大小:")
            size_layout.addWidget(size_label)
            size_combo = QComboBox()
            size_combo.setObjectName('size_combo')
            size_combo.addItems(list(self.config_manager.sizes.keys()))
            size_combo.setCurrentText(self.config_manager.current_size)

            def update_size_text(text):
                grid_width,grid_height = self.config_manager.sizes[text]
                text = f"<font color='red'><b>通关游戏需要{grid_width*grid_height:.0f}分！</b></font>"
                self.size_text_label.setText(text)
            self.size_text_label = QLabel()
            update_size_text(self.config_manager.current_size) # 初次更新
            size_combo.currentTextChanged.connect(lambda text:update_size_text(text))
            size_layout.addWidget(size_combo)
            size_layout.addSpacing(40 if self.dpi_gt96 else 20)
            size_layout.addWidget(self.size_text_label)
            # 添加空白间隔
            size_layout.addStretch(1)

            # 新增快捷键说明
            shortcut_group = QGroupBox("快捷键")
            shortcut_layout = QVBoxLayout(shortcut_group)
            shortcut_info = "1. <code>[Esc]</code> 暂停游戏<br>2. <code>[+][-]</code> 调节游戏速度FPS<br>3. <code>[Ctrl+][Ctrl-]</code> 调节音量<br>4. <code>[Ctrl+N]</code> 切换背景音乐<br>5. <code>[Ctrl+M]</code> 切换主题颜色<br>6. <code>[Ctrl+1/2/3/4/5]</code> 切换游戏大小"
            if not self.audio_available:
                shortcut_info += f"<br>7. <font color='red'>系统不支持播放音乐</font>"
            shortcut_info_label = QLabel(shortcut_info)
            shortcut_info_label.setTextInteractionFlags(Qt.TextBrowserInteraction)  # 让文本可交互
            shortcut_layout.addWidget(shortcut_info_label)

            # 新增关于我
            aboutme_group = QGroupBox("关于我")
            aboutme_layout = QVBoxLayout(aboutme_group)
            aboutme_info = "1. GitHub：<a style='color:white' href='https://github.com/JuneWaySue'>JuneWaySue</a><br>2. CSDN：<a style='color:white' href='https://blog.csdn.net/sinat_39629323'>七里香还是稻香</a><br>3. 微信公众号：<a style='color:white' href='https://user-images.githubusercontent.com/45711125/234814025-af439d36-d595-434d-bb51-e138b0c7738d.jpg'>Python王者之路</a>"
            aboutme_info_label = QLabel(aboutme_info)
            aboutme_info_label.setOpenExternalLinks(True)
            aboutme_info_label.setTextInteractionFlags(Qt.TextBrowserInteraction)  # 让文本可交互
            aboutme_layout.addWidget(aboutme_info_label)
            
            main_layout.addLayout(music_layout)
            main_layout.addLayout(color_layout)
            main_layout.addLayout(size_layout)
            main_layout.addWidget(shortcut_group)
            main_layout.addWidget(aboutme_group)
        else:
            # 获取当前配置
            config = deepcopy(self.config_manager.configs[mode])
            # FPS设置
            fps_layout = QHBoxLayout()
            fps_layout.addWidget(QLabel("游戏速度(FPS):"))
            fps_slider = QSlider(Qt.Horizontal)
            fps_slider.setRange(1, 100)
            fps_slider.setValue(config["fps"])
            
            fps_label = QLabel(str(config["fps"]))
            fps_label.setObjectName("fps_label")
            fps_slider.valueChanged.connect(lambda v: fps_label.setText(str(v)))
            
            fps_layout.addWidget(fps_slider)
            fps_layout.addWidget(fps_label)
            main_layout.addLayout(fps_layout)

            # 根据模式创建玩家配置组
            if mode == "单人游戏":
                # 只有玩家1，且必须是人类
                player1_group = self._create_player_group("玩家1", config[1], force_human=True)
                main_layout.addWidget(player1_group)
                
            elif mode == "单机游戏":
                # 只有玩家1，且必须是AI
                player1_group = self._create_player_group("玩家1", config[1], force_ai=True)
                main_layout.addWidget(player1_group)
                
            elif mode == "双人对战":
                # 两个玩家都必须是人类
                player1_group = self._create_player_group("玩家1", config[1], force_human=True)
                player2_group = self._create_player_group("玩家2", config[2], force_human=True)

                player1_ctrl = player1_group.findChild(QComboBox, "ctrl_combo")
                player2_ctrl = player2_group.findChild(QComboBox, "ctrl_combo")
                
                # 连接信号
                player1_ctrl.currentTextChanged.connect(
                    lambda text: self._update_opposite_ctrl(text, player2_ctrl)
                )
                player2_ctrl.currentTextChanged.connect(
                    lambda text: self._update_opposite_ctrl(text, player1_ctrl)
                )

                main_layout.addWidget(player1_group)
                main_layout.addWidget(player2_group)
                
            elif mode == "人机对战":
                # 玩家1必须是人类，玩家2必须是AI
                player1_group = self._create_player_group("玩家1", config[1], force_human=True)
                player2_group = self._create_player_group("玩家2", config[2], force_ai=True)
                main_layout.addWidget(player1_group)
                main_layout.addWidget(player2_group)
                
            elif mode == "双机对战":
                # 两个玩家都必须是AI
                player1_group = self._create_player_group("玩家1", config[1], force_ai=True)
                player2_group = self._create_player_group("玩家2", config[2], force_ai=True)
                main_layout.addWidget(player1_group)
                main_layout.addWidget(player2_group)
        
        # 添加伸缩因子使内容靠上
        main_layout.addStretch(1)

        # 设置内容widget
        scroll_area.setWidget(content)
        
        # 将滚动区域添加到tab (替换原来的直接添加布局)
        tab_layout = QVBoxLayout(tab)
        tab_layout.addWidget(scroll_area)
        tab_layout.setContentsMargins(0, 0, 0, 0)

    def _update_opposite_ctrl(self, selected_ctrl, opposite_ctrl):
        """当一方选择控制方式时，更新另一方的控制方式"""
        if selected_ctrl == "方向键":
            # 如果一方选择了方向键，另一方自动设为WSAD
            opposite_ctrl.setCurrentText("WSAD")
        else:
            # 如果一方选择了WSAD，另一方自动设为方向键
            opposite_ctrl.setCurrentText("方向键")

    def _create_player_group(self, title, player_config, force_human=False, force_ai=False):
        """创建玩家配置组，可强制指定玩家类型"""
        group = QGroupBox(title)
        group.setObjectName(title)
        layout = QVBoxLayout(group)
        
        # 玩家类型（Human/AI）
        type_combo = QComboBox()
        type_combo.addItems(["人类玩家", "AI玩家"])
        
        # 根据强制类型设置初始选择
        if force_human:
            type_combo.setCurrentText("人类玩家")
            type_combo.setEnabled(False)  # 禁用选择
        elif force_ai:
            type_combo.setCurrentText("AI玩家")
            type_combo.setEnabled(False)  # 禁用选择
        else:
            # 根据配置设置初始选择
            type_combo.setCurrentText("人类玩家" if player_config.get("player") == "Human" else "AI玩家")
        
        # 控制方式（仅对人类玩家可见）
        ctrl_combo = QComboBox()
        ctrl_combo.addItems(["方向键", "WSAD"])
        if "ctrl" in player_config:
            ctrl_combo.setCurrentText("方向键" if player_config["ctrl"] == "default" else "WSAD")
        
        # AI类型（仅对AI玩家可见）
        ai_combo = QComboBox()
        ai_combo.addItems(["AI-DQN1", "AI-DQN2", "Rule-BFS"])
        if "agent" in player_config:
            if player_config["player"] == 'Rule-BFS':
                ai_combo.setCurrentText('Rule-BFS')
            else:
                ai_combo.setCurrentText(player_config["agent"])

        # 添加颜色选择按钮
        color_btn = QPushButton("选择颜色")
        if "color" in player_config:
            color_btn.setStyleSheet(f"background-color: rgb{player_config['color']}")
        # 连接颜色选择信号
        color_btn.clicked.connect(lambda: self._select_color(color_btn))

        # 动态显示/隐藏控件
        def update_ui():
            is_human = type_combo.currentText() == "人类玩家"
            ctrl_combo.setVisible(is_human)
            ai_combo.setVisible(not is_human)
        
        type_combo.currentTextChanged.connect(update_ui)
        update_ui()  # 初始更新
        
        # 添加到布局
        layout.addWidget(QLabel("类型:"))
        layout.addWidget(type_combo)
        if force_human:
            layout.addWidget(QLabel("控制方式:"))
        layout.addWidget(ctrl_combo)
        if force_ai:
            layout.addWidget(QLabel("AI类型:"))
        layout.addWidget(ai_combo)
        layout.addWidget(QLabel("颜色:"))
        layout.addWidget(color_btn)
        
        # 为控件设置对象名称以便后续查找
        type_combo.setObjectName("type_combo")
        ctrl_combo.setObjectName("ctrl_combo")
        ai_combo.setObjectName("ai_combo")
        color_btn.setObjectName("color_btn")
        
        return group
        
    def _select_color(self, button):
        # 打开颜色选择对话框
        qw = QWidget()
        qw.setWindowIcon(self.create_emoji_icon('🎨'))  # 设置 Emoji 图标
        # 应用与主游戏一致的赛博朋克风格样式
        qw.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3a, stop:1 #1a1a2a);
                border: 2px solid #00ffff;
                border-radius: 8px;
            }}
            QLabel {{
                color: #e0e0e0;
                font: bold {40 if self.dpi_gt96 else 20}px "Segoe UI";
            }}
            QAbstractItemView, QListWidget, QListView {{
                outline: 0px;
                background-color: #2a2a3a;
                color: white;
                selection-background-color: #00ffff;
                border: 1px solid #505070;
                border-radius: 4px;
            }}
            QScrollBar:vertical {{
                background: #303040;
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #505070;
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QPushButton {{
                font: bold {40 if self.dpi_gt96 else 20}px "Segoe UI";
                min-width: 120px;
                min-height: 30px;
                padding: 5px;
                border: 2px solid #505070;
                border-radius: 6px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #303040, stop:1 #202030);
                color: white;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #404050, stop:1 #303040);
                border: 2px solid #00ffff;
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #202030, stop:1 #101020);
            }}
        """)
        color_dialog = QColorDialog()
        color = color_dialog.getColor(parent=qw,title='选择颜色')
        if color.isValid():
            rgb = (color.red(), color.green(), color.blue())
            button.setStyleSheet(f"background-color: rgb{rgb}")

    def _save_all_settings(self, tab_widget):
        game_config = {}
        for i in range(tab_widget.count()):
            mode = tab_widget.tabText(i)
            tab = tab_widget.widget(i)
            
            if mode == '其他设置':
                # 获取音量设置
                bgm_value_label = tab.findChild(QLabel, "bgm_value_label")
                bgm_value = int(bgm_value_label.text())
                if self.media_player.volume() != bgm_value:
                    self.media_player.setVolume(bgm_value)

                # 获取音乐设置
                music_combo = tab.findChild(QComboBox, "music_combo")
                music_idx = music_combo.currentIndex()
                if self.playlist.currentIndex() != music_idx:
                    self._change_bgm(music_idx)

                # 获取主题颜色设置
                color_combo = tab.findChild(QComboBox, "color_combo")
                color_idx = color_combo.currentIndex()
                if self.config_manager.cur_color_idx != color_idx:
                    self.config_manager.cur_color_idx = color_idx
                    color_pair = self.config_manager.all_presets[color_idx]
                    for mode,item in game_config.items():
                        for number,v in item.items():
                            if number == 'fps' or 'color' not in v:
                                continue
                            game_config[mode][number]['color'] = color_pair[number-1]

                # 获取游戏大小设置
                size_combo = tab.findChild(QComboBox, "size_combo")
                current_size = size_combo.currentText()
                self.adjust_size(current_size)
            else:
                # 获取FPS设置
                fps_label = tab.findChild(QLabel, "fps_label")
                fps = int(fps_label.text())
                
                # 构建配置
                config = {"fps": fps}
                
                # 获取玩家配置
                player1_group = tab.findChild(QGroupBox, "玩家1")
                player2_group = tab.findChild(QGroupBox, "玩家2")
                
                # 确保玩家1配置存在
                config[1] = self._get_player_config(player1_group) if player1_group else {}
                
                # 根据模式处理玩家2配置
                if mode in ["双人对战", "人机对战", "双机对战"]:
                    config[2] = self._get_player_config(player2_group) if player2_group else {}
                else:
                    config[2] = {}  # 单人游戏和单机游戏玩家2为空

            game_config[mode] = config
        
        # 更新配置
        self.config_manager.configs = game_config
        if self.stacked_widget.currentIndex() == 0:
            self.stacked_widget.widget(0)._update_button_tooltip(self.config_manager,self.media_player.volume(),self.audio_available)
            
    def _get_player_config(self, group):
        """从设置对话框获取玩家配置"""
        config = {}
        
        type_combo = group.findChild(QComboBox, "type_combo")
        if not type_combo:  # 如果没有找到控件，返回空配置
            return config
            
        ctrl_combo = group.findChild(QComboBox, "ctrl_combo")
        ai_combo = group.findChild(QComboBox, "ai_combo")
        
        if type_combo.currentText() == "人类玩家":
            ctrl = "default" if ctrl_combo.currentText() == "方向键" else "wsad"
            config.update({
                "player": "Human",
                "ctrl": ctrl
            })
        else:
            config.update({
                "player": ai_combo.currentText(),
                "agent": ai_combo.currentText()
            })

        # 获取颜色设置
        color_btn = group.findChild(QPushButton, "color_btn")
        if color_btn:
            style = color_btn.styleSheet()
            if "background-color" in style:
                color_str = style.split("rgb")[1].split(")")[0]
                config["color"] = eval(color_str+')')
        
        return config

    def _setup_menu_ui(self):
        # 添加旋转菜单
        rotate_menu = RotateMenuWidget(self.args.window_title, self.pixel_width + self.args.info_width,self.pixel_height,self.args.rect_size)
        
        # 连接按钮信号
        for btn in rotate_menu.buttons:
            btn.clicked.connect(self._on_mode_selected)

        self.setup_menu_buttons(rotate_menu)
        rotate_menu._update_button_tooltip(self.config_manager,self.media_player.volume(),self.audio_available)

        self.stacked_widget.addWidget(rotate_menu)

    def _on_mode_selected(self):
        clicked_btn = self.sender()
        mode_map = {
            "单人游戏": "单人游戏",
            "单机游戏": "单机游戏",
            "双人对战": "双人对战",
            "人机对战": "人机对战",
            "双机对战": "双机对战"
        }
        self.mode = mode_map[clicked_btn.property("mode")]

        # 直接使用预存的配置
        self.game_config = deepcopy(self.config_manager.configs[self.mode])
        self._start_game_with_config(self.mode, self.game_config)

    def _setup_game_ui(self):
        """创建游戏界面"""
        game_container = QWidget()
        main_layout = QHBoxLayout(game_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧信息面板
        self.left_info = SnakeInfoPanel(self.args.info_width//2,self.easter_egg,side="left")
        # 右侧信息面板
        self.right_info = SnakeInfoPanel(self.args.info_width//2,self.easter_egg,side="right")

        # 中间游戏区域
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.game_widget = GameWidget(self, self.args, self.env, easter_egg=self.easter_egg)
        center_layout.addWidget(self.game_widget)

        main_layout.addWidget(self.left_info, stretch=1)
        main_layout.addWidget(center_widget, stretch=8)
        main_layout.addWidget(self.right_info, stretch=1)

        self.stacked_widget.addWidget(game_container)
        self.game_widget.scoreUpdated.connect(self.update_info_panels)

    def _start_game_with_config(self, mode, config):
        """根据配置启动游戏"""
        # 确保配置格式正确
        game_config = {
            'fps': config.get('fps', 60),  # 获取FPS设置，默认为60
            1: config.get(1, {}),  # 玩家1配置
            2: config.get(2, {})   # 玩家2配置
        }
        
        # 设置蛇的颜色
        for player_id in [1, 2]:
            if player_id in config and 'color' in config[player_id]:
                self.game_widget.value_map[player_id]['color'] = config[player_id]['color']

        # 设置AI代理（将AI1/AI2字符串映射到实际的agent对象）
        if mode in ["单机游戏", "人机对战", "双机对战"]:
            for player_id in [1, 2]:
                if game_config[player_id].get('player') and 'AI-DQN' in game_config[player_id].get('player'):
                    ai_name = game_config[player_id]['agent']  # AI1或AI2
                    # 映射到info_map中对应的agent对象
                    game_config[player_id]['agent'] = self.info_map[{'AI-DQN1':1, 'AI-DQN2':2}[ai_name]]['agent']
        
        # 更新游戏窗口标题
        if self.audio_available:
            self.setWindowTitle(f'{self.args.window_title} - {mode} 「背景音乐：🎵 {self.bgm_files_to_name[self.bgm_index_to_files[self.playlist.currentIndex()]]}」')
        else:
            self.setWindowTitle(f'{self.args.window_title} - {mode}')
        # 重置并启动游戏
        self.game_widget.game_config = game_config
        self.game_widget.resetGame()
        self.game_widget.startGame()
        
        # 切换到游戏界面
        self.stacked_widget.setCurrentIndex(1)
        self.game_widget.setFocus()

    def show_menu(self):
        """显示菜单界面"""
        self.stacked_widget.setCurrentIndex(0)
        self.game_widget.timer.stop()
        if self.audio_available:
            self.setWindowTitle(f'{self.args.window_title} 「背景音乐：🎵 {self.bgm_files_to_name[self.bgm_index_to_files[self.playlist.currentIndex()]]}」')
        else:
            self.setWindowTitle(f'{self.args.window_title}')
        if self.bgm_index is not None:
            self.setWindowIcon(self.window_icon)  # 设置 Emoji 图标
            self.bgm_index = None
        if self.pre_volume is not None:
            self.media_player.setVolume(self.pre_volume)
            self.pre_volume = None

        self.stacked_widget.widget(0)._update_button_tooltip(self.config_manager,self.media_player.volume(),self.audio_available)

    def closeEvent(self, event):
        """重写关闭事件处理"""
        if self._force_close:  # 强制关闭模式
            super().closeEvent(event)
            if hasattr(self,'media_player'):
                self.media_player.stop()
            return
        
        if self.stacked_widget.currentIndex() == 1:  # 游戏界面
            self.game_widget.showDialogue('暂停')
            if self._force_close:
                self.close()
            else:
                event.ignore()  # 阻止窗口关闭
        else:  # 菜单界面
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("退出确认")
            msg_box.setWindowIcon(self.create_emoji_icon('⚠'))  # 设置 Emoji 图标
            msg_box.setText("确定要退出游戏吗？")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)

            reply = msg_box.exec()
            if reply == QMessageBox.Yes:
                self._force_close = True
                self.close()  # 再次触发关闭事件
                self.media_player.stop()
            else:
                event.ignore()  # 关键修复：明确忽略关闭事件
    
    def create_emoji_icon(self, emoji, size=100, save_path=None):
        # 获取设备像素比
        dpr = QApplication.primaryScreen().devicePixelRatio()
        # 计算物理尺寸（考虑高DPI屏幕）
        physical_size = int(size * dpr)
        
        # 创建高分辨率pixmap
        pixmap = QPixmap(physical_size, physical_size)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        
        # 设置Emoji字体
        emoji_font = QFont()
        font_names = [
            "Segoe UI Emoji", 
            "Apple Color Emoji",
            "Noto Color Emoji",
            "EmojiOne",
            "Symbola"
        ]
        emoji_font.setFamilies(font_names)
        emoji_font.setPixelSize(int(physical_size * 0.8))  # 使用80%的空间

        # 绘制带描边的Emoji
        painter.setFont(emoji_font)
        
        # 计算居中位置
        metrics = QFontMetricsF(emoji_font)
        text_rect = metrics.boundingRect(emoji)
        x = int((physical_size - text_rect.width()) / 2)
        y = int((physical_size - text_rect.height()) / 2 + metrics.ascent())
        
        # 绘制描边（增加可见性）
        painter.setPen(QPen(Qt.white, 3))
        painter.drawText(x, y, emoji)
        
        # 绘制主体
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawText(x, y, emoji)
        
        painter.end()

        if save_path:
            pixmap.save(save_path)

        # 直接返回图标（不再缩放）
        return QIcon(pixmap)

    def update_info_panels(self, info):
        """更新两侧信息面板"""
        if not hasattr(self,'game_config'):
            self.left_info.update_info(info[1])
            self.right_info.update_info(info[2])
            return
        
        left_flag,right_flag=0,0

        if self.game_config[1].get('ctrl') == 'wsad':
            self.left_info.update_info(info[1])
            left_flag=1
        elif self.game_config[2].get('ctrl') == 'wsad':
            self.left_info.update_info(info[2])
            left_flag=2

        if self.game_config[1].get('ctrl') == 'default':
            self.right_info.update_info(info[1])
            right_flag=1
        elif self.game_config[2].get('ctrl') == 'default':
            self.right_info.update_info(info[2])
            right_flag=2

        if left_flag == 0 and right_flag == 0:
            self.left_info.update_info(info[1])
            self.right_info.update_info(info[2])
        elif left_flag != 0 and right_flag == 0:
            self.right_info.update_info(info[{1:2,2:1}[left_flag]])
        elif left_flag == 0 and right_flag != 0:
            self.left_info.update_info(info[{1:2,2:1}[right_flag]])

    def keyPressEvent(self, event):
        if self.stacked_widget.currentIndex() == 1:
            self.game_widget.handleKeyPress(event)

class SnakeInfoPanel(QWidget):
    def __init__(self, width, easter_egg, side="left"):
        super().__init__()
        self.side = side
        self.setFixedWidth(width)
        self.info = {}
        self.easter_egg = easter_egg

        # 现代字体设置
        self.title_font = QFont("Segoe UI", 14, QFont.Bold)
        self.label_font = QFont("Segoe UI Semibold", 11)
        self.value_font = QFont("Segoe UI", 12)
        self.icon_font = QFont("Segoe UI Symbol", 24)
        
        # 统一尺寸参数
        self.card_height = 70
        self.icon_size = 40
        self.padding = 15

        # 聊天区域参数
        self.chat_lines = []  # 存储聊天记录
        self.append_flag = True

    def update_info(self, snake_info):
        self.info = snake_info
        self.is_done = snake_info.get('done', False)  # 获取蛇的状态
        self.player = self.info.get('player')

        # 收集step_info到聊天记录
        step = snake_info.get('steps', 0)
        step_info = snake_info.get('step_info', {}).get(step, {})
        
        if step_info and self.append_flag:
            # 将字典信息转为可读文本
            text = f'💰'
            value = 0
            dead_reason = ''
            for k, v in step_info.items():
                if k == 'done':
                    continue
                value += v
                if v <= -20 and k != '不能追到蛇尾惩罚':
                    dead_reason = k
            value = f'+{value:.3f}' if value > 0 else f'{value:.3f}'
            self.chat_lines.append(f'{text}{value}')
            if dead_reason != '':
                self.chat_lines.append(f'{dead_reason}')
                self.append_flag = False
            
            # 限制最大记录数
            if len(self.chat_lines) > 10:
                self.chat_lines.pop(0)

        if 'color' in snake_info:
            # 根据蛇的颜色计算主题颜色
            self.theme_color = QColor(*snake_info['color'])
        else:
            # 默认颜色
            self.theme_color = QColor(100, 200, 255) if self.side == "left" else QColor(255, 100, 100)

        # 根据主题色重新生成背景渐变
        h, s, v, _ = self.theme_color.getHsv()
        gradient = QLinearGradient(0, 0, 0, self.height())

        # 使用HSV颜色模型调整亮度
        gradient.setColorAt(0, QColor.fromHsv(h, s, max(20, v//3)))       # 顶部稍亮
        gradient.setColorAt(0.5, QColor.fromHsv(h, s, max(15, v//4)))     # 中间过渡
        gradient.setColorAt(1, QColor.fromHsv(h, s, max(10, v//5)))       # 底部最暗

        self.bg_gradient = gradient

        self.update()

    def paintEvent(self, event):
        if len(self.info) == 0: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制背景
        if self.is_done and not self.info.get('victory'):
            painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
        else:
            painter.fillRect(self.rect(), self.bg_gradient)

        # 绘制装饰性光带
        self.draw_light_strip(painter)
        # 绘制标题栏
        y_start = self.draw_title(painter)
        # 绘制信息卡片
        self.draw_info_cards(painter,y_start)
        # 绘制方向仪表盘
        self.draw_direction_dial(painter)

    def draw_light_strip(self, painter):
        strip = QLinearGradient(0, 0, 0, self.height())
        strip.setColorAt(0, QColor(0, 0, 0, 150) if self.is_done and not self.info.get('victory') else self.theme_color.lighter(120))
        strip.setColorAt(1, Qt.transparent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(strip)
        if self.side == "left":
            painter.drawRect(self.width()-5, 0, 5, self.height())
        else:
            painter.drawRect(0, 0, 5, self.height())

    def draw_title(self, painter):
        painter.setFont(self.title_font)
        painter.setPen(QColor(0, 0, 0, 150) if self.is_done and not self.info.get('victory') else self.theme_color)
        
        if self.player is None:
            title = '🈚'
            game_time = '--:--:--'
        elif self.player == 'Human':
            done = '😊' if not self.info.get('done') else ('😎' if self.info.get('victory') else '🤡')
            title = f'{done}{self.player}'
            seconds = int((self.info.get('end_time',datetime.now())-self.info['start_time']).total_seconds())
            game_time = f'{seconds//3600%24:02d}:{seconds//60%60:02d}:{seconds%60:02d}'
            if seconds//(3600*24) > 0:
                game_time = f'{seconds//(3600*24):0d}天 {game_time}'
        else:
            done = '🤖' if not self.info.get('done') else ('😎' if self.info.get('victory') else '🤡')
            title = f'{done}{self.player}'
            seconds = int((self.info.get('end_time',datetime.now())-self.info['start_time']).total_seconds())
            game_time = f'{seconds//3600%24:02d}:{seconds//60%60:02d}:{seconds%60:02d}'
            if seconds//(3600*24) > 0:
                game_time = f'{seconds//(3600*24):0d}天 {game_time}'

        title = f'{title}\n{game_time}'
        # 使用字体测量精确计算位置
        metrics = QFontMetrics(self.title_font)
        y_base = 5
        title_width = metrics.width(title)
        text_height = metrics.height() * 2
        draw_rect = QRect((self.width()-title_width)//2, y_base, title_width, text_height)
        painter.drawText(draw_rect, Qt.AlignCenter | Qt.TextWordWrap, title)

        return text_height + y_base * 2

    def draw_info_cards(self, painter,y_start=100):
        card_margin = 10
        info_items = [
            ("", "Alive" if not self.info.get('done') or self.info.get('victory') else "Dead", "❤️" if not self.info.get('done') or self.info.get('victory') else "💔"),
            ("", self.info.get('score', 1), "🍎"),
            ("", f"{self.info.get('reward', 0):.1f}", "💰"),
            ("", self.info.get('steps', 0), "🎮"),
            ("", self.info['max_steps'] - self.info['didn_eat_steps'], "⏰"),
            ("", self.chat_lines[-1] if self.chat_lines else "-", "💬"),
        ]

        for i in range(len(info_items)):
            label, value, icon = info_items[i]
            value = value if self.player is not None else '-'
            # 卡片位置计算
            card_y = y_start + i*(self.card_height + card_margin)
            # 绘制卡片背景
            self.draw_card_background(painter, card_y)
            # 绘制图标
            self.draw_icon(painter, icon, card_y)
            # 绘制文字
            self.draw_card_text(painter, label, value, card_y)

    def draw_card_background(self, painter, y):
        painter.setBrush(QColor(255, 255, 255, 15))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.padding, y, 
                              self.width()-2*self.padding, self.card_height, 8, 8)

    def draw_icon(self, painter, icon, y):
        painter.setFont(self.icon_font)
        painter.setPen(QColor(255, 255, 255, 50))
        # 图标垂直居中
        icon_y = y + (self.card_height - self.icon_size)//2
        painter.drawText(self.padding + 10, icon_y + self.icon_size - 5, icon)

    def draw_card_text(self, painter, label, value, y):
        # 标签文字
        painter.setFont(self.label_font)
        painter.setPen(QColor(200, 200, 200))
        label_y = y + 25
        painter.drawText(self.padding + 60, label_y, label)
        
        # 数值文字
        painter.setFont(self.value_font)
        painter.setPen(QColor(0, 0, 0, 150) if self.is_done and not self.info.get('victory') else self.theme_color)
        value_str = str(value)
        value_width = QFontMetrics(self.value_font).width(value_str)
        value_x = self.width() - self.padding - value_width - 10
        painter.drawText(value_x, y + 45, value_str)

    def draw_direction_dial(self, painter):
        dial_size = 160
        center_x = self.width() // 2
        center_y = self.height() - dial_size//2 - 20
        
        # 仪表盘背景
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.setPen(QPen(QColor(255, 255, 255, 50), 2))
        painter.drawEllipse(center_x - dial_size//2, center_y - dial_size//2, dial_size, dial_size)
        
        if self.player is None:
            return

        ctrl_type = self.info.get('ctrl', 'default')
        if ctrl_type == 'default':
            directions = {
                'up': (0, -1, "⬆" if self.player == 'Human' else '▲'),   # 上箭头
                'down': (0, 1, "⬇" if self.player == 'Human' else '▼'),  # 下箭头
                'left': (-1, 0, "⬅" if self.player == 'Human' else '◀'), # 左箭头
                'right': (1, 0, "➡" if self.player == 'Human' else '▶')  # 右箭头
            }
        else:
            directions = {
                'up': (0, -1, "W"),   # W键
                'down': (0, 1, "S"),   # S键
                'left': (-1, 0, "A"),  # A键
                'right': (1, 0, "D")   # D键
            }
        
        current_dir = self.info['snake'].direction if not self.info.get('done') else None
        marker_size = 35
        
        for dir_name, (dx, dy, symbol) in directions.items():
            radius = dial_size//2 - 20
            x = center_x + dx * radius
            y = center_y + dy * radius
            
            # 高亮当前方向
            if dir_name == current_dir:
                # 悬浮动画 + 旋转效果
                hover_offset = np_sin(time()*5) * 3
                y += hover_offset
                
                # 背景改为动态渐变色
                gradient = QRadialGradient(x, y, marker_size)
                gradient.setColorAt(0, self.theme_color.lighter(150))
                gradient.setColorAt(1, self.theme_color.darker(150))
                painter.setBrush(gradient)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(int(x-marker_size//2), int(y-marker_size//2), 
                                marker_size, marker_size)
                
                # 符号添加描边
                painter.setPen(QPen(QColor(30, 30, 30), 2))
                painter.setFont(QFont("Segoe UI Symbol", 18, QFont.Bold))
            else:
                # 非当前方向半透明显示
                painter.setPen(QPen(QColor(255, 255, 255, 100), 2))
                painter.setFont(QFont("Segoe UI Symbol", 14))

            # 绘制符号
            text_width = QFontMetrics(painter.font()).width(symbol)
            painter.drawText(int(x - text_width//2), int(y + 14), symbol)

class GameWidget(QWidget):
    scoreUpdated = pyqtSignal(dict)  # 声明信号

    def __init__(self, parent, args, env=None, game_config=None, easter_egg='star'):
        super().__init__(parent)
        self.env = env
        if game_config is not None:
            self.game_config = game_config
        else:
            self.game_config = {
                'fps': 60,
                1:{'player':'Human','ctrl':'wsad'},
                2:{'player':'Human','ctrl':'default'},
            }

        self.update_init(args)
        if not self.args.is_env:
            self.resetGame()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.updateGameState)
            self.startGame()

        # 添加选择相关属性
        self.selected_cells = OrderedDict()  # 存储已选中的方格坐标
        self.selection_mode = False  # 选择模式开关

        # 添加心形路径追踪相关属性
        self.heart_cells = [(25, 10), (24, 10), (24, 9), (23, 9), (23, 8), (22, 8), (22, 7), (21, 7), (21, 6), (20, 6), (19, 6), (19, 5), (18, 5), (17, 5), (17, 4), (16, 4), (15, 4), (15, 5), (14, 5), (13, 5), (13, 6), (12, 6), (11, 6), (11, 7), (10, 7), (10, 8), (9, 8), (9, 9), (8, 9), (8, 10), (7, 10), (7, 11), (8, 11), (8, 12), (7, 12), (7, 13), (8, 13), (8, 14), (7, 14), (7, 15), (8, 15), (8, 16), (7, 16), (7, 17), (8, 17), (8, 18), (7, 18), (7, 19), (8, 19), (8, 20), (9, 20), (9, 21), (10, 21), (10, 22), (11, 22), (11, 23), (12, 23), (12, 24), (13, 24), (13, 25), (14, 25), (14, 26), (15, 26), (15, 27), (16, 27), (16, 28), (17, 28), (17, 29), (18, 29), (18, 30), (19, 30), (19, 31), (20, 31), (20, 32), (21, 32), (21, 33), (22, 33), (22, 34), (23, 34), (23, 35), (24, 35), (24, 36), (25, 36), (26, 36), (26, 35), (27, 35), (27, 34), (28, 34), (28, 33), (29, 33), (29, 32), (30, 32), (30, 31), (31, 31), (31, 30), (32, 30), (32, 29), (33, 29), (33, 28), (34, 28), (34, 27), (35, 27), (35, 26), (36, 26), (36, 25), (37, 25), (37, 24), (38, 24), (38, 23), (39, 23), (39, 22), (40, 22), (40, 21), (41, 21), (41, 20), (42, 20), (42, 19), (43, 19), (43, 18), (42, 18), (42, 17), (43, 17), (43, 16), (42, 16), (42, 15), (43, 15), (43, 14), (42, 14), (42, 13), (43, 13), (43, 12), (42, 12), (42, 11), (43, 11), (43, 10), (42, 10), (42, 9), (41, 9), (41, 8), (40, 8), (40, 7), (39, 7), (39, 6), (38, 6), (37, 6), (37, 5), (36, 5), (35, 5), (35, 4), (34, 4), (33, 4), (33, 5), (32, 5), (31, 5), (31, 6), (30, 6), (29, 6), (29, 7), (28, 7), (28, 8), (27, 8), (27, 9), (26, 9), (26, 10)]
        self.star_cells = [(25, 5), (24, 5), (24, 6), (24, 7), (23, 7), (23, 8), (23, 9), (23, 10), (22, 10), (22, 11), (22, 12), (22, 13), (22, 14), (22, 15), (21, 15), (20, 15), (19, 15), (18, 15), (17, 15), (16, 15), (15, 15), (14, 15), (13, 15), (12, 15), (11, 15), (10, 15), (9, 15), (8, 15), (7, 15), (7, 16), (8, 16), (9, 16), (9, 17), (10, 17), (11, 17), (11, 18), (12, 18), (13, 18), (13, 19), (14, 19), (15, 19), (15, 20), (16, 20), (17, 20), (17, 21), (18, 21), (19, 21), (19, 22), (20, 22), (21, 22), (21, 23), (21, 24), (21, 25), (20, 25), (20, 26), (19, 26), (19, 27), (18, 27), (18, 28), (17, 28), (17, 29), (16, 29), (16, 30), (15, 30), (15, 31), (14, 31), (14, 32), (13, 32), (13, 33), (13, 34), (13, 35), (13, 36), (14, 36), (15, 36), (16, 36), (17, 36), (17, 35), (18, 35), (18, 34), (19, 34), (19, 33), (20, 33), (20, 32), (21, 32), (21, 31), (22, 31), (22, 30), (23, 30), (23, 29), (24, 29), (24, 28), (25, 28), (26, 28), (26, 29), (27, 29), (27, 30), (28, 30), (28, 31), (29, 31), (29, 32), (30, 32), (30, 33), (31, 33), (31, 34), (32, 34), (32, 35), (33, 35), (33, 36), (34, 36), (35, 36), (36, 36), (37, 36), (37, 35), (37, 34), (37, 33), (37, 32), (36, 32), (36, 31), (35, 31), (35, 30), (34, 30), (34, 29), (33, 29), (33, 28), (32, 28), (32, 27), (31, 27), (31, 26), (30, 26), (30, 25), (29, 25), (29, 24), (29, 23), (29, 22), (30, 22), (31, 22), (31, 21), (32, 21), (33, 21), (33, 20), (34, 20), (35, 20), (35, 19), (36, 19), (37, 19), (37, 18), (38, 18), (39, 18), (39, 17), (40, 17), (41, 17), (41, 16), (42, 16), (43, 16), (43, 15), (42, 15), (41, 15), (40, 15), (39, 15), (38, 15), (37, 15), (36, 15), (35, 15), (34, 15), (33, 15), (32, 15), (31, 15), (30, 15), (29, 15), (28, 15), (28, 14), (28, 13), (28, 12), (28, 11), (28, 10), (27, 10), (27, 9), (27, 8), (27, 7), (26, 7), (26, 6), (26, 5)]
        self.easter_egg = easter_egg
        self.path_following = False  # 是否正在跟随路径
        self.follow_path_map = {
            'border_path':None,'border_target':None,
            'first_heart_path':None,'first_heart_target':None,
            'all_heart_path':None,'all_heart_target':None,
            'wise':np_choice(['顺时针','逆时针']),
            'index_count':defaultdict(int),'done':False,'perfect':False
        }

        self.current_dialog = None

    def update_init(self, args):
        self.args = args
        self.max_score = args.grid_width * args.grid_height

        # 计算实际像素尺寸
        pixel_width = self.args.grid_width * self.args.rect_size
        pixel_height = self.args.grid_height * self.args.rect_size

        self.setFixedSize(pixel_width, pixel_height)
        self.setFocusPolicy(Qt.StrongFocus)

        # 创建苹果图标（尺寸适配网格大小）
        self._food_icon = self.window().create_emoji_icon('🍎', int(self.args.rect_size * 0.9))  # 90%的格子大小

        # 添加心形路径追踪相关属性
        self.border_cells = [(0,i) for i in range(self.args.grid_height)]+\
                    [(self.args.grid_width-1,i) for i in range(self.args.grid_height)]+\
                    [(i,0) for i in range(self.args.grid_width)]+\
                    [(i,self.args.grid_height-1) for i in range(self.args.grid_width)]
        self.border_cells_second = [(1,i) for i in range(1,self.args.grid_height-1)]+\
                    [(self.args.grid_width-2,i) for i in range(1,self.args.grid_height-1)]+\
                    [(i,1) for i in range(1,self.args.grid_width-1)]+\
                    [(i,self.args.grid_height-2) for i in range(1,self.args.grid_width-1)]
        if self.env is not None:
            self.env.args = self.args
            self.env.max_score = self.max_score
            self.env.each_score_steps = 200 if args.grid_width >= 40 else 100

    def mousePressEvent(self, event):
        if self.selection_mode:
            # 将鼠标位置转换为网格坐标
            grid_x = event.x() // self.args.rect_size
            grid_y = event.y() // self.args.rect_size
            
            # 确保坐标在有效范围内
            if 0 <= grid_x < self.args.grid_width and 0 <= grid_y < self.args.grid_height:
                cell = (grid_x, grid_y)
                if cell in self.selected_cells:
                    self.selected_cells.pop(cell)  # 取消选择
                else:
                    self.selected_cells[cell]=1 # 添加选择
                
                self.update()  # 重绘界面

    def startGame(self):
        assert any(self.game_config[i].get('player') in ['AI-DQN1','AI-DQN2','Rule-BFS','Human'] for i in [1,2])
        self.only_ai = True if all(self.game_config[i].get('player') in ['AI-DQN1','AI-DQN2','Rule-BFS'] for i in [1,2] if self.game_config[i].get('player') is not None) else False
        fps = self.game_config['fps']
        self.timer.start(fps)

    def resetGame(self):
        self.env.init_data(self.game_config)
        self.value_map = self.env.value_map
        self.food = self.env.food

        self.window().left_info.chat_lines.clear()
        self.window().left_info.append_flag = True
        self.window().right_info.chat_lines.clear()
        self.window().right_info.append_flag = True
        self.follow_path_map = {
            'border_path':None,'border_target':None,
            'first_heart_path':None,'first_heart_target':None,
            'all_heart_path':None,'all_heart_target':None,
            'wise':np_choice(['顺时针','逆时针']),
            'index_count':defaultdict(int),'done':False,'perfect':False
        }
        self.path_following = False
        if hasattr(self,'text_animation'):
            self.text_animation.stop()
        self.celebration_counter = 0
        self._food_icon = self.window().create_emoji_icon('🍎', int(self.args.rect_size * 0.9))  # 90%的格子大小
        self.selected_cells = OrderedDict()  # 存储已选中的方格坐标
        self.selection_mode = False  # 选择模式开关

    def handleKeyPress(self, event):
        """处理玩家按键"""
        key = event.key()
        if not self.only_ai:
            # 玩家1方向键
            if key in [Qt.Key_Up, Qt.Key_Right, Qt.Key_Down, Qt.Key_Left]:
                for number in [1,2]:
                    if self.value_map[number].get('player') != 'Human' or \
                        self.value_map[number].get('ctrl') != 'default':
                        continue
                    self.value_map[number]['key_pressed'] = key
                    break

            # 玩家2WASD控制
            elif key in [Qt.Key_W, Qt.Key_D, Qt.Key_S, Qt.Key_A]:
                key = {
                    Qt.Key_W:Qt.Key_Up,
                    Qt.Key_D:Qt.Key_Right,
                    Qt.Key_S:Qt.Key_Down,
                    Qt.Key_A:Qt.Key_Left
                }[key]
                for number in [1,2]:
                    if self.value_map[number].get('player') != 'Human' or \
                        self.value_map[number].get('ctrl') != 'wsad':
                        continue
                    self.value_map[number]['key_pressed'] = key
                    break
                
        if key == Qt.Key_Escape:
            self.showDialogue('暂停')

    def calc_action(self, number):
        if self.game_config[number].get('player') and 'AI-DQN' in self.game_config[number].get('player'):
            if self.value_map[number]['bfs_move'] > 0:
                action = self.bfs_agent(number)
                self.value_map[number]['bfs_move'] -= 1
            else:
                state = self.env._get_state(number)
                action = self.game_config[number]['agent'].act(state, epsilon=0)
        elif self.game_config[number].get('player') == 'Rule-BFS':
            action = self.bfs_agent(number)
        elif self.value_map[number]['key_pressed'] is None:
            action = None
        elif self.value_map[number]['key_pressed'] is not None:
            if self.value_map[number]['snake'].direction == 'none':
                action = self.value_map[number]['key_pressed']
            else:
                for action,dir in self.env.action_map[self.value_map[number]['snake'].direction].items():
                    if self.value_map[number]['key_pressed'] == self.env.qt_key_map[dir]:
                        break
                else:
                    action = 0 # 直行
        
        return action

    def updateGameState(self):
        # 停止定时器，等待所有计算完成
        self.timer.stop()
        
        easter_egg_cells = self.star_cells if self.easter_egg == 'star' else self.heart_cells
        border_cells = self.border_cells + self.border_cells_second if self.easter_egg == 'star' else self.border_cells
        actions = [None,None]
        if (self.path_following or any([self.value_map[i]['score'] == len(easter_egg_cells) for i in [1,2]])) and (not self.follow_path_map['done']) and (sum([self.value_map[i]['done'] for i in [1,2]]) == 1) and self.window().media_player.volume() != 0 and self.max_score == 2000:
            # 彩蛋模式
            for number in [1, 2]:
                if self.value_map[number]['done']:
                    continue

                if self.value_map[number]['easter_egg'] is None:
                    self.value_map[number]['easter_egg'] = 'border'
                    if hasattr(self,'falling_hearts'):
                        del self.falling_hearts
                if self.value_map[number]['easter_egg'] == 'border' and set([tuple(i) for i in self.value_map[number]['snake'].body]) - set(border_cells) == set():
                    self.value_map[number]['easter_egg'] = 'first_heart'
                if self.value_map[number]['easter_egg'] == 'first_heart' and set([tuple(i) for i in self.value_map[number]['snake'].body]) & set(easter_egg_cells) != set():
                    self.value_map[number]['easter_egg'] = 'all_heart'
                if self.value_map[number]['easter_egg'] == 'all_heart':
                    if set([tuple(i) for i in self.value_map[number]['snake'].body]) - set(easter_egg_cells) == set():
                        self.follow_path_map['perfect'] = True
                        self._food_icon = self.window().create_emoji_icon('⭐', int(self.args.rect_size * 0.9))  # 90%的格子大小
                    if len(self.follow_path_map['index_count']) > 0 and set(self.follow_path_map['index_count'].values()) == {2}:
                        # 显示消息
                        self.show_message()
                    if self.easter_egg == 'star' and hasattr(self,'falling_hearts') and all([i['finished'] for i in self.falling_hearts]):
                        self.follow_path_map['done'] = True
                        self.value_map[number]['easter_egg'] = None
                        self._food_icon = self.window().create_emoji_icon('🍎', int(self.args.rect_size * 0.9))  # 90%的格子大小

                if self.value_map[number]['easter_egg'] is not None:
                    action = self._get_path_following_action(number,easter_egg_cells)
                    actions[number-1] = action
        else:
            # 创建线程池执行AI计算
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {}
                for number in [1, 2]:
                    if not self.value_map[number]['done']:
                        futures[number] = executor.submit(self.calc_action, number)
                
                # 等待所有计算完成
                for number, future in futures.items():
                    actions[number-1] = future.result()
        
        self.value_map = self.env.step(actions,is_play=True)
        self.env.value_map = self.value_map
        self.scoreUpdated.emit(self.value_map)  # 发射信号
        self.update() # 重绘界面

        # 重新启动定时器
        self.timer.start(self.game_config['fps'])

        if any([self.value_map[i]['victory'] for i in [1,2]]):
            self.showDialogue('Victory')
            return

        if all([self.value_map[i]['done'] for i in [1,2]]):
            self.showDialogue('游戏结束')

    def _get_path_following_action(self, number, easter_egg_cells):
        easter_egg = self.value_map[number]['easter_egg']
        assert easter_egg in ['border','first_heart','all_heart']

        snake = self.value_map[number]['snake']
        another = self.value_map[{1:2,2:1}[number]]['snake']
        head = snake.body[0]
        direction = snake.direction

        if easter_egg in ['border','first_heart']:
            func = max
            if tuple(head) == self.follow_path_map[f'{easter_egg}_target']:
                self.follow_path_map[f'{easter_egg}_target'] = None
                func = min

            if easter_egg == 'first_heart':
                func = min
                cells = [i for i in easter_egg_cells if list(i) not in snake.body+another.body]
            else:
                cells = [i for i in self.border_cells if list(i) not in snake.body+another.body]
                cells = list(set(cells))
                if len(cells) == 0:
                    cells = [i for i in self.border_cells_second if list(i) not in snake.body+another.body]
                    cells = list(set(cells))

            if self.follow_path_map[f'{easter_egg}_target'] is None:
                self.follow_path_map[f'{easter_egg}_target'] = func(cells, key=lambda f: abs(f[0] - head[0]) + abs(f[1] - head[1]))

            action = self.bfs_agent(number, self.follow_path_map[f'{easter_egg}_target'])
        else:
            index = easter_egg_cells.index(tuple(head))
            if self.follow_path_map['wise'] == '顺时针':
                next_index = (index + 1) % len(easter_egg_cells)
            else:
                next_index = (index - 1) % len(easter_egg_cells)
            value = np_array(easter_egg_cells[next_index]) - np_array(head)

            for d,v in snake.d_map.items():
                if value.tolist() == v:
                    break
            else:
                d = np_choice(list(snake.d_map.keys()))

            for action,dir in self.env.action_map[direction].items():
                if d == dir:
                    break
            else:
                action = 0 # 直行

            self.follow_path_map['index_count'][index] += 1

        return action

    def _find_path_bfs(self, snake, another, target, obstacles_add=None):
        """使用BFS算法寻找安全路径"""
        head = snake.body[0]
        visited = set([tuple(head)])
        queue = [(head, [])]
        score = len({tuple(i) for i in snake.body})
        direction = snake.direction
        
        # 定义四个可能的移动方向
        directions = {
            'right':[1, 0],   # 右
            'left':[-1, 0],  # 左
            'down':[0, 1],   # 下
            'up':[0, -1]   # 上
        }
        shuffle_d = list(directions.keys())
        np_shuffle(shuffle_d)

        # 创建障碍物地图（排除两条蛇，但不包括蛇尾，蛇尾是安全的）
        obstacles = set()
        for seg in snake.body[:-1]+another.body[:-1]:
            grid = tuple(seg)
            obstacles.add(grid)
        if obstacles_add is not None:
            obstacles.add(obstacles_add) # 如果吃完食物后找不到蛇尾的路径，那么此时食物可认为是障碍

        count = 0
        while queue:
            current, path = queue.pop(0)
            
            # 如果到达目标点
            if current[0] == target[0] and current[1] == target[1]:
                return path
                
            for dir,(dx, dy) in directions.items():
                if count == 0 and score == 1 and dir not in set(self.env.action_map[direction].values()):
                    continue
                
                nx, ny = current[0] + dx, current[1] + dy
                # 检查新位置是否有效
                if (0 <= nx < self.args.grid_width and 
                    0 <= ny < self.args.grid_height and 
                    (nx, ny) not in visited and 
                    (nx, ny) not in obstacles):
                    
                    visited.add((nx, ny))
                    new_path = path + [dir]
                    queue.append(([nx, ny], new_path))

            count+=1
        
        return None  # 没有找到路径

    def bfs_agent(self, number, target=None):
        if not hasattr(self, 'action_count_map'):
            self.action_count_map = defaultdict(int)

        qt_key_map = self.env.qt_key_map
        action_map = self.env.action_map

        snake=self.value_map[number]['snake']
        another=self.value_map[{1:2,2:1}[number]]['snake']

        def _path_to_action(path,direction):
            for action,dir in action_map[direction].items():
                if path == dir:
                    break
            else:
                action = 0
            return action

        min_food = self.env.min_foods[number-1] if target is None else target
        v_snake = deepcopy(snake)
        path_food = self._find_path_bfs(v_snake, another, min_food)
        path_tail = None
        action_food = []
        if path_food is not None:
            for path in path_food:
                action = _path_to_action(path,v_snake.direction)
                action_food.append(action)
                key = qt_key_map[action_map[v_snake.direction][action]]
                v_snake.changeDirection(key)
                v_snake.move()
            v_snake.grow()
            tail = v_snake.body[-1]
            path_tail = self._find_path_bfs(v_snake, another, tail)
        
        if path_tail is not None:
            self.action_count_map['action_food'] += 1
            return action_food[0]
        
        # 定义四个可能的移动方向
        directions = {
            'right':[1, 0],   # 右
            'left':[-1, 0],  # 左
            'down':[0, 1],   # 下
            'up':[0, -1]   # 上
        }
        shuffle_d = list(directions.keys())
        np_shuffle(shuffle_d)

        head = snake.body[0]
        visited = set([tuple(head)])
        # 创建障碍物地图（排除两条蛇，但不包括蛇尾，蛇尾是安全的，且不能吃到食物，因为前面验证过吃了食物会找不到蛇尾）
        obstacles = set()
        for seg in snake.body[:-1]+another.body[:-1]:
            grid = tuple(seg)
            obstacles.add(grid)
        obstacles.add(tuple(min_food))

        dis = -np_inf
        longest_action = []
        safe_action = []
        for direction in shuffle_d:
            dx, dy = directions[direction]
            if direction not in set(action_map[snake.direction].values()):
                continue
            nx, ny = head[0] + dx, head[1] + dy
            # 检查新位置是否有效
            if (0 <= nx < self.args.grid_width and 
                0 <= ny < self.args.grid_height and 
                (nx, ny) not in visited and 
                (nx, ny) not in obstacles):
                v_snake = deepcopy(snake)
                action = _path_to_action(direction,v_snake.direction)
                key = qt_key_map[action_map[v_snake.direction][action]]
                v_snake.changeDirection(key)
                v_snake.move()
                tail = v_snake.body[-1]
                this_dis = abs(nx - tail[0]) + abs(ny - tail[1])
                if self._find_path_bfs(v_snake, another, tail, obstacles_add=tuple(min_food)) is not None:
                    safe_action.append(action)
                    if this_dis > dis:
                        dis = this_dis
                        longest_action.append(action)

        if len(longest_action) > 0 and self.value_map[number]['didn_eat_steps'] < self.value_map[number]['max_steps'] * 0.5:
            self.action_count_map['longest_action'] += 1
            return longest_action[-1]
        
        if len(safe_action) > 0:
            self.action_count_map['safe_action'] += 1
            return np_choice(safe_action)

        tail = snake.body[-1]
        path_tail = self._find_path_bfs(snake, another, tail, obstacles_add=tuple(min_food))
        if path_tail is not None:
            action = _path_to_action(path_tail[0],snake.direction)
            self.action_count_map['tail_exclude_food_action'] += 1
            return action
        
        tail = snake.body[-1]
        path_tail = self._find_path_bfs(snake, another, tail)
        if path_tail is not None:
            action = _path_to_action(path_tail[0],snake.direction)
            self.action_count_map['tail_eat_food_action'] += 1
            return action

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self.env._calculate_reachable_cells, a, snake, another) for a in [0, 1, 2]]
            (forward_free,forward_big), (left_free,left_big), (right_free,right_big) = [f.result() for f in futures]
            frees = [forward_free,left_free,right_free]

        self.action_count_map['frees_action'] += 1
        return np_argmax(frees).item()

    def paintEvent(self, event):
        painter = QPainter(self)
    
        # 渐变背景
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(40, 40, 50))
        gradient.setColorAt(1, QColor(25, 25, 35))
        painter.fillRect(self.rect(), gradient)

        # 绘制网格线
        painter.setPen(QPen(QColor(80, 80, 100, 50), 1))
        grid_size = self.args.rect_size
        for x in range(0, self.width(), grid_size):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), grid_size):
            painter.drawLine(0, y, self.width(), y)

        self.drawSnake(painter)
        self.drawFood(painter)

        # 绘制被选中的方格
        if self.selection_mode and self.selected_cells:
            painter.setBrush(QColor(255, 255, 0, 100))  # 半透明黄色
            painter.setPen(QPen(QColor(255, 255, 0), 2))
            
            size = self.args.rect_size
            for cell in self.selected_cells:
                x = cell[0] * size
                y = cell[1] * size
                painter.drawRect(x, y, size, size)

        # 绘制庆祝文字和爱心效果
        if hasattr(self, 'celebration_text') and self.celebration_counter > 0:
            painter.save()
            
            colors = [
                (255, 0, 0),    # 红
                (255, 165, 0),  # 橙
                (255, 255, 0),  # 黄
                (0, 128, 0),    # 绿
                (0, 0, 255),    # 蓝
                (75, 0, 130),   # 靛
                (238, 130, 238) # 紫
            ]
            
            # ===== 4. 飘落粒子效果 =====
            if not hasattr(self, 'falling_hearts'):
                # 初始化飘落爱心
                self.falling_hearts = []
                for _ in range(520 if self.easter_egg != 'star' else 100):  # 100个飘落爱心
                    self.falling_hearts.append({
                        'x': random_randint(0, self.width()),
                        'y': random_randint(-int(self.height()*0.5), 0),
                        'size': random_randint(10, 30),
                        'speed': random_uniform(3.0, 5.0),
                        'color': random_choice(colors),
                        'alpha': random_randint(150, 220),
                        'finished': False  # 添加粒子完成标志
                    })
            # 更新已有爱心位置
            for i in range(len(self.falling_hearts)):
                if self.falling_hearts[i]['finished']:  # 如果粒子已经完成，则不更新位置
                    continue

                self.falling_hearts[i]['y'] += self.falling_hearts[i]['speed']
                if self.falling_hearts[i]['y'] > self.height():
                    self.falling_hearts[i]['finished'] = True
                
                # 绘制飘落爱心
                func = self._draw_mini_star
                func(
                    painter,
                    int(self.falling_hearts[i]['x']),
                    int(self.falling_hearts[i]['y']),
                    self.falling_hearts[i]['size'],
                    color=QColor(*self.falling_hearts[i]['color']),
                    alpha=self.falling_hearts[i]['alpha']
                )
            
            painter.restore()

    def drawSnake(self, painter):
        # 找出分数更高的蛇
        leading_number = 0 if self.value_map[1]['score'] == self.value_map[2]['score'] else (1 if self.value_map[1]['score'] > self.value_map[2]['score'] else 2)

        for number in [1,2]:
            # 检查是否处于心形路径跟随状态
            is_easter_egg_path = self.value_map[number]['easter_egg'] is not None and (sum([self.value_map[i]['done'] for i in [1,2]]) == 1)

            snake_len = len(self.value_map[number]['snake'].body)
            if is_easter_egg_path:
                snake_color = (219, 112, 147)
                glow_color = QColor(255, 182, 193)
            else:
                snake_color = self.value_map[number].get('color', (30, 144, 255) if number == 1 else (255, 69, 0))
                glow_color = self._get_contrast_glow_color(snake_color)
            
            if is_easter_egg_path:
                snake_colors = get_gradient_colors(snake_len)
            else:
                snake_colors = neon_gradient_colors(snake_len, base_color=snake_color)
            
            # 根据是否是领先者增强效果
            is_leading = (number == leading_number) and not any([self.value_map[i]['done'] for i in [1,2]])

            head_scheme = {
                'color': QColor(*snake_color),
                'glow_color': glow_color,
                'pulse_ratio': 1.3 if is_leading else 1.1,  # 领先者头部更大
                'extra_effects': is_leading  # 是否添加额外效果
            }

            for i, segment in enumerate(self.value_map[number]['snake'].body):
                size = self.args.rect_size
                x = segment[0] * size
                y = segment[1] * size

                if i == 0:
                    self._draw_snake_head(painter, x, y, size,head_scheme,self.value_map[number]['snake'].direction)
                else:
                    # 3D立体效果
                    base_color = QColor(*(snake_colors[i]))
                    shadow_color = base_color.darker(150)
                    
                    # 主体
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(base_color)
                    painter.drawRoundedRect(x+2, y+2, size-4, size-4, 4, 4)

                    if is_easter_egg_path:
                        self._draw_easter_egg_segment(painter, x, y, size,is_tail=i==snake_len-1)
                    else:
                        # 高光
                        highlight = QLinearGradient(x, y, x, y+size)
                        highlight.setColorAt(0, QColor(255,255,255,50))
                        highlight.setColorAt(1, Qt.transparent)
                        painter.setBrush(highlight)
                        painter.drawRoundedRect(x+2, y+2, size-4, size-4, 4, 4)
                        
                        # # 阴影
                        painter.setBrush(shadow_color)
                        painter.drawRoundedRect(x-1, y-1, size, size, 4, 4)

    def _draw_easter_egg_segment(self, painter, x, y, size, is_tail=False):
        """彩蛋模式的蛇身"""
        painter.save()
        
        # ---- 1. 基础渐变 ----
        segment_rect = QRect(x, y, size, size)
        gradient = QLinearGradient(x, y, x + size, y + size)
        gradient.setColorAt(0, QColor(255, 182, 193))  # 浅粉红
        gradient.setColorAt(1, QColor(219, 112, 147))  # 中粉红

        # ---- 2. 爱心纹理 ----
        if random_random() > 0.5:  # 30%概率出现爱心纹理
            texture = QPixmap(size, size)
            texture.fill(Qt.transparent)
            tex_painter = QPainter(texture)
            
            for _ in range(3):
                heart_size = random_randint(size//6, size//4)
                heart_x = random_randint(0, size - heart_size)
                heart_y = random_randint(0, size - heart_size)
                func = self._draw_mini_star
                func(
                    tex_painter, 
                    heart_x, heart_y, 
                    heart_size,
                    color=QColor(255, 255, 255, 80)
                )
            
            tex_painter.end()
            painter.setBrush(QBrush(texture))
        
        # ---- 3. 3D效果 ----
        painter.setPen(QPen(QColor(199, 21, 133, 150), 2))
        painter.drawRoundedRect(segment_rect, 4, 4)
        
        # 高光效果
        if not is_tail:
            highlight = QLinearGradient(x, y, x, y + size)
            highlight.setColorAt(0, QColor(255, 255, 255, 80))
            highlight.setColorAt(0.7, Qt.transparent)
            painter.setBrush(highlight)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(segment_rect, 4, 4)
        
        # ---- 4. 尾部特殊标记 ----
        if is_tail:
            func = self._draw_mini_star
            func(
                painter,
                x + size//2,
                y + size//2,
                size//3,
                color=QColor(255, 20, 147, 200)
            )
        
        painter.restore()

    # 辅助函数：绘制迷你爱心
    def _draw_mini_heart(self, painter, x, y, size, color=None, alpha=255):
        """绘制小型爱心 (性能优化版)"""
        path = QPainterPath()
        size = max(5, size)  # 最小尺寸限制
        
        # 简化版心形路径
        path.moveTo(x, y - size//3)
        path.cubicTo(
            x - size//2, y - size,
            x - size, y,
            x, y + size//2
        )
        path.cubicTo(
            x + size, y,
            x + size//2, y - size,
            x, y - size//3
        )
        
        if color is None:
            color = QColor(255, 105, 180, alpha)
        else:
            color.setAlpha(alpha)
        
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

    def _draw_mini_star(self, painter, x, y, size, color=None, alpha=255):
        """绘制小型五角星 (性能优化版)"""
        path = QPainterPath()
        size = max(5, size)  # 最小尺寸限制

        # 五角星路径参数
        outer_radius = size
        inner_radius = outer_radius * 0.382  # 黄金比例
        
        # 绘制五角星路径
        for i in range(5):
            # 外点
            outer_angle = 2 * np_pi * i / 5 - np_pi/2  # 旋转90度使一个尖朝上
            outer_x = x + outer_radius * np_cos(outer_angle)
            outer_y = y + outer_radius * np_sin(outer_angle)
            
            # 内点
            inner_angle = outer_angle + np_pi/5  # 每个内点位于两个外点之间
            inner_x = x + inner_radius * np_cos(inner_angle)
            inner_y = y + inner_radius * np_sin(inner_angle)
            
            if i == 0:
                path.moveTo(outer_x, outer_y)
            else:
                path.lineTo(outer_x, outer_y)
            
            path.lineTo(inner_x, inner_y)
        
        path.closeSubpath()

        if color is None:
            color = QColor(255, 215, 0, alpha)  # 默认金色
        else:
            color.setAlpha(alpha)
        
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

    def _get_contrast_glow_color(self, base_color):
        """更智能的对比色生成方法"""
        r, g, b = base_color
        
        # 计算亮度
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        
        if brightness > 150:  # 非常亮的颜色
            # 生成深色光晕 - 降低亮度40%
            return QColor(
                int(r * 0.6),
                int(g * 0.6),
                int(b * 0.6),
                120  # 较高的不透明度
            )
        elif brightness > 100:  # 中等亮度
            # 轻微加深
            return QColor(
                int(r * 0.8),
                int(g * 0.8),
                int(b * 0.8),
                100
            )
        else:  # 暗色
            # 生成亮色光晕 - 提高亮度
            return QColor(
                min(int(r * 1.6), 255),
                min(int(g * 1.6), 255),
                min(int(b * 1.6), 255),
                80  # 较低的不透明度
            )

    def _draw_snake_head(self, painter, x, y, size, scheme, direction):
        """绘制带特效的蛇头"""
        # 动态参数
        pulse = abs(np_sin(time()*5)) * 3  # 脉动动画
        rotation_map = {
            'up': 0,
            'right': 90,
            'down': 180,
            'left': 270,
            'none': 360
        }
        
        # 保存画布状态
        painter.save()
        
        # 移动到头部中心
        painter.translate(x + size/2, y + size/2)
        painter.rotate(rotation_map[direction])
        
        # 绘制光晕效果
        glow_radius = int(size * scheme['pulse_ratio'] + pulse)
        gradient = QRadialGradient(0, 0, glow_radius)
        gradient.setColorAt(0, scheme['glow_color'])
        gradient.setColorAt(1, Qt.transparent)
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(-glow_radius, -glow_radius, 2*glow_radius, 2*glow_radius)
        
        # 绘制头部主体
        head_size = size * 0.8 * scheme['pulse_ratio']
        painter.setBrush(scheme['color'])
        painter.setPen(QPen(Qt.white, 2))
        
        # 绘制三角形
        path = QPainterPath()
        path.moveTo(-head_size/2, head_size/2)
        path.lineTo(0, -head_size/2)
        path.lineTo(head_size/2, head_size/2)
        path.closeSubpath()
        painter.drawPath(path)

        # 添加眼睛效果
        eye_size = size * 0.15
        # 左眼
        painter.setBrush(Qt.white)
        painter.drawEllipse(int(-head_size/3 - eye_size/2), 
                        int(-head_size/4 - eye_size/2), 
                        int(eye_size), int(eye_size))
        # 右眼
        painter.drawEllipse(int(head_size/3 - eye_size/2), 
                        int(-head_size/4 - eye_size/2), 
                        int(eye_size), int(eye_size))
        
        # 领先者添加旋转光晕
        if scheme['extra_effects']:
            glow_radius = int(size * 1.2)
            for i in range(3):  # 三层光晕
                rotation = (time() * (i+1) * 30) % 360
                painter.rotate(rotation)
                
                gradient = QConicalGradient(0, 0, rotation)
                gradient.setColorAt(0, scheme['glow_color'].lighter(200))
                gradient.setColorAt(0.5, Qt.transparent)
                gradient.setColorAt(1, Qt.transparent)
                
                painter.setBrush(gradient)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(-glow_radius, -glow_radius, glow_radius*2, glow_radius*2)
                painter.rotate(-rotation)  # 恢复旋转

        # 恢复画布状态
        painter.restore()

    def drawFood(self, painter):
        # 绘制所有食物
        for food in self.food.foods:
            size = self.args.rect_size
            x = food[0] * size
            y = food[1] * size
            
            # 计算绘制位置（居中）
            offset = (size - self._food_icon.actualSize(QSize(size, size)).width()) // 2
            rect = QRect(x + offset, y + offset, size, size)
            
            # 绘制带动态效果的食物
            current_time = QTime.currentTime()
            msec = current_time.msec() + current_time.second() * 1000

            # 保存画布状态
            painter.save()

            # 改为匀速旋转动画：每秒转一圈（1000ms/360度）
            rotation = (msec / 1000) * 360  # 每秒旋转360度
            painter.translate(rect.center())        # 移动到中心点
            painter.rotate(rotation)              # 绕中心点旋转
            painter.translate(-rect.center())      # 恢复原坐标系

            # 绘制苹果图标
            self._food_icon.paint(painter, rect, Qt.AlignCenter)

            # 恢复画布状态
            painter.restore()

        # 绘制被吃掉时的特效
        for food in self.food.eated:
            size = self.args.rect_size
            x, y = food[0]*size, food[1]*size
            center_x, center_y = x + size/2, y + size/2
            self._draw_eaten_effect(painter, center_x, center_y)
        self.food.eated.clear()

    def _draw_eaten_effect(self, painter, x, y):
        """绘制被吃时的特效"""
        # 粒子爆发效果
        for i in range(8):
            angle = i * np_pi/4
            dx = (self.args.rect_size - 5) * np_cos(angle + time()*5)
            dy = (self.args.rect_size - 5) * np_sin(angle + time()*5)
            painter.setBrush(QColor(255, 80, 80, 200))  # 红色粒子
            painter.drawEllipse(int(x+dx), int(y+dy), self.args.rect_size//8,self.args.rect_size//8)

    def showDialogue(self,title):
        self.timer.stop()

        if self.current_dialog is not None:
            self.current_dialog.close()

        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)

        if title != 'Victory':
            # 关键设置：使背景完全透明
            dialog.setWindowFlags(dialog.windowFlags() | Qt.FramelessWindowHint)
            dialog.setAttribute(Qt.WA_TranslucentBackground)
        else:
            dialog.setWindowIcon(self.window().create_emoji_icon('🏆'))  # 设置 Emoji 图标
            dialog.setText("🎉 恭喜你，完美通关！")
            dialog.setStyleSheet(f"""
                QMessageBox {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #ff9a9e, stop:1 #fad0c4);
                    border: 3px solid #ff69b4;
                    border-radius: 15px;
                    font-size: {40 if self.window().dpi_gt96 else 20}px;
                    color: #8b0000;
                    min-width: 400px;
                }}
                QLabel {{
                    color: #8b0000;
                    font-weight: bold;
                    font-size: {40 if self.window().dpi_gt96 else 20}px;
                }}
                QPushButton {{
                    background-color: #ff69b4;
                    color: white;
                    border-radius: 10px;
                    padding: 10px 20px;
                    min-width: {200 if self.window().dpi_gt96 else 100}px;
                    min-height: {50 if self.window().dpi_gt96 else 25}px;
                    font-size: {40 if self.window().dpi_gt96 else 20}px;
                }}
                QPushButton:hover {{
                    background-color: #ff1493;
                }}
            """)

        # 按钮定义与角色分配
        resume_button,retry_button = None,None
        if title == '暂停':
            resume_button = dialog.addButton("继续游戏", QMessageBox.AcceptRole)
        else:
            retry_button = dialog.addButton("重新开始", QMessageBox.AcceptRole)
        return_button = dialog.addButton("返回主菜单", QMessageBox.ActionRole)
        exit_button = dialog.addButton("退出游戏", QMessageBox.RejectRole)
        
        if title == '暂停':
            dialog.setEscapeButton(resume_button)
        else:
            dialog.setEscapeButton(return_button)

        # 连接信号处理结果
        dialog.buttonClicked.connect(lambda btn: self.handleDialogResult(btn, dialog, title))

        # 非阻塞显示
        dialog.show()
        self.current_dialog = dialog

        dialog.installEventFilter(self)  # 让主窗口处理事件

    def handleDialogResult(self, button, dialog, title):
        role = dialog.buttonRole(button)
        
        if role == QMessageBox.AcceptRole:
            if title == '暂停':
                self.startGame()
            else:
                self.resetGame()
                self.startGame()
        elif role == QMessageBox.ActionRole:
            self.window().show_menu()
        elif role == QMessageBox.RejectRole:
            self.window()._force_close = True
            self.window().close()

        # 清理对话框引用
        self.current_dialog = None

    def show_celebration_effect(self):
        # 显示庆祝文字
        self.celebration_text = ""
        self.celebration_counter = 0
        
        # 启动文字动画计时器
        self.text_animation = QTimer(self)
        self.text_animation.timeout.connect(self.update_celebration_text)
        self.text_animation.start(50)

    def update_celebration_text(self):
        """更新庆祝文字效果"""
        self.celebration_counter += 1
        self.update()

    def show_message(self):
        # 确保游戏暂停
        self.timer.stop()
        
        # 创建半透明背景
        overlay = QWidget(self)
        overlay.setGeometry(0, 0, self.width(), self.height())
        overlay.setStyleSheet("background-color: rgba(0, 0, 0, 150);")
        overlay.show()
        
        # 创建自定义对话框
        dialog = QDialog(self)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint & ~Qt.WindowCloseButtonHint)
        dialog.setWindowTitle('隐藏彩蛋')
        dialog.setWindowIcon(self.window().create_emoji_icon('🌟'))  # 设置 Emoji 图标
        
        if self.window().dpi_gt96:
            dialog.setMinimumSize(1314, 520)
        else:
            dialog.setMinimumSize(520, 520)
        dialog.setStyleSheet(f"""
            QMessageBox {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ff9a9e, stop:1 #fad0c4);
                border: 3px solid #ff69b4;
                border-radius: 15px;
                font-size: {40 if self.window().dpi_gt96 else 20}px;
                color: #8b0000;
                min-width: 400px;
            }}
            QLabel {{
                color: #8b0000;
                font-weight: bold;
                font-size: {40 if self.window().dpi_gt96 else 20}px;
            }}
            QPushButton {{
                background-color: #ff69b4;
                color: white;
                border-radius: 10px;
                padding: 10px 20px;
                min-width: 100px;
                font-size: {40 if self.window().dpi_gt96 else 20}px;
            }}
            QPushButton:hover {{
                background-color: #ff1493;
            }}
        """)

        # 主布局
        layout = QVBoxLayout(dialog)
        
        # 文本标签
        self.easter_egg_text = ("恭喜你！获得了一颗七彩幸运星！⭐\n\n"
            "愿你从今往后平安健康、幸福美满！\n\n"
            "2025蛇年，蛇来运转！")
        label = QLabel(self.easter_egg_text)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        # 按钮容器
        button_layout = QHBoxLayout(objectName="button_layout")
        button_layout.setSpacing(20)
        button_layout.setContentsMargins(50, 20, 50, 20)
        
        # 创建两个按钮
        self.yes_button = QPushButton("接好运！🌠", objectName="yes_button")
        self.no_button = QPushButton("再想想", objectName="no_button")
        
        self.yes_ind = 0
        
        # 初始按钮顺序
        button_layout.addWidget(self.yes_button)
        button_layout.addWidget(self.no_button)
        
        # 为"考虑一下"按钮添加事件过滤器
        self.yes_button.installEventFilter(self)
        self.no_button.installEventFilter(self)
        # 添加：为对话框安装键盘事件过滤器
        dialog.installEventFilter(self)
        
        # 连接按钮信号
        self.yes_button.clicked.connect(dialog.accept)
        self.no_button.clicked.connect(dialog.reject)
        
        layout.addLayout(button_layout)
        
        # 显示对话框
        dialog.exec_()
        
        # 处理结果
        if dialog.result() == QDialog.Accepted:
            # 特殊庆祝效果
            self.show_celebration_effect()
        
        # 清理
        overlay.deleteLater()
        self.timer.start()

    def eventFilter(self, obj, event):
        """事件过滤器，用于处理按钮悬停事件"""
        if self.current_dialog is not None:
            if event.type() == QEvent.KeyPress:
                key = event.key()
                # 音量调节
                if event.modifiers() & Qt.ControlModifier and key in [Qt.Key_Plus, Qt.Key_Minus]:
                    self.window().adjust_volume(1 if key == Qt.Key_Plus else -1)
                    return True
                # FPS调整
                if key in [Qt.Key_Plus, Qt.Key_Minus]:
                    self.window().adjust_fps(1 if key == Qt.Key_Plus else -1)
                    return True
                # 切歌
                if event.modifiers() & Qt.ControlModifier and key == Qt.Key_N:
                    self.window().playlist.next()
                    return True
                # 切主题
                if event.modifiers() & Qt.ControlModifier and key == Qt.Key_M:
                    self.window().adjust_color()
                    self.scoreUpdated.emit(self.value_map)  # 发射信号
                    self.update() # 重绘界面
                    return True
        else:
            if hasattr(self,'no_button') and obj == self.no_button and event.type() == event.Enter:
                # 当鼠标悬停在"考虑一下"按钮上时，交换按钮位置
                layout = self.no_button.parent().findChild(QHBoxLayout, "button_layout")
                
                # 保存当前按钮
                yes_btn = self.no_button.parent().findChild(QPushButton, "yes_button")
                no_btn = self.no_button.parent().findChild(QPushButton, "no_button")
                
                # 交换位置重新添加
                if self.yes_ind == 0:
                    layout.insertWidget(0, no_btn)  # 将no_btn移动到第一个位置
                    layout.insertWidget(1, yes_btn)  # 将yes_btn移动到第二个位置
                    self.yes_ind = 1
                else:
                    layout.insertWidget(0, yes_btn)  # 将no_btn移动到第一个位置
                    layout.insertWidget(1, no_btn)  # 将yes_btn移动到第二个位置
                    self.yes_ind = 0

            # 处理键盘事件 - 禁用方向键
            if event.type() == QEvent.KeyPress:
                key = event.key()
                # 禁用所有方向键
                if key in [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,Qt.Key_Enter,Qt.Key_Return,Qt.Key_Escape,Qt.Key_Space]:
                    return True  # 表示事件已被处理，不再传递
        
        return super().eventFilter(obj, event)