import yaml
import os


def load_config():
    """
    config.yaml 파일을 읽어 설정을 로드
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.yaml')
        with open(config_path, "r") as file:
            config = yaml.safe_load(file)
        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}


config = load_config()
