from collections import deque, namedtuple
from random import random as random_random, choice as random_choice, getstate as random_getstate
from gc import collect as gc_collect
from copy import deepcopy
from datetime import datetime

from numpy.random import choice as np_choice,randint as np_randint,get_state as np_get_state,uniform as np_uniform
from numpy.linalg import norm as np_norm
from numpy import array as np_array,ones as np_ones,zeros as np_zeros,\
    float32,float64,int64,exp as np_exp,bool_,savez as np_savez,\
    load as np_load,argmax as np_argmax,arange as np_arange
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtCore import Qt, QTimer

from torch import tensor as torch_tensor,float32 as torch_float32,long as torch_long,\
    no_grad,save as torch_save,get_rng_state,load as torch_load,device as torch_device
from torch.cuda import get_rng_state_all,is_available
from torch.amp import GradScaler,autocast
from torch.nn.utils import clip_grad_norm_
from torch.nn import Module, Sequential, Linear, ReLU, Dropout
from torch.optim import Adam

from utils import Struct
from snake_game import Snake,Food,MainWindow

class SnakeEnv:
    def __init__(self, args, qt_app=None):
        self.args = args
        self.max_score = args.grid_width * args.grid_height
        self.each_score_steps = self.max_score // 10 if not hasattr(args,'each_score_steps') else args.each_score_steps
        self.render_mode = qt_app is not None

        # 初始化Qt相关对象
        self.qt_app = qt_app
        self.main_window = MainWindow(self.args,env=None) if self.render_mode else None

        if self.render_mode:
            self.timer = QTimer()
            self.timer.timeout.connect(self._qt_update)
            self.timer.start(1)  # 1 FPS

        self.qt_key_map = {
            'up': Qt.Key_Up,
            'right': Qt.Key_Right,
            'down': Qt.Key_Down,
            'left': Qt.Key_Left,
        }
        self.qt_key_map_reverse = {v: k for k, v in self.qt_key_map.items()}

        # 动作空间定义 (3个动作)
        self.action_space = [0, 1, 2]  # 前，左，右
        # 不同方向下的3个动作映射
        self.action_map = {
            'up': {0:'up',1:'left',2:'right'},
            'right': {0:'right',1:'up',2:'down'},
            'down': {0:'down',1:'right',2:'left'},
            'left': {0:'left',1:'down',2:'up'},
        }

        # 初始化游戏对象
        self.init_data()

    def init_data(self,game_config=None):
        if game_config is None:
            game_config = {1:{'player':'AI-DQN1'}, 2:{'player':'AI-DQN2'}}
        self.value_map = {}
        locs = np_choice([0,1,2,3,4],size=2,replace=False)
        for number in [1,2]:
            player = game_config[number].get('player')
            self.value_map[number] = {
                'snake': Snake(self.args,number=number,loc=locs[number-1]), 
                'score': 1,'head_deque': deque(maxlen=self.max_score+1), # 保存最近self.max_score+1步蛇头坐标，用于检测转圈
                'steps': 0, 'didn_eat_steps': 0, 'max_steps': self.each_score_steps,
                'reward': 0,'done': False,'key_pressed': None,'step_info':{},
                'bfs_move':0,'easter_egg':None,'start_time':datetime.now(),
                'victory': False,
            }
            if self.value_map[number]['snake'].direction == 'none' and player in ['AI-DQN1','AI-DQN2','Rule-BFS']:
                self.value_map[number]['snake'].changeDirection(np_choice([Qt.Key_Up, Qt.Key_Right, Qt.Key_Down, Qt.Key_Left]))
            self.value_map[number]['head_deque'].append(self.value_map[number]['snake'].body[0])
            self.value_map[number]['path_to_tail'] = 1
            self.value_map[number]['path_to_food'] = 1

            self.value_map[number].update(game_config[number])
            if player is None:
                self.value_map[number]['snake'].body = []
                self.value_map[number]['done'] = True
                self.value_map[number]['head_deque'].clear()

        self.food = Food(self.args)
        self.food.respawn([self.value_map[i]['snake'] for i in [1,2] if not self.value_map[i]['done']])
        self._find_min_foods_and_old_heads()

    def reset(self, game_config=None):
        """重置环境，返回初始状态"""
        self.init_data(game_config)

        if self.render_mode:
            window_size = self.main_window.geometry()        # 获取窗口尺寸
            x = (self.args.screen_width - window_size.width()) // 2
            y = (self.args.screen_height - window_size.height()) // 8
            self.main_window.move(x, y)
            self.main_window.show()
            self.main_window.game_widget.value_map = self.value_map
            self.main_window.game_widget.food = self.food
            self.main_window.left_info.chat_lines.clear()
            self.main_window.left_info.append_flag = True
            self.main_window.right_info.chat_lines.clear()
            self.main_window.right_info.append_flag = True
            self._qt_update()

        return [self._get_state(number) for number in [1,2]]

    def _qt_update(self):
        """Qt事件循环更新"""
        self.qt_app.processEvents()
        self.main_window.game_widget.scoreUpdated.emit(self.value_map)  # 发射信号
        self.main_window.game_widget.update()

    def close(self):
        """关闭渲染窗口"""
        if self.render_mode:
            self.main_window.close()

    def _body_to_foods(self, number):
        for segment in self.value_map[number]['snake'].body:
            if (0 <= segment[0] < self.args.grid_width and 
                0 <= segment[1] < self.args.grid_height) and \
                (segment not in self.food.foods) and \
                (segment not in self.value_map[{1:2,2:1}[number]]['snake'].body):
                self.food.foods.append(segment)
        self.value_map[number]['snake'].body = []  # 清空蛇身

    def _update_step_info(self, number, info):
        step = self.value_map[number]['steps']
        if step not in self.value_map[number]['step_info']:
            self.value_map[number]['step_info'][step] = info
        else:
            self.value_map[number]['step_info'][step].update(info)

    def step(self, actions, is_play=False):
        rewards = [0,0]

        # 处理转向动作并移动蛇
        for number in [1,2]:
            if self.value_map[number]['done'] or actions[number-1] is None:
                continue

            # 转换动作到Qt键值
            if actions[number-1] in self.qt_key_map_reverse:
                key = actions[number-1]
            else:
                key = self.qt_key_map[self.action_map[self.value_map[number]['snake'].direction][actions[number-1]]]
            self.value_map[number]['snake'].changeDirection(key)

            # 移动蛇
            self.value_map[number]['snake'].move()
            self.value_map[number]['steps'] += 1
            self.value_map[number]['head_deque'].append(self.value_map[number]['snake'].body[0])

            # 判断撞自身或撞墙
            if self.value_map[number]['snake'].isOutOfBounds():
                rewards[number-1] = -20
                self.value_map[number]['done'] = True
                self.value_map[number]['end_time'] = datetime.now()
                self._update_step_info(number,{'撞墙':-20,'done':True})
            elif self.value_map[number]['snake'].isCollidingWithSelf():
                rewards[number-1] = -30
                self.value_map[number]['done'] = True
                self.value_map[number]['end_time'] = datetime.now()
                self._update_step_info(number,{'撞自身':-30,'done':True})

        # 如果两条蛇都还活着，并且如果头部发生了位置交换，则视为头对头碰撞
        if not any([self.value_map[i]['done'] for i in [1,2]]):
            if (self.value_map[1]['snake'].body[0] == self.old_heads[1] and self.value_map[2]['snake'].body[0] == self.old_heads[0]):
                len1 = len(self.value_map[1]['snake'].body)
                len2 = len(self.value_map[2]['snake'].body)
                if len1 > len2:
                    rewards[1] = -40
                    self.value_map[2]['done'] = True
                    self.value_map[2]['end_time'] = datetime.now()
                    self._update_step_info(2,{'位置交换头撞头':-40,'done':True})
                elif len2 > len1:
                    rewards[0] = -40
                    self.value_map[1]['done'] = True
                    self.value_map[1]['end_time'] = datetime.now()
                    self._update_step_info(1,{'位置交换头撞头':-40,'done':True})
                else:  # 长度相同
                    rewards[0] = -40
                    rewards[1] = -40
                    self.value_map[1]['done'] = True
                    self.value_map[1]['end_time'] = datetime.now()
                    self.value_map[2]['done'] = True
                    self.value_map[2]['end_time'] = datetime.now()
                    self._update_step_info(1,{'位置交换头撞头':-40,'done':True})
                    self._update_step_info(2,{'位置交换头撞头':-40,'done':True})

        # 如果两条蛇都还活着，判断对撞
        if not any([self.value_map[i]['done'] for i in [1,2]]):
            collision = self.value_map[1]['snake'].isCollidingWithOther(self.value_map[2]['snake'])
            # 碰撞类型解析 [1撞2身, 2撞1身, 头对头]
            if any(collision):
                if collision[0]:  # 1头撞2身
                    rewards[0] = -30
                    self.value_map[1]['done'] = True
                    self.value_map[1]['end_time'] = datetime.now()
                    self._update_step_info(1,{'撞对方身体':-30,'done':True})
                if collision[1]:  # 2头撞1身 
                    rewards[1] = -30
                    self.value_map[2]['done'] = True
                    self.value_map[2]['end_time'] = datetime.now()
                    self._update_step_info(2,{'撞对方身体':-30,'done':True})
                if collision[2]:  # 头对头
                    len1 = len(self.value_map[1]['snake'].body)
                    len2 = len(self.value_map[2]['snake'].body)
                    if len1 > len2:
                        rewards[1] = -40
                        self.value_map[2]['done'] = True
                        self.value_map[2]['end_time'] = datetime.now()
                        self._update_step_info(2,{'位置相同头撞头':-40,'done':True})
                    elif len2 > len1:
                        rewards[0] = -40
                        self.value_map[1]['done'] = True
                        self.value_map[1]['end_time'] = datetime.now()
                        self._update_step_info(1,{'位置相同头撞头':-40,'done':True})
                    else:  # 长度相同
                        rewards[0] = -40
                        rewards[1] = -40
                        self.value_map[1]['done'] = True
                        self.value_map[1]['end_time'] = datetime.now()
                        self.value_map[2]['done'] = True
                        self.value_map[2]['end_time'] = datetime.now()
                        self._update_step_info(1,{'位置相同头撞头':-40,'done':True})
                        self._update_step_info(2,{'位置相同头撞头':-40,'done':True})

        # 检测是否吃到食物
        eat_foods = [False,False]
        snake_lens = [0,0]
        for number in [1,2]:
            if self.value_map[number]['done']:
                continue

            snake_lens[number-1] = len(self.value_map[number]['snake'].body) # 吃食物前的长度
            for food in self.food.foods[:]:  # 使用切片复制列表以避免修改时迭代
                if self.value_map[number]['snake'].isCollidingWithFood(food):
                    if self.value_map[number]['easter_egg'] is None: # 彩蛋模式不grow
                        self.value_map[number]['snake'].grow()
                    self.food.remove(food)
                    eat_foods[number-1] = True
                    self.value_map[number]['head_deque'].clear()
                    self.value_map[number]['didn_eat_steps'] = 0
                    break
            else:
                # 记录多少步没有吃到食物了
                if actions[number-1] is not None:
                    self.value_map[number]['didn_eat_steps'] += 1

            # 彩蛋模式无限步数
            if self.value_map[number]['easter_egg'] is not None:
                self.value_map[number]['didn_eat_steps'] = 0

            score = len(self.value_map[number]['snake'].body)
            self.value_map[number]['score'] = score
            self.value_map[number]['max_steps'] = min(score * self.each_score_steps,self.max_score * (5 if is_play else 2)) # 玩游戏时允许最多转五圈全图

            # 步数检测
            if self.value_map[number]['didn_eat_steps'] >= self.value_map[number]['max_steps']:
                rewards[number-1] = -20
                self.value_map[number]['done'] = True
                self.value_map[number]['end_time'] = datetime.now()
                self._update_step_info(number,{'食物获取超时':-20,'done':True})

        # 如果某条蛇死亡，将其身体变成食物，但只添加在游戏边界内且不在其他蛇的部分
        for number in [1,2]:
            if self.value_map[number]['done']:
                self._body_to_foods(number)

        # 补充食物
        if any(eat_foods):
            self.food.respawn([self.value_map[i]['snake'] for i in [1,2] if not self.value_map[i]['done']])

        # 计算奖励与惩罚
        for number in [1,2]:
            if self.value_map[number]['done']:
                continue

            eat_food = eat_foods[number-1]
            snake_len = snake_lens[number-1]
            if eat_food:
                rewards[number-1] += 15 + snake_len * 0.2  # 长蛇吃食物奖励更大
                self._update_step_info(number,{'吃到食物奖励':15 + snake_len * 0.2})
            elif actions[number-1] is not None:
                # 基础时间惩罚
                rewards[number-1] -= 0.05 * (1 + snake_len * 0.01)
                self._update_step_info(number,{'基础时间惩罚':-0.05 * (1 + snake_len * 0.01)})

                # 动态距离奖励与惩罚：根据靠近/远离食物的程度给予奖惩
                prev_dist = abs((np_array(self.min_foods[number-1]) - np_array(self.old_heads[number-1])).sum())
                current_dist = abs((np_array(self.min_foods[number-1]) - np_array(self.value_map[number]['snake'].body[0])).sum())
                current_norm_dist = np_norm(np_array(self.min_foods[number-1]) - np_array(self.value_map[number]['snake'].body[0]))
                distance_reward = (prev_dist - current_dist) / current_norm_dist
                rewards[number-1] += distance_reward
                if distance_reward > 0:
                    self._update_step_info(number,{'靠近食物奖励':distance_reward})
                else:
                    self._update_step_info(number,{'远离食物惩罚':distance_reward})

                # 转圈不惩罚，只是会让bfs接管走几步，试图跳出这个怪圈，且这个不在训练中使用，只在玩游戏时开启
                if is_play and len(self.value_map[number]['head_deque']) >= snake_len:
                    head_deque = list(self.value_map[number]['head_deque'])
                    snake_last = tuple(head_deque[-snake_len:])
                    others = head_deque[:-snake_len]
                    histories = list(zip(*[others[i:] for i in range(snake_len)]))
                    if snake_last in histories:
                        self.value_map[number]['bfs_move'] = max(np_randint(2,6),snake_len)
                        self.value_map[number]['head_deque'].clear()

            # 能否追到蛇尾奖励与惩罚（尝试抵消时间惩罚）
            if snake_len > 1 and actions[number-1] is not None:
                self.value_map[number]['path_to_tail'],_ = self._has_path_to_target(self.value_map[number]['snake'],self.value_map[{1:2,2:1}[number]]['snake'],target=self.value_map[number]['snake'].body[-1])
                if not self.value_map[number]['path_to_tail']:
                    r = 0.05 * (1 + snake_len * 0.01)
                    if eat_food:
                        # 如果吃了食物后追不到蛇尾了，那么取消之前10%的奖励
                        r += (15 + snake_len * 0.2) * 0.1
                    rewards[number-1] -= r
                    self._update_step_info(number,{'不能追到蛇尾惩罚':-r})
                else:
                    r = 0.05 * (1 + snake_len * 0.01)
                    if eat_food:
                        # 如果吃了食物后还能追到蛇尾，那么加多10%的奖励
                        r += (15 + snake_len * 0.2) * 0.1
                    rewards[number-1] += r
                    self._update_step_info(number,{'能追到蛇尾奖励':r})
        
        # 通关判定
        # 如果两条蛇都还活着，判断两条蛇加起来是否已经沾满了整个空间
        if not any([self.value_map[i]['done'] for i in [1,2]]):
            if sum([self.value_map[i]['score'] for i in [1,2]]) >= self.max_score:
                for number in [1,2]:
                    rewards[number-1] += 100
                    self.value_map[number]['done'] = True
                    self.value_map[number]['end_time'] = datetime.now()
                    self.value_map[number]['victory'] = True
                    self._update_step_info(number,{'通关游戏':100,'done':True,'victory':True})

        # 判断某一条蛇是否已经沾满了整个空间
        for number in [1,2]:
            if self.value_map[number]['done']:
                continue

            if self.value_map[number]['score'] >= self.max_score:
                rewards[number-1] += 100
                self.value_map[number]['done'] = True
                self.value_map[number]['end_time'] = datetime.now()
                self.value_map[number]['victory'] = True
                self._update_step_info(number,{'通关游戏':100,'done':True,'victory':True})

        for number in [1,2]:
            self.value_map[number]['reward'] += rewards[number-1]

        # 更新头部位置，及最近食物的位置
        if any([not self.value_map[i]['done'] for i in [1,2]]):
            self._find_min_foods_and_old_heads()

        if is_play:
            return self.value_map

        if self.render_mode:
            # 触发界面重绘
            self.main_window.game_widget.value_map = self.value_map
            self.main_window.game_widget.food = self.food
            self._qt_update()

        return [self._get_state(number) for number in [1,2]], rewards, self.value_map

    def _get_state(self,number):
        """获取当前状态表示"""
        if self.value_map[number]['done']:
            return np_ones(self.args.state_size) * -1

        snake = self.value_map[number]['snake']
        snake_len = len(snake.body)
        direction = snake.direction
        head = np_array(snake.body[0])

        another = self.value_map[{1:2,2:1}[number]]['snake']
        another_len = len(another.body)
        another_done = self.value_map[{1:2,2:1}[number]]['done']
        another_direction = another.direction
        another_possible_cells=[]
        is_big = 1
        if not another_done:
            is_big = int(snake_len > another_len)
            another_head = np_array(another.body[0])
            if another_direction == 'none':
                another_possible_cells=[(another_head+np_array(another.d_map[d])).tolist() for d in self.action_map.keys()]
            else:
                another_possible_cells=[(another_head+np_array(another.d_map[d])).tolist() for d in self.action_map[another_direction].values()]

        # 3个方向的真危险或可能发生的头撞头的危险
        dangers = [i for d in self.action_map[direction].values() for i in self._check_danger(snake.d_map[d],number,another_possible_cells,is_big)]

        # 运动方向
        dir_state = [
            int(direction == 'up'),
            int(direction == 'right'),
            int(direction == 'down'),
            int(direction == 'left')
        ]

        # 蛇身比例
        snake_rate = [snake_len / self.max_score]
        snake_rate_two = [(snake_len+another_len) / self.max_score]

        # 新增：食物相对坐标的归一化值
        food = np_array(self.min_foods[number-1])
        food_rel = (food - head) / np_array([self.args.grid_width, self.args.grid_height])
        
        # 食物相对方向
        food_dir = self._food_direction(snake,food)

        # 新增：蛇头到边界的距离
        left_dist = head[0] / self.args.grid_width
        right_dist = (self.args.grid_width - head[0]) / self.args.grid_width
        top_dist = head[1] / self.args.grid_height
        bottom_dist = (self.args.grid_height - head[1]) / self.args.grid_height
        four_dir_dist = [left_dist, right_dist, top_dist, bottom_dist]
        
        if another_done:
            # food_dir_another = [-1,-1,-1,-1]
            # dir_state_another = [-1,-1,-1,-1]
            snake_rate_another = [-1]
            # food_rel_another = np_array([-1,-1])
            head_each_other_rel = np_array([-1,-1])
            # four_dir_dist_another = [-1, -1, -1, -1]
        else:
            # food = np_array(self.min_foods[{1:2,2:1}[number]-1])
            # food_dir_another = self._food_direction(another,food)
            # dir_state_another = [
            #     int(another_direction == 'up'),
            #     int(another_direction == 'right'),
            #     int(another_direction == 'down'),
            #     int(another_direction == 'left')
            # ]
            snake_rate_another = [another_len / self.max_score]
            # food_rel_another = (food - another_head) / np_array([self.args.grid_width, self.args.grid_height])
            # 新增：与另一条蛇相对坐标的归一化值
            head_each_other_rel = (another_head - head) / np_array([self.args.grid_width, self.args.grid_height])
            # left_dist_another = another_head[0] / self.args.grid_width
            # right_dist_another = (self.args.grid_width - another_head[0]) / self.args.grid_width
            # top_dist_another = another_head[1] / self.args.grid_height
            # bottom_dist_another = (self.args.grid_height - another_head[1]) / self.args.grid_height
            # four_dir_dist_another = [left_dist_another, right_dist_another, top_dist_another, bottom_dist_another]

        # 新增特征：三个动作的可达格子数、及是否比蛇身大
        # with ThreadPoolExecutor(max_workers=3) as executor:
        #     futures = [executor.submit(self._calculate_reachable_cells, a, snake, another) for a in [0, 1, 2]]
        #     (forward_free,forward_big), (left_free,left_big), (right_free,right_big) = [f.result() for f in futures]

        # 新增特征：三个动作是否能追到蛇尾、及需要的步数
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self._calculate_path_to_tail, a, snake, another) for a in [0, 1, 2]]
            (forward_tail,forward_steps), (left_tail,left_steps), (right_tail,right_steps) = [f.result() for f in futures]

        # 找出最大步数到达蛇尾
        max_steps_to_tail = np_array([forward_steps,left_steps,right_steps])
        if max_steps_to_tail.sum() == -3:
            max_steps_to_tail=max_steps_to_tail.tolist()
        else:
            max_steps_to_tail=[(-1 if each == -1 else (1 if each == max_steps_to_tail.max() else 0)) for each in max_steps_to_tail]

        # self.value_map[number]['path_to_food'],_ = self._has_path_to_target(snake,another,target=self.min_foods[number-1])

        path_to_tail = self.value_map[number]['path_to_tail']
        # path_to_food = self.value_map[number]['path_to_food']
        didn_eat_steps_rate = self.value_map[number]['didn_eat_steps'] / self.value_map[number]['max_steps']

        state = np_array(
            [int(another_done)] +                       # 对手是否死亡 (1)
            [path_to_tail] +                            # 能否追到蛇尾 (1)
            # [path_to_food] +                            # 能否吃到苹果 (1)
            [didn_eat_steps_rate] +                     # 多久没吃苹果的步数比例 (1)
            # [forward_free, left_free, right_free] +     # 执行三个动作分别可达区域比例 (3)
            # [forward_big, left_big, right_big] +        # 执行三个动作分别可达区域是否比蛇身大 (3)
            [forward_tail, left_tail, right_tail] +     # 执行三个动作分别是否能追到蛇尾 (3)
            max_steps_to_tail +                         # 执行三个动作中最大步数追到蛇尾 (3)
            food_rel.tolist() +                         # 蛇头与最近苹果的相对坐标 (2)
            # food_rel_another.tolist() +                 # 对手蛇头与其最近苹果的相对坐标 (2)
            head_each_other_rel.tolist() +              # 与对手蛇头的相对坐标 (2)
            four_dir_dist +                             # 到四个边界的距离 (4)
            # four_dir_dist_another +                     # 对手到四个边界距离 (4)
            [is_big] +                                  # 蛇身是否比对手长 (1)
            dangers +                                   # 三个方向危险检测 (3)
            food_dir +                                  # 最近苹果相对蛇头的方向 (4)
            # food_dir_another +                          # 对手的最近苹果相对其蛇头的方向 (4)
            dir_state +                                 # 运动方向的独热编码 (4)
            # dir_state_another +                         # 对手运动方向的独热编码 (4)
            snake_rate +                                # 蛇身占整个空间的比例 (1)
            snake_rate_another +                        # 对手蛇身占整个空间的比例 (1)
            snake_rate_two,                             # 两条蛇占整个空间比例 (1)
            dtype=float32
        )

        return state

    def _find_min_foods_and_old_heads(self):
        old_heads = [None,None]
        min1_foods = [None,None] # 第一近食物
        min2_foods = [None,None] # 第二近食物
        for number in [1,2]:
            if self.value_map[number]['done'] or len(self.food.foods) == 0:
                continue
            old_heads[number-1] = self.value_map[number]['snake'].body[0]
            min1_foods[number-1] = min(self.food.foods, key=lambda f: abs(f[0] - old_heads[number-1][0]) + abs(f[1] - old_heads[number-1][1]))
            left_foods = [i for i in self.food.foods if i != min1_foods[number-1]]
            if len(left_foods) > 0:
                min2_foods[number-1] = min(left_foods, key=lambda f: abs(f[0] - old_heads[number-1][0]) + abs(f[1] - old_heads[number-1][1]))
        
        min_foods = [None,None] # 最有可能吃到的食物
        # 如果两条蛇都还活着，并且第一近食物相同，并且存在多个食物，则找出每条蛇最有可能吃到的食物，作为目标食物
        if not any([self.value_map[i]['done'] for i in [1,2]]) and min1_foods[0] == min1_foods[1] and len(self.food.foods) > 1:
            distance1 = abs(min1_foods[0][0] - old_heads[0][0]) + abs(min1_foods[0][1] - old_heads[0][1])
            distance2 = abs(min1_foods[1][0] - old_heads[1][0]) + abs(min1_foods[1][1] - old_heads[1][1])
            if distance1 < distance2:
                min_foods[0] = min1_foods[0]
                min_foods[1] = min2_foods[1]
            else:
                min_foods[0] = min2_foods[0]
                min_foods[1] = min1_foods[1]
        else:
            min_foods = min1_foods

        self.min_foods = min_foods
        self.old_heads = old_heads

    def _is_collision(self,test_pos,snake,another):
        return (
            test_pos[0] < 0 or
            test_pos[1] < 0 or
            test_pos[0] >= self.args.grid_width or
            test_pos[1] >= self.args.grid_height or
            test_pos.tolist() in snake.body[1:] or
            test_pos.tolist() in another.body
        )

    def _check_danger(self, direction, number, another_possible_cells=[], is_big=1, count=2):
        """检查指定方向是否有危险（1表示有危险）"""
        snake = self.value_map[number]['snake']
        another = self.value_map[{1:2,2:1}[number]]['snake']
        head = np_array(snake.body[0])
        dangers = []
        for i in range(1,count):
            test_pos = head + np_array(direction) * i
            # 真危险
            danger = int(self._is_collision(test_pos,snake,another))
            if danger == 0 and is_big == 0:
                # 短蛇或者长度相等的蛇都可能会有头撞头的危险
                danger = int(test_pos.tolist() in another_possible_cells) * 0.5
            dangers.append(danger)
        return dangers

    def _food_direction(self,snake,food):
        """获取最近食物相对方向（4维）"""
        head = np_array(snake.body[0])
        food = np_array(food)
        diff = food - head
        
        return [
            int(diff[1] < 0),  # 食物在上方
            int(diff[0] > 0),   # 食物在右侧
            int(diff[1] > 0),   # 食物在下方
            int(diff[0] < 0)    # 食物在左侧
        ]

    def _bfs_reachable_cells(self, start_pos, temp_body):
        # 转换为网格坐标
        start_grid = tuple(start_pos)
        visited = np_zeros((self.args.grid_width, self.args.grid_height), dtype=bool)
        queue = deque([start_grid])
        visited[start_grid[0]][start_grid[1]] = True

        # 预生成障碍物网格坐标
        obstacles = set(tuple(seg) for seg in temp_body)

        count = 1
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]

        while queue:
            x, y = queue.popleft()
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.args.grid_width and 0 <= ny < self.args.grid_height:
                    if not visited[nx][ny] and (nx, ny) not in obstacles:
                        visited[nx][ny] = True
                        queue.append((nx, ny))
                        count += 1
        return count

    def _calculate_reachable_cells(self, action, snake, another):
        v_snake = deepcopy(snake)
        original_direction = v_snake.direction
        key = self.qt_key_map[self.action_map[original_direction][action]]
        v_snake.changeDirection(key)
        v_snake.move()
        for food in self.food.foods:
            if v_snake.isCollidingWithFood(food):
                v_snake.grow()
                break

        new_head = np_array(v_snake.body[0])
        # 立即碰撞检测
        if self._is_collision(new_head,v_snake,another):
            return 0.0,0

        # 生成临时身体（避免深拷贝）
        temp_body = v_snake.body[:-1] + another.body[:-1]

        # 执行BFS
        reachable = self._bfs_reachable_cells(new_head, temp_body)
        free_space = (self.args.grid_width * self.args.grid_height) - len(temp_body)

        reachable_space = reachable / free_space if free_space > 0 else 0.0
        big_than_snake = int(reachable > len(v_snake.body))
        return reachable_space,big_than_snake

    def _calculate_path_to_tail(self,action, snake, another):
        v_snake = deepcopy(snake)
        original_direction = v_snake.direction
        key = self.qt_key_map[self.action_map[original_direction][action]]
        v_snake.changeDirection(key)
        v_snake.move()
        for food in self.food.foods:
            if v_snake.isCollidingWithFood(food):
                v_snake.grow()
                break

        # 立即碰撞检测
        if self._is_collision(np_array(v_snake.body[0]),v_snake,another):
            return 0, -1

        if len(v_snake.body) < 2:
            return 1, -1  # 单节蛇身不需要路径

        return self._has_path_to_target(v_snake,another,target=v_snake.body[-1])

    def _has_path_to_target(self,snake,another,target):
        """使用BFS判断蛇头是否能到达target"""
        # 转换坐标到网格系统
        head_grid = tuple(snake.body[0])
        target_grid = tuple(target)
        
        # 创建障碍物地图（排除尾部以及另一条蛇）
        obstacles = set()
        for seg in snake.body[:-1]+another.body[:-1]:
            grid = tuple(seg)
            obstacles.add(grid)
        
        # BFS初始化
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        queue = deque([(head_grid, 0)]) # (位置，步数)
        visited = set([tuple(head_grid)])
        
        while queue:
            (x, y),steps = queue.popleft()
            if (x, y) == target_grid:
                assert steps > 0
                return 1, steps
            
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                new_pos = (nx, ny)
                if (0 <= nx < self.args.grid_width and 
                    0 <= ny < self.args.grid_height and
                    new_pos not in visited and
                    new_pos not in obstacles):
                    visited.add(new_pos)
                    queue.append((new_pos, steps + 1))
        
        return 0, -1

