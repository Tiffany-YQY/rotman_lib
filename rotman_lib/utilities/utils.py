import os, sys
import pandas as pd



def initialise():
    sys.path.append(os.path.dirname(os.getcwd()))


def get_config_folder():
    tmp_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(tmp_path, "configs")
