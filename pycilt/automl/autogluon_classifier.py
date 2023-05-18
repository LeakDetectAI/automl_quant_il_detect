import logging

import numpy as np
import pandas as pd
from autogluon.tabular import TabularPredictor
from sklearn.utils import check_random_state

from pycilt.automl.automl_core import AutomlClassifier
from pycilt.automl.model_configurations import hyperparameters


class AutoGluonClassifier(AutomlClassifier):

    def __init__(self, n_features, n_classes, time_limit=1800, output_folder=None, eval_metric='accuracy',
                 use_hyperparameters=True, delete_tmp_folder_after_terminate=True, random_state=None):
        self.logger = logging.getLogger(name=AutoGluonClassifier.__name__)
        self.random_state = check_random_state(random_state)
        self.output_folder = output_folder
        self.delete_tmp_folder_after_terminate = delete_tmp_folder_after_terminate
        self.hyperparameter_tune_kwargs = {'scheduler': 'local', 'searcher': 'auto'}
        self.eval_metric = eval_metric
        self.use_hyperparameters = use_hyperparameters
        if self.use_hyperparameters:
            self.hyperparameters = hyperparameters
        else:
            self.hyperparameters = None
        self.auto_stack = True
        self.n_features = n_features
        self.n_classes = n_classes
        self.sample_weight = "auto_weight"
        self.time_limit = time_limit
        self.model = None
        self.class_label = 'class'
        self.columns = [f'feature_{i}' for i in range(self.n_features)] + [self.class_label]
        self.leaderboard = None

    def fit(self, X, y, **kwd):
        data = np.concatenate((X, y[:, None]), axis=1)
        if self.n_features != X.shape[-1]:
            raise ValueError(f"Dataset passed does not contain {self.n_features}")
        train_data = pd.DataFrame(data=data, columns=self.columns)
        self.model = TabularPredictor(label=self.class_label, sample_weight=self.sample_weight,
                                      eval_metric=self.eval_metric, path=self.output_folder)
        self.model.fit(train_data, time_limit=self.time_limit, hyperparameters=hyperparameters,
                       hyperparameter_tune_kwargs=self.hyperparameter_tune_kwargs, auto_stack=self.auto_stack)
        self.leaderboard = self.model.leaderboard(extra_info=True)
        if self.delete_tmp_folder_after_terminate:
            self.model.delete_models(models_to_keep='best', dry_run=False)
            self.model.save_space()
    def predict(self, X, verbose=0):
        test_data = self.convert_to_dataframe(X, None)
        y_pred = self.model.predict(test_data)
        return y_pred.values

    def score(self, X, y, sample_weight=None, verbose=0):
        test_data = self.convert_to_dataframe(X, y)
        score = self.model.evaluate(test_data)['balanced_accuracy']
        return score

    def predict_proba(self, X, verbose=0):
        test_data = self.convert_to_dataframe(X, None)
        y_pred = self.model.predict_proba(test_data)
        return y_pred.values

    def decision_function(self, X, verbose=0):
        test_data = self.convert_to_dataframe(X, None)
        y_pred = self.model.predict_proba(test_data)
        return y_pred.values

    def convert_to_dataframe(self, X, y):
        if y is None:
            n_instances = X.shape[0]
            y = self.random_state.choice(self.n_classes, size=n_instances)
        data = np.concatenate((X, y[:, None]), axis=1)
        if self.n_features != X.shape[-1]:
            raise ValueError(f"Dataset passed does not contain {self.n_features}")
        df_data = pd.DataFrame(data=data, columns=self.columns)
        return df_data

    def get_k_rank_model(self, k):
        self.leaderboard.sort_values(['score_val'], ascending=False, inplace=True)
        model_name = self.leaderboard.iloc[k - 1]['model']
        model = self.model._trainer.load_model(model_name)
        return model