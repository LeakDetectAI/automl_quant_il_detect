import inspect
import logging
import multiprocessing
import os
import random
import re
import sys
from datetime import datetime, timedelta

import dill
import numpy as np
import openml
import sklearn
import tensorflow as tf
import torch
from keras import backend as K
from netcal.binning import IsotonicRegression, HistogramBinning
from netcal.scaling import LogisticCalibration, BetaCalibration, TemperatureScaling
from packaging import version
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, AdaBoostClassifier, \
    ExtraTreesClassifier
from sklearn.linear_model import RidgeClassifier, SGDClassifier
from sklearn.metrics import f1_score, accuracy_score, matthews_corrcoef, \
    mutual_info_score, balanced_accuracy_score
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier, ExtraTreeClassifier
from sklearn.utils import check_random_state
from skopt.space import Real, Categorical, Integer

from pycilt import *
from pycilt.contants import *
from pycilt.metrics import *

__all__ = ["datasets", "classifiers", "calibrators", "calibrator_params", "mi_estimators", "get_dataset_reader",
           "learners", "classification_metrics", "mi_estimation_metrics", "mi_metrics", "lp_metric_dict",
           "get_duration_seconds", "duration_till_now", "time_from_now", "get_dataset_reader", "seconds_to_time",
           "time_from_now", "create_search_space", "get_dataset_reader", "convert_learner_params",
           "create_directory_safely", "setup_logging", "setup_random_seed", "check_file_exists",
           "get_automl_learned_estimator"]

from pycilt.utils import log_exception_error

datasets = {SYNTHETIC_DATASET: SyntheticDatasetGenerator,
            SYNTHETIC_DISTANCE_DATASET: SyntheticDatasetGeneratorDistance,
            SYNTHETIC_IMBALANCED_DATASET: SyntheticDatasetGenerator,
            SYNTHETIC_DISTANCE_IMBALANCED_DATASET: SyntheticDatasetGeneratorDistance,
            OPENML_DATASET: OpenMLDatasetReader}
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
               AUTO_GLUON: AutoGluonClassifier,
               TABPNF: AutoTabPFNClassifier,
               }

calibrators = {ISOTONIC_REGRESSION: IsotonicRegression,
               PLATT_SCALING: LogisticCalibration,
               HISTOGRAM_BINNING: HistogramBinning,
               BETA_CALIBRATION: BetaCalibration,
               TEMPERATURE_SCALING: TemperatureScaling}
calibrator_params = {ISOTONIC_REGRESSION: {'detection': False, 'independent_probabilities': False},
                     PLATT_SCALING: {'temperature_only': False, 'method': 'mle'},
                     HISTOGRAM_BINNING: {'detection': False, 'independent_probabilities': False},
                     BETA_CALIBRATION: {'detection': False, 'independent_probabilities': False},
                     TEMPERATURE_SCALING: {'detection': False, 'independent_probabilities': False}}
mi_estimators = {GMM_MI_ESTIMATOR: GMMMIEstimator,
                 'gmm_mi_estimator_more_instances': GMMMIEstimator,
                 'gmm_mi_estimator_true': GMMMIEstimator,
                 'gmm_mi_estimator_more_instances_true': GMMMIEstimator,
                 MINE_MI_ESTIMATOR: MineMIEstimator,
                 'mine_mi_estimator_hpo': MineMIEstimatorHPO,
                 'softmax_mi_estimator': PCSoftmaxMIEstimator,
                 'pc_softmax_mi_estimator': PCSoftmaxMIEstimator}

leakage_detectors = {AUTO_GLUON: AutoGluonLeakageDetector,
                     TABPNF: TabPFNLeakageDetector,
                     MULTI_LAYER_PERCEPTRON: MLPLeakageDetector,
                     MINE_MI_ESTIMATOR: MIEstimationLeakageDetector,
                     GMM_MI_ESTIMATOR: MIEstimationLeakageDetector}

learners = {**classifiers, **mi_estimators, **leakage_detectors}

classification_metrics = {
    ACCURACY: accuracy_score,
    F_SCORE: f1_score,
    # AUC_SCORE: auc_score,
    MCC: matthews_corrcoef,
    # INFORMEDNESS: balanced_accuracy_score,
    ESTIMATED_MUTUAL_INFORMATION_SCORE: mutual_info_score,
    SANTHIUB: santhi_vardi_upper_bound,
    HELLMANUB: helmann_raviv_upper_bound,
    FANOSLB: fanos_lower_bound,
    FANOS_ADJUSTEDLB: fanos_adjusted_lower_bound
}
mi_estimation_metrics = {
    MCMC_MI_ESTIMATION: None,
    MCMC_LOG_LOSS: None,
    MCMC_PC_SOFTMAX: None,
    MCMC_SOFTMAX: None,
    MID_POINT_MI_ESTIMATION: mid_point_mi,
    LOG_LOSS_MI_ESTIMATION: log_loss_estimation,
    LOG_LOSS_MI_ESTIMATION_ISOTONIC_REGRESSION: log_loss_estimation,
    LOG_LOSS_MI_ESTIMATION_PLATT_SCALING: log_loss_estimation,
    LOG_LOSS_MI_ESTIMATION_BETA_CALIBRATION: log_loss_estimation,
    LOG_LOSS_MI_ESTIMATION_TEMPERATURE_SCALING: log_loss_estimation,
    LOG_LOSS_MI_ESTIMATION_HISTOGRAM_BINNING: log_loss_estimation,
    PC_SOFTMAX_MI_ESTIMATION: pc_softmax_estimation,
    PC_SOFTMAX_MI_ESTIMATION_ISOTONIC_REGRESSION: pc_softmax_estimation,
    PC_SOFTMAX_MI_ESTIMATION_PLATT_SCALING: pc_softmax_estimation,
    PC_SOFTMAX_MI_ESTIMATION_BETA_CALIBRATION: pc_softmax_estimation,
    PC_SOFTMAX_MI_ESTIMATION_TEMPERATURE_SCALING: pc_softmax_estimation,
    PC_SOFTMAX_MI_ESTIMATION_HISTOGRAM_BINNING: pc_softmax_estimation}
