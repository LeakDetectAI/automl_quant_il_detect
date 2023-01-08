import inspect
import logging
import multiprocessing
import os
import random
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import tensorflow as tf
import torch
from keras import backend as K
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, AdaBoostClassifier, \
    ExtraTreesClassifier
from sklearn.linear_model import RidgeClassifier, SGDClassifier
from sklearn.metrics import f1_score, accuracy_score, matthews_corrcoef, \
    mutual_info_score
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier, ExtraTreeClassifier
from sklearn.utils import check_random_state
from skopt.space import Real, Categorical, Integer
from tensorflow.core.protobuf.config_pb2 import ConfigProto
from tensorflow.python.client.session import Session

from experiments.contants import *
from pycilt.baseline import MajorityVoting
from pycilt.bayes_predictor import BayesPredictor
from pycilt.metrics import *
from pycilt.mi_estimators import MineMIEstimator, GMMMIEstimator, PCSoftmaxMIEstimator
from pycilt.multi_layer_perceptron import MultiLayerPerceptron
from pycilt.synthetic_data_generator import SyntheticDatasetGenerator
from autosklearn.experimental.askl2 import AutoSklearn2Classifier

__all__ = ["get_dataset_reader", "duration_till_now", "time_from_now", "get_dataset_reader", "create_search_space",
           "create_directory_safely", "setup_logging", "setup_random_seed", "check_file_exists"]

datasets = {
    SYNTHETIC_DATASET: SyntheticDatasetGenerator,
}
classifiers = {MULTI_LAYER_PERCEPTRON: MultiLayerPerceptron,
               SGD_CLASSIFIER: SGDClassifier,
               RIDGE_CLASSIFIER: RidgeClassifier,
               LINEAR_SVC: LinearSVC,
               DECISION_TREE: DecisionTreeClassifier,
               EXTRA_TREE: ExtraTreeClassifier,
               RANDOM_FOREST: RandomForestClassifier,
               EXTRA_TREES: ExtraTreesClassifier,
               ADA_BOOST_CLASSIFIER: AdaBoostClassifier,
               GRADIENT_BOOSTING_CLASSIFICATION: GradientBoostingClassifier,
               BAYES_PREDICTOR: BayesPredictor,
               MAJORITY_VOTING: MajorityVoting,
               AUTO_SKLEARN: AutoSklearn2Classifier
               }

mi_estimators = {'gmm_mi_estimator': GMMMIEstimator,
                 'mine_mi_estimator': MineMIEstimator,
                 'softmax_mi_estimator': PCSoftmaxMIEstimator,
                 'pc_softmax_mi_estimator': PCSoftmaxMIEstimator}
learners = {**classifiers, **mi_estimators}



classification_metrics = {
    ACCURACY: accuracy_score,
    F_SCORE: f1_score,
    #AUC_SCORE: auc_score,
    MCC: matthews_corrcoef,
    #INFORMEDNESS: instance_informedness,
    MISCORE: mutual_info_score,
    SANTHIUB: santhi_vardi_upper_bound,
    HELLMANUB: helmann_raviv_upper_bound,
    FANOSLB: fanos_lower_bound,
    FANOS_ADJUSTEDLB: fanos_adjusted_lower_bound
}
mi_metrics = {
    EMI: None,
}
lp_metric_dict = {CLASSIFICATION: classification_metrics, MUTUAL_INFORMATION: {**mi_metrics, **classification_metrics}}


def get_duration_seconds(duration):
    time = int(re.findall(r"\d+", duration)[0])
    d = duration.split(str(time))[1].upper()
    options = {"D": 24 * 60 * 60, "H": 60 * 60, "M": 60}
    return options[d] * time


def duration_till_now(start):
    return (datetime.now() - start).total_seconds()


def seconds_to_time(target_time_sec):
    return str(timedelta(seconds=target_time_sec))

def time_from_now(target_time_sec):
    base_datetime = datetime.now()
    delta = timedelta(seconds=target_time_sec)
    target_date = base_datetime + delta
    return target_date.strftime("%Y-%m-%d %H:%M:%S")


