import sys
from warnings import filterwarnings
filterwarnings('ignore')

from time import time
from os.path import dirname,abspath,join,exists
from traceback import format_exc as traceback_format_exc
from random import randint as random_randint
from zipfile import ZipFile as zipfile_ZipFile
from io import BytesIO as io_BytesIO
from pkgutil import get_data as pkgutil_get_data

from torch import load as torch_load, device as torch_device
from torch.cuda import is_available as torch_cuda_is_available
from PyQt5.QtWidgets import QApplication
from snake_ai import DQNAgent,SnakeEnv
from snake_game import MainWindow
from utils import seed_everything,Struct,get_rect_size

class EmbeddedResources:
    """处理嵌入在EXE中的资源文件"""
    @staticmethod
    def extract_models():
        """从EXE中提取模型文件到内存"""
        # 直接从 PyInstaller 的临时目录加载资源
        base_path = getattr(sys, '_MEIPASS', dirname(abspath(__file__)))
        resource_path = join(base_path, 'resources', 'models.zip')
        
        # 从内存加载资源（如果使用 PyInstaller 的 --add-data）
        if not exists(resource_path):
            try:
                # 尝试从内存加载
                data = pkgutil_get_data('resources', 'models.zip')
                if data:
                    return io_BytesIO(data)
            except ImportError:
                pass
            
            # 回退到相对路径
            resource_path = join(dirname(__file__), 'resources', 'models.zip')
        
        # 加载 ZIP 文件
        if exists(resource_path):
            with open(resource_path, 'rb') as f:
                zip_data = io_BytesIO(f.read())
            return zip_data
        
        # 最终回退：尝试从当前目录加载
        return open('models.zip', 'rb')

    @staticmethod
    def load_model(zip_data, file_path):
        """从 ZIP 文件加载模型"""
        with zipfile_ZipFile(zip_data) as zip_ref:
            if file_path in zip_ref.namelist():
                return io_BytesIO(zip_ref.read(file_path))
        return io_BytesIO()

def main():
    seed_everything(2025+random_randint(520,1314)+int(time())%5201314)
    
    try:
        # 从嵌入资源加载模型
        file_system = EmbeddedResources.extract_models()
        
        # 直接从内存加载训练状态
        args = Struct(**torch_load(EmbeddedResources.load_model(file_system, "args_state.pth")))
        if torch_cuda_is_available():
            args.device=torch_device("cuda")
            map_location=None
        else:
            try:
                from torch_directml import device as amd_device
            except:
                args.device=torch_device("cpu")
            else:
                args.device = amd_device()
            map_location='cpu'

        # 创建应用
        qt_app = QApplication([])
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        args.screen_width = screen_size.width()
        args.screen_height = screen_size.height()
        args.window_title = '贪吃2025蛇来运转'
        args.is_env = False
        args.grid_width = 50 # 默认大小
        args.grid_height = 40 # 默认大小
        args.info_width = int(args.screen_width * 0.25)
        args.dpi = screen.logicalDotsPerInch()
        args.rect_size = get_rect_size(args)

        # 加载DQN智能体（直接从内存加载）
        info_map = {}
        for number in [1, 2]:
            # 创建agent实例
            agent = DQNAgent(args)
            
            # 加载模型权重
            model_data = EmbeddedResources.load_model(file_system, f"dqn_snake_mean_max_score_number{number}.pth")
            agent.policy_net.load_state_dict(torch_load(model_data,weights_only=False,map_location=map_location))
            
            info_map[number] = {'agent': agent}
        
        env = SnakeEnv(args, qt_app=None)
        main_window = MainWindow(args, env=env, info_map=info_map)

        window_size = main_window.geometry()        # 获取窗口尺寸
        x = (args.screen_width - window_size.width()) // 2
        y = (args.screen_height - window_size.height()) // 8
        main_window.move(x, y)
        main_window.show()
        qt_app.exec_()
        qt_app.quit()
    
    except:
        with open("error.log", "w") as f:
            f.write(traceback_format_exc())

if __name__ == "__main__":
    main()