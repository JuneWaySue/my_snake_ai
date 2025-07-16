import warnings
warnings.filterwarnings('ignore')
from snake_ai import SnakeEnv,load_training_state
from utils import seed_everything,get_rect_size,zip_files

import torch,random,time,os,argparse
from datetime import datetime
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import QApplication
from multiprocessing import Pool

def test(argv,play_name,play_map):
    seed_everything(2025)
    args,info_map,random_state=load_training_state(load_path=argv.load_path,use_best='mean_max_score',use_map={1:1,2:2},load_memory=False)
    random.setstate(random_state['python'])
    np.random.set_state(random_state['numpy'])
    torch.set_rng_state(random_state['torch'])
    if torch.cuda.is_available() and random_state['cuda'] is not None:
        torch.cuda.set_rng_state_all(random_state['cuda'])

    qt_app = QApplication([])
    screen = QApplication.primaryScreen()
    args.dpi = screen.logicalDotsPerInch()
    screen_size = screen.size()
    args.screen_width = screen_size.width()
    args.screen_height = screen_size.height()
    args.info_width = int(args.screen_width * 0.25)
    args.grid_width = argv.grid_width
    args.grid_height = argv.grid_height
    args.each_score_steps = argv.each_score_steps
    args.rect_size = get_rect_size(args)
    args.window_title = 'Snake AI Test'

    test_env = SnakeEnv(args, qt_app=qt_app)
    test_env.main_window.game_widget.env = test_env
    df_list = []
    for episode in range(0,argv.test_num):
        test_env.render_mode = argv.render_mode

        for number in [1, 2]:
            info_map[number]['done'] = False
            info_map[number]['rewards'] = 0
            info_map[number]['info'] = None

        states = test_env.reset(game_config=play_map)
        actions = [None,None]
        while not all([info_map[i]['done'] for i in [1,2]]):
            if not test_env.render_mode:
                test_env.main_window.game_widget.value_map = test_env.value_map
                test_env.main_window.game_widget.food = test_env.food
                test_env.main_window.left_info.chat_lines.clear()
                test_env.main_window.left_info.append_flag = True
                test_env.main_window.right_info.chat_lines.clear()
                test_env.main_window.right_info.append_flag = True
            for number in [1, 2]:
                if info_map[number]['done']:
                    continue
                if not play_map[number].get('player'):
                    continue
                elif play_map[number]['player'] == 'Rule-BFS':
                    actions[number-1] = test_env.main_window.game_widget.bfs_agent(number)
                else:
                    actions[number-1] = info_map[{'AI-DQN1':1,'AI-DQN2':2}[play_map[number]['player']]]['agent'].act(states[number-1],epsilon=0)
            next_states, rewards, info = test_env.step(actions)
            states = next_states

            for number in [1, 2]:
                if info_map[number]['done']:
                    continue
                info_map[number]['done'] = info[number]['done']
                info_map[number]['rewards'] += rewards[number-1]
                info_map[number]['info'] = info[number]
        test_env.close()

        df = []
        for number in [1, 2]:
            if not play_map[number].get('player'):
                continue
            df.append({
                'Agent':play_map[number]['player'],
                'Step':f"{info_map[number]['info']['steps']} [{info_map[number]['info']['didn_eat_steps']}/{info_map[number]['info']['max_steps']}]",
                'Score':info_map[number]['info']['score'],
                'Reward':info_map[number]['rewards'],
                'Speed':f"{(info_map[number]['info']['end_time']-info_map[number]['info']['start_time']).total_seconds() / info_map[number]['info']['steps']:.4f} s/step",
                'Reason':','.join([i for i in list(info_map[number]['info']['step_info'].items())[-1][1].keys() if i not in ['done','victory']])
            })

        df=pd.DataFrame(df)
        df_list.append(df.assign(episode=episode+1))
        print('-'*130)
        print(f"[Test {play_name}] Episode: {episode+1}/{argv.test_num} | DateTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"+
                df.to_string(float_format='%.1f',index=False))
    
    save_path=f'test/{args.grid_width}x{args.grid_height}'
    os.makedirs(save_path,exist_ok=True)
    pd.concat(df_list).to_pickle(f'{save_path}/{play_name}.pkl')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Snake AI Test')
    parser.add_argument('--test_num', type=int, default=100, help='对战局数')                                       # 100,100
    parser.add_argument('--grid_width', type=int, default=10, help='多少格子的宽度')                                 # 10,20
    parser.add_argument('--grid_height', type=int, default=10, help='多少格子的高度')                                # 10,20
    parser.add_argument('--each_score_steps', type=int, default=50, help='每多一分增加多少步可移动，上限为全图的两倍')  # 50,100
    parser.add_argument('--load_path', type=str, default='checkpoints', help='模型文件夹路径')
    parser.add_argument('--processe_num', type=int, default=os.cpu_count(), help='使用多少进程数量')
    parser.add_argument('--players', type=str, default='1,2,r,1vs2,1vsr,rvs2', help='对局设置')
    parser.add_argument('--render_mode', action="store_true", help='是否观看对局')
    parser.add_argument('--zip_result', action="store_true", help='是否压缩结果文件')
    argv = parser.parse_args()

    players_map={
        '1':'AI-DQN1 单机','2':'AI-DQN2 单机','r':'Rule-BFS 单机',
        '1vs2':'AI-DQN1 VS AI-DQN2','1vsr':'AI-DQN1 VS Rule-BFS','rvs2':'Rule-BFS VS AI-DQN2'
    }
    play_maps_fix={
        'AI-DQN1 单机':{1:{'player':'AI-DQN1'},2:{}},
        'AI-DQN2 单机':{1:{'player':'AI-DQN2'},2:{}},
        'Rule-BFS 单机':{1:{'player':'Rule-BFS'},2:{}},
        'AI-DQN1 VS AI-DQN2':{1:{'player':'AI-DQN1'},2:{'player':'AI-DQN2'}},
        'AI-DQN1 VS Rule-BFS':{1:{'player':'AI-DQN1'},2:{'player':'Rule-BFS'}},
        'Rule-BFS VS AI-DQN2':{1:{'player':'Rule-BFS'},2:{'player':'AI-DQN2'}}
    }
    play_maps={players_map[i]:play_maps_fix[players_map[i]] for i in argv.players.split(',')}

    start_time=time.time()
    with Pool(processes=min(argv.processe_num,len(play_maps))) as pool:
        pool.starmap(test, tuple([(argv,i,j) for i,j in play_maps.items()]))
    print(f'Total time: {time.time()-start_time:.2f} s')

    if argv.zip_result:
        save_path=f'test/{argv.grid_width}x{argv.grid_height}'
        zip_files([f'{save_path}/{i}' for i in os.listdir(save_path)],zip_name='pkl_data.zip')