def get_dataset_reader(dataset_name, dataset_params):
    dataset_func = datasets[dataset_name]
    dataset_func = dataset_func(**dataset_params)
    return dataset_func


def create_search_space(hp_ranges):
    def isint(v):
        return type(v) is int

    def isfloat(v):
        return type(v) is float

    def isbool(v):
        return type(v) is bool

    def isstr(v):
        return type(v) is str

    search_space = {}
    for key, value in hp_ranges.items():
        print(key, value)
        if isint(value[0]) and isint(value[1]):
            search_space[key] = Integer(value[0], value[1])
        if isfloat(value[0]) and isfloat(value[1]):
            if len(value) == 3:
                search_space[key] = Real(value[0], value[1], prior=value[2])
        if (isbool(value[0]) and isbool(value[1])) or (isstr(value[0]) and isstr(value[1])):
            search_space[key] = Categorical(value)
    return search_space

def convert_learner_params(params):
    for key, value in params.items():
        if value == 'None':
            params[key] = None
    return params

def create_directory_safely(path, is_file_path=False):
    try:
        if is_file_path:
            path = os.path.dirname(path)
        if not os.path.exists(path):
            os.mkdir(path)
    except Exception as e:
        print(str(e))


def setup_logging(log_path=None, level=logging.INFO):
    """Function setup as many logging for the experiments"""
    if log_path is None:
        dirname = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        dirname = os.path.dirname(dirname)
        log_path = os.path.join(dirname, "logs", "logs.log")

    # log = logging.getLogger()  # root logger
    # for hdlr in log.handlers[:]:  # remove all old handlers
    #    log.removeHandler(hdlr)
    #
    # fileh = logging.FileHandler(log_path, 'a')
    # formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)-8s %(message)s')
    # fileh.setFormatter(formatter)
    # fileh.setLevel(level)
    # log.addHandler(fileh)
    # log.setLevel(level)
    logging.basicConfig(filename=log_path, level=level,
                        format='%(asctime)s %(name)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', force=True)
    logger = logging.getLogger("SetupLogging")  # root logger
    logger.info("log file path: {}".format(log_path))
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    logging.getLogger("tensorflow").setLevel(logging.ERROR)
    logging.getLogger("pytorch").setLevel(logging.ERROR)

    # logging.captureWarnings(True)


def setup_random_seed(random_state=1234):
    # logger.info('Seed value: {}'.format(seed))
    logger = logging.getLogger("Setup Logging")
    random_state = check_random_state(random_state)
    seed = random_state.randint(2 ** 31, dtype="uint32")
    os.environ['PYTHONHASHSEED'] = str(seed)

    seed = random_state.randint(2 ** 31, dtype="uint32")
    torch.manual_seed(seed)
    tf.random.set_seed(seed)

    seed = random_state.randint(2 ** 31, dtype="uint32")
    np.random.seed(seed)
    random.seed(seed)
    os.environ["KERAS_BACKEND"] = "tensorflow"
    devices = tf.config.experimental.list_physical_devices('GPU')
    logger.info("Devices {}".format(devices))
    n_gpus = len(devices)
    logger.info("Number of GPUS {}".format(n_gpus))
    if n_gpus == 0:
        config = ConfigProto(
            intra_op_parallelism_threads=1,
            inter_op_parallelism_threads=1,
            allow_soft_placement=True,
            log_device_placement=False,
            device_count={"CPU": multiprocessing.cpu_count() - 2},
        )
    else:
        config = ConfigProto(
            allow_soft_placement=True,
            log_device_placement=True,
            intra_op_parallelism_threads=2,
            inter_op_parallelism_threads=2,
        )
        config.gpu_options.allow_growth = True
    sess = Session(config=config)
    K.set_session(sess)


def check_file_exists(file_path):
    file_path = os.path.normpath(file_path)
    if not os.path.exists(file_path):
        print("Error: provided file path '%s' does not exist!" % file_path)
        sys.exit(-1)
    return