class DuelingDQN(Module):
    def __init__(self, args):
        super().__init__()
        
        # 特征提取层
        self.feature = Sequential(
            Linear(args.state_size, args.hidden_size[0]),
            ReLU(),
            Dropout(args.dropout),

            Linear(args.hidden_size[0], args.hidden_size[1]),
            ReLU(),
            Dropout(args.dropout)
        )
        
        # 价值流
        self.value_stream = Sequential(
            Linear(args.hidden_size[1], args.hidden_size[2]),
            ReLU(),
            Dropout(args.dropout),
            Linear(args.hidden_size[2], 1)
        )
        
        # 优势流
        self.advantage_stream = Sequential(
            Linear(args.hidden_size[1], args.hidden_size[2]),
            ReLU(),
            Dropout(args.dropout),
            Linear(args.hidden_size[2], args.action_size)
        )
        
    def forward(self, x):
        features = self.feature(x)
        values = self.value_stream(features)
        advantages = self.advantage_stream(features)
        
        # 计算Q值
        qvals = values + (advantages - advantages.mean(dim=1, keepdim=True))
        return qvals

class SumTree:
    def __init__(self, capacity):
        self.capacity = capacity
        self.tree = np_zeros(2 * capacity - 1,dtype=float64)  # SumTree的节点数
        self.data = [None] * capacity  # 使用列表并初始化为None
        self.sample_count = np_zeros(capacity,dtype=int64)  # 采样计数器并初始化为0
        self.write = 0  # 当前写入位置
        self.size = 0  # 当前存储的经验数

    def _propagate(self, idx, change):
        """从叶子节点向上更新优先级总和"""
        parent = (idx - 1) // 2
        self.tree[parent] += change
        if parent != 0:
            self._propagate(parent, change)

    def _retrieve(self, idx, s):
        """根据采样值s找到对应的叶子节点索引"""
        left = 2 * idx + 1
        right = left + 1
        if left >= len(self.tree):
            return idx
        if s <= self.tree[left]:
            return self._retrieve(left, s)
        else:
            return self._retrieve(right, s - self.tree[left])

    def total(self):
        """返回总优先级"""
        return self.tree[0]

    def add(self, priority, data):
        """添加经验到SumTree"""
        idx = self.write + self.capacity - 1  # 叶子节点起始索引
        self.data[self.write] = data
        self.sample_count[self.write] = 0  # 初始化采样次数为0
        self.update(idx, priority)
        self.write = (self.write + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def update(self, idx, priority):
        """更新某个叶子节点的优先级"""
        change = priority - self.tree[idx]
        self.tree[idx] = priority
        self._propagate(idx, change)

    def get(self, s):
        """根据采样值s返回(叶子节点索引, 经验数据, 优先级)"""
        idx = self._retrieve(0, s)
        data_idx = idx - self.capacity + 1
        self.sample_count[data_idx] += 1  # 每次采样增加计数
        return (idx, self.data[data_idx], self.tree[idx])

class PrioritizedReplayBufferSumTree:
    def __init__(self, buffer_size, batch_size, alpha=0.6, decay_factor=0.1):
        self.buffer_size = buffer_size
        self.batch_size = batch_size
        self.alpha = alpha
        self.max_priority = 1.0  # 初始优先级
        self.decay_factor = decay_factor  # 采样频率衰减系数
        
        # 使用SumTree替代原有的优先级数组
        self.tree = SumTree(buffer_size)
        self.experience = namedtuple("Experience", ["state", "action", "reward", "next_state", "done"])

    def add(self, state, action, reward, next_state, done):
        """添加经验到SumTree"""
        e = self.experience(state, action, reward, next_state, done)
        priority = self.max_priority  # 新经验的初始优先级为当前最大优先级
        self.tree.add(priority**self.alpha, e)

    def sample(self, beta):
        """从SumTree中采样一批经验"""
        indices = []
        experiences = []
        weights = []
        priorities = []
        segment = self.tree.total() / self.batch_size

        for i in range(self.batch_size):
            a = segment * i
            b = segment * (i + 1)
            s = np_uniform(a, b)
            idx, exp, priority = self.tree.get(s)
            indices.append(idx)
            experiences.append(exp)
            priorities.append(priority)

        # 计算重要性采样权重
        total = self.tree.size
        sampling_prob = np_array(priorities) / self.tree.total()
        weights = (total * sampling_prob) ** (-beta)
        weights /= weights.max()  # 归一化

        # 转换为Tensor
        states = torch_tensor(
            np_array([e.state for e in experiences]), dtype=torch_float32)
        actions = torch_tensor(
            np_array([e.action for e in experiences]), dtype=torch_long)
        rewards = torch_tensor(
            np_array([e.reward for e in experiences]), dtype=torch_float32)
        next_states = torch_tensor(
            np_array([e.next_state for e in experiences]), dtype=torch_float32)
        dones = torch_tensor(
            np_array([e.done for e in experiences]), dtype=torch_float32)

        return (states, actions, rewards, next_states, dones, indices, weights)

    def update_priorities(self, indices, priorities):
        """更新优先级时加入采样频率惩罚"""
        for idx, priority in zip(indices, priorities):
            data_idx = idx - self.tree.capacity + 1
            # 计算衰减因子：采样次数越多，优先级衰减越大
            decay = np_exp(-self.tree.sample_count[data_idx] * self.decay_factor)
            adjusted_priority = (priority + 1e-5) * decay  # 防止优先级为零、应用衰减
            self.tree.update(idx, adjusted_priority**self.alpha)
            self.max_priority = max(self.max_priority, adjusted_priority)

    def save_buffer(self, filename):
        """保存 SumTree 完整状态"""
        np_savez(filename,
            tree=self.tree.tree,              # 保存完整的 SumTree 节点（含中间节点）
            data_states=np_array([exp.state for exp in self.tree.data[:self.tree.size]], dtype=float32),
            data_actions=np_array([exp.action for exp in self.tree.data[:self.tree.size]], dtype=int64),
            data_rewards=np_array([exp.reward for exp in self.tree.data[:self.tree.size]], dtype=float64),
            data_next_states=np_array([exp.next_state for exp in self.tree.data[:self.tree.size]], dtype=float32),
            data_dones=np_array([exp.done for exp in self.tree.data[:self.tree.size]], dtype=bool_),
            sample_count=self.tree.sample_count,  # 保存完整的sample_count数组
            write=np_array([self.tree.write], dtype=int64),      # 写入位置
            size=np_array([self.tree.size], dtype=int64),        # 当前存储量
            max_priority=np_array([self.max_priority], dtype=float64)  # 最大优先级
        )

    def load_buffer(self, filename):
        """加载 SumTree 完整状态"""
        data = np_load(filename, allow_pickle=True)
        
        # 重建 SumTree 结构
        self.tree.tree = data['tree'].copy()            # 恢复完整的树结构（含中间节点）
        self.tree.write = data['write'].item()          # 恢复写入位置
        self.tree.size = data['size'].item()            # 恢复当前存储量
        self.max_priority = data['max_priority'].item() # 恢复最大优先级

        # 恢复完整的sample_count数组
        self.tree.sample_count = data['sample_count'].copy()  # 直接转换为list
        
        # 重建经验数据
        batch_size = self.tree.size // 10  # 根据内存调整分块大小
        for start_idx in range(0, self.tree.size, batch_size):
            end_idx = min(start_idx + batch_size, self.tree.size)
            # 按块读取数据
            states_batch = data['data_states'][start_idx:end_idx]
            actions_batch = data['data_actions'][start_idx:end_idx]
            rewards_batch = data['data_rewards'][start_idx:end_idx]
            next_states_batch = data['data_next_states'][start_idx:end_idx]
            dones_batch = data['data_dones'][start_idx:end_idx]
            
            # 逐条处理当前块
            for i in range(len(states_batch)):
                exp = self.experience(
                    states_batch[i],
                    actions_batch[i],
                    rewards_batch[i],
                    next_states_batch[i],
                    dones_batch[i]
                )
                self.tree.data[start_idx + i] = exp
            
            # 释放当前块内存
            del states_batch, actions_batch, rewards_batch, next_states_batch, dones_batch
            gc_collect()

        del data
        gc_collect()

    def __len__(self):
        return self.tree.size

# DQN智能体
class DQNAgent:
    def __init__(self, args):
        self.args = args
        self.epsilon = self.args.epsilon
        self.device = self.args.device

        # 初始化网络
        self.policy_net = DuelingDQN(args).to(self.device)
        self.target_net = DuelingDQN(args).to(self.device)

        self.optimizer = Adam(self.policy_net.parameters(), lr=self.args.learning_rate)
        self.memory = PrioritizedReplayBufferSumTree(self.args.buffer_size, self.args.batch_size, self.args.per_alpha, self.args.decay_factor)  # 改用优先缓冲区
        self.beta = self.args.beta_start  # 重要性采样调整系数

        # 添加混合精度相关组件
        if self.args.use_amp:
            self.scaler = GradScaler('cuda',enabled=self.args.use_amp)  # 梯度缩放器
        else:
            self.scaler = None
        
    def act(self, state, epsilon=1.0):
        if random_random() > min(epsilon,self.epsilon):
            state = torch_tensor(state, dtype=torch_float32).unsqueeze(0).to(self.device)
            with no_grad():
                action_values = self.policy_net(state)
            return np_argmax(action_values.cpu().data.numpy())
        else:
            return random_choice(np_arange(self.args.action_size))

    def learn(self):
        if len(self.memory) < self.args.batch_size:
            return
        
        self.policy_net.train()
        self.target_net.train()

        # 采样时获取索引和权重
        states, actions, rewards, next_states, dones, indices, weights = self.memory.sample(self.beta)
        states = states.to(self.device)
        actions = actions.to(self.device)
        rewards = rewards.to(self.device)
        next_states = next_states.to(self.device)
        dones = dones.to(self.device)
        weights = torch_tensor(weights).to(self.device)

        # 使用自动混合精度上下文
        with autocast('cuda',enabled=self.args.use_amp):
            # 计算当前Q值和目标Q值
            Q_expected = self.policy_net(states).gather(1, actions.unsqueeze(1))
            Q_targets_next = self.target_net(next_states).detach().max(1)[0].unsqueeze(1)
            Q_targets = rewards.unsqueeze(1) + (self.args.gamma * Q_targets_next * (1 - dones.unsqueeze(1)))
            
            # 计算TD误差用于更新优先级
            td_errors = (Q_targets - Q_expected).detach().cpu().abs().numpy().flatten()
            self.memory.update_priorities(indices, td_errors)
            
            # 计算带权重的损失
            loss = (Q_expected - Q_targets.detach()).pow(2) * weights.unsqueeze(1)
            loss = loss.mean()
        
        # 优化网络
        self.optimizer.zero_grad()
        if self.args.use_amp:
            self.scaler.scale(loss).backward()
            clip_grad_norm_(self.policy_net.parameters(), 1.0)  # 梯度裁剪
            self.scaler.step(self.optimizer)
            self.scaler.update()
        else:
            loss.backward()
            clip_grad_norm_(self.policy_net.parameters(), 1.0)  # 梯度裁剪
            self.optimizer.step()
        
        # 更新目标网络
        self.soft_update()
        
        # 衰减探索率
        self.epsilon = max(self.args.epsilon_min, self.epsilon*self.args.epsilon_decay)

        # 衰减beta值（通常在训练过程中逐渐增加到1）
        self.beta = min(1.0, self.beta + self.args.beta_increment)

        self.policy_net.eval()
        self.target_net.eval()
    
    def soft_update(self):
        for target_param, policy_param in zip(self.target_net.parameters(), self.policy_net.parameters()):
            target_param.data.copy_(self.args.tau*policy_param.data + (1.0-self.args.tau)*target_param.data)

def save_training_state(number, args, episode, info_map, episode_info, save_path='checkpoints'):
    # 核心模型参数
    model_checkpoint = {
        'policy_net': info_map[number]['agent'].policy_net.state_dict(),
        'target_net': info_map[number]['agent'].target_net.state_dict(),
        'optimizer': info_map[number]['agent'].optimizer.state_dict(),
        'epsilon': info_map[number]['agent'].epsilon,
        'beta': info_map[number]['agent'].beta
    }
    if args.use_amp:
        model_checkpoint['scaler'] = info_map[number]['agent'].scaler.state_dict()
    torch_save(model_checkpoint, f"{save_path}/model_checkpoint_number{number}.pth")
    
    # 经验回放缓冲区（需扩展PrioritizedReplayBufferSumTree类）
    info_map[number]['agent'].memory.save_buffer(f"{save_path}/replay_buffer_number{number}.npz")
    
    # 训练进度
    info_map_copy = {}
    for k,v in info_map[number].items():
        if k != 'agent':
            if k == 'info':
                info_copy = {}
                for kk,vv in v.items():
                    if kk != 'snake':
                        info_copy[kk] = vv
                info_map_copy[k] = info_copy
            else:
                info_map_copy[k] = v
    torch_save({
        'current_episode': episode,
        'info_map': info_map_copy
    }, f"{save_path}/training_progress_number{number}.pth")

    if number == 1:
        # 随机数状态
        random_state = {
            'python': random_getstate(),
            'numpy': np_get_state(),
            'torch': get_rng_state(),
            'cuda': get_rng_state_all() if is_available() else None,
            'episode_info':episode_info
        }
        torch_save(random_state, f"{save_path}/random_states.pth")
        
        # 保存args超参数
        torch_save(args.__dict__, f"{save_path}/args_state.pth")

def load_training_state(load_path='checkpoints',use_best=False,use_map={1:1,2:2},load_memory=True,load_process=True):
    # 加载args超参数
    args = torch_load(f"{load_path}/args_state.pth",weights_only=False)
    if is_available():
        args['device']=torch_device("cuda")
        map_location=None
    else:
        args['device']=torch_device("cpu")
        map_location='cpu'
    args = Struct(**args)

    # 加载随机数状态
    random_state = torch_load(f"{load_path}/random_states.pth",weights_only=False,map_location=map_location)

    info_map = {}
    for number in [1,2]:
        # 加载模型参数
        agent = DQNAgent(args)
        checkpoint = torch_load(f"{load_path}/model_checkpoint_number{use_map[number]}.pth",weights_only=False,map_location=map_location)
        agent.policy_net.load_state_dict(checkpoint['policy_net'])
        if use_best:
            agent.policy_net.load_state_dict(torch_load(f'{load_path}/dqn_snake_{use_best}_number{use_map[number]}.pth',map_location=map_location,weights_only=False))
        agent.target_net.load_state_dict(checkpoint['target_net'])
        agent.optimizer.load_state_dict(checkpoint['optimizer'])
        if args.use_amp and 'scaler' in checkpoint:
            agent.scaler.load_state_dict(checkpoint['scaler'])
        agent.epsilon = checkpoint['epsilon']
        agent.beta = checkpoint['beta']
        
        if load_memory:
            # 加载经验回放缓冲区
            agent.memory.load_buffer(f"{load_path}/replay_buffer_number{use_map[number]}.npz")
        
        info_map[number] = {'agent': agent}
        if load_process:
            # 加载训练进度
            progress = torch_load(f"{load_path}/training_progress_number{use_map[number]}.pth",weights_only=False,map_location=map_location)
            info_map[number].update(progress)
            tmp_dict=info_map[number].pop('info_map')
            for col in ['current_episode', 'done', 'rewards', 'info']:
                if col in tmp_dict:
                    tmp_dict.pop(col)
            info_map[number].update(tmp_dict)

    return args,info_map,random_state