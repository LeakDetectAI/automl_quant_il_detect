from .sklearn_classifier_leakage_detector import SklearnClassifierLeakageDetector
from ..contants import EXPECTED_MUTUAL_INFORMATION, GMM_MI_ESTIMATOR, MINE_MI_ESTIMATOR
from ..mi_estimators import GMMMIEstimator, MineMIEstimatorHPO


class MIEstimationLeakageDetector(SklearnClassifierLeakageDetector):
    def __int__(self, mi_technique, padding_name, learner_params, fit_params, hash_value, cv_iterations, n_hypothesis,
                base_directory, search_space, hp_iters, n_inner_folds, validation_loss, random_state=None, **kwargs):
        super().__int__(padding_name=padding_name, learner_params=learner_params, fit_params=fit_params,
                        hash_value=hash_value, cv_iterations=cv_iterations, n_hypothesis=n_hypothesis,
                        base_directory=base_directory, search_space=search_space, hp_iters=hp_iters,
                        n_inner_folds=n_inner_folds, validation_loss=validation_loss, random_state=random_state,
                        **kwargs)

        if mi_technique == MINE_MI_ESTIMATOR:
            self.base_detector = MineMIEstimatorHPO
            self.n_jobs = 1
        if mi_technique == GMM_MI_ESTIMATOR:
            self.base_detector = GMMMIEstimator
            self.n_jobs = 10

    def __initialize_objects__(self):
        for i in range(self.n_hypothesis):
            self.results[f'model_{i}'] = {}
            self.results[f'model_{i}'][EXPECTED_MUTUAL_INFORMATION] = []

    def perform_hyperparameter_optimization(self, X, y):
        return super().perform_hyperparameter_optimization(X, y)

    def fit(self, X, y):
        if self._is_fitted_:
            self.logger.info(f"Model already fitted for the padding {self.padding_name}")
        else:
            train_size = self.perform_hyperparameter_optimization(X, y)
            for k, (train_index, test_index) in enumerate(self.cv_iterator.split(X, y)):
                self.logger.info(f"************************************ Split {k} ************************************")
                train_index = train_index[:train_size]
                X_train, X_test = X[train_index], X[test_index]
                y_train, y_test = y[train_index], y[test_index]
                self.calculate_majority_voting_accuracy(X_train, y_train, X_test, y_test)
                for i, model in enumerate(self.estimators):
                    self.logger.info(f"************************************ Model {i} ************************************")
                    model.fit(X=X_train, y=y_train)
                    metric_loss = model.estimate_mi(X, y)
                    self.logger.info(f"Metric {EXPECTED_MUTUAL_INFORMATION}: Value {metric_loss}")
                    model_name = list(self.results.keys())[i]
                    self.results[model_name][EXPECTED_MUTUAL_INFORMATION].append(metric_loss)
            self.store_results()