ild_metrics = {
    ACCURACY: accuracy_score,
    F_SCORE: f1_score,
    # AUC_SCORE: auc_score,
    MCC: matthews_corrcoef,
    INFORMEDNESS: balanced_accuracy_score,
    FPR: false_positive_rate,
    FNR: false_negative_rate
}
mi_metrics = {
    ESTIMATED_MUTUAL_INFORMATION: None,
    MCMC_MI_ESTIMATION: None,
    MCMC_LOG_LOSS: None,
    MCMC_PC_SOFTMAX: None,
    MCMC_SOFTMAX: None,
}
lp_metric_dict = {AUTO_ML: {**classification_metrics, **mi_estimation_metrics},
                  CLASSIFICATION: {**classification_metrics, **mi_estimation_metrics},
                  MUTUAL_INFORMATION: {**mi_metrics, **classification_metrics},
                  MUTUAL_INFORMATION_NEW: {**mi_metrics, **classification_metrics},
                  LEAKAGE_DETECTION: ild_metrics}


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


def create_search_space(hp_ranges, logger):
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
        logger.info(f"Before key {key} value {value}")
        if version.parse(sklearn.__version__) < version.parse("0.25.0"):
            if key == 'criterion' and 'squared_error' in value:
                value = ["friedman_mse", "mse"]
        if isint(value[0]) and isint(value[1]):
            search_space[key] = Integer(value[0], value[1])
        if isfloat(value[0]) and isfloat(value[1]):
            if len(value) == 3:
                search_space[key] = Real(value[0], value[1], prior=value[2])
        if (isbool(value[0]) and isbool(value[1])) or (isstr(value[0]) and isstr(value[1])):
            search_space[key] = Categorical(value)
        logger.info(f"key {key} value {value}")
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
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
    # logging.captureWarnings(True)


def setup_random_seed(random_state=1234):
    # logger.info('Seed value: {}'.format(seed))
    logger = logging.getLogger("Setup Logging")
    random_state = check_random_state(random_state)

    seed = random_state.randint(2 ** 31, dtype="uint32")
    torch.manual_seed(seed)
    logger.info(f"Total number of torch threads {torch.get_num_threads()}")
    if torch.get_num_threads() <= 2:
        n_cpus = 1
    else:
        n_cpus = torch.get_num_threads() - 2
        if "pc2" in os.environ["HOME"]:
            n_cpus = 4
    logger.info(f"Torch threads set {n_cpus}")

    torch.set_num_threads(n_cpus)
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
        config = tf.compat.v1.ConfigProto(
            intra_op_parallelism_threads=1,
            inter_op_parallelism_threads=1,
            allow_soft_placement=True,
            log_device_placement=False,
            device_count={"CPU": multiprocessing.cpu_count() - 2},
        )
    else:
        config = tf.compat.v1.ConfigProto(
            allow_soft_placement=True,
            log_device_placement=True,
            intra_op_parallelism_threads=2,
            inter_op_parallelism_threads=2,
        )
        config.gpu_options.allow_growth = True
    sess = tf.compat.v1.Session(config=config)
    K.set_session(sess)


def check_file_exists(file_path):
    file_path = os.path.normpath(file_path)
    if not os.path.exists(file_path):
        print("Error: provided file path '%s' does not exist!" % file_path)
        sys.exit(-1)
    return


def get_automl_learned_estimator(optimizers_file_path, logger):
    try:
        estimator = dill.load(open(optimizers_file_path, "rb"))
    except Exception as error:
        log_exception_error(logger, error)
        logger.error(f"No such file or directory: {optimizers_file_path}")
        estimator = None
    return estimator


def get_openml_datasets():
    YOUR_API_KEY = '2e5bf0586e06bc552a66c263cbdbd52f'
    USER_ID = "2086"
    openml.config.apikey = YOUR_API_KEY
    datasets = openml.datasets.list_datasets()
    openml_datasets = {}
    for dataset_id, dataset in datasets.items():
        # print(dataset)
        if dataset['uploader'] == USER_ID:
            # print(dataset['name'])
            openml_datasets[dataset_id] = {'name': dataset['name'], 'link': f"https://www.openml.org/d/{dataset_id}"}
    return openml_datasets
