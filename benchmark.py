import time
import argparse

import ml_dataset_loader.datasets as data_loader
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_squared_error, accuracy_score
from sklearn.model_selection import train_test_split


# Global parameters
random_seed = 0


class Data:
    def __init__(self, X, y, name, task, metric, train_size=0.6, validation_size=0.2,
                 test_size=0.2):
        assert (train_size + validation_size + test_size) == 1.0
        self.name = name
        self.task = task
        self.metric = metric
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(X, y,
                                                                                test_size=test_size,
                                                                                random_state=random_seed)

        self.X_train, self.X_val, self.y_train, self.y_val = train_test_split(self.X_train,
                                                                              self.y_train,
                                                                              test_size=validation_size / train_size,
                                                                              random_state=random_seed)

        assert (self.X_train.shape[0] + self.X_val.shape[0] + self.X_test.shape[0]) == X.shape[0]


def eval(data, pred):
    if data.metric == "RMSE":
        return np.sqrt(mean_squared_error(data.y_test, pred))
    elif data.metric == "Accuracy":
        # Threshold prediction if binary classification
        if data.task == "Classification":
            pred = pred > 0.5
        return accuracy_score(data.y_test, pred)
    else:
        raise ValueError("Unknown metric: " + data.metric)


def add_data(df, algorithm, data, elapsed, metric):
    time_col = (data.name, 'Time(s)')
    metric_col = (data.name, data.metric)
    try:
        df.insert(len(df.columns), time_col, float(0))
        df.insert(len(df.columns), metric_col, float(0))
    except:
        pass

    df.at[algorithm, time_col] = elapsed
    df.at[algorithm, metric_col] = metric


def configure_xgboost(data, params):
    params.update({'max_depth': 0, 'grow_policy': 'lossguide',
                   'max_leaves': 2 ** 6})
    if data.task == "Regression":
        params["objective"] = "reg:linear"
    elif data.task == "Multiclass classification":
        params["objective"] = "multi:softmax"
        params["num_class"] = np.max(data.y_test) + 1
    elif data.task == "Classification":
        params["objective"] = "binary:logistic"
    else:
        raise ValueError("Unknown task: " + data.task)


def run_xgboost(data, params, args):
    dtrain = xgb.DMatrix(data.X_train, data.y_train)
    dval = xgb.DMatrix(data.X_val, data.y_val)
    dtest = xgb.DMatrix(data.X_test, data.y_test)
    start = time.time()
    bst = xgb.train(params, dtrain, args.num_rounds, [(dtrain, "train"), (dval, "val")])
    elapsed = time.time() - start
    pred = bst.predict(dtest)
    metric = eval(data, pred)
    return elapsed, metric


def train_xgboost_cpu(data, df, args):
    params = {'tree_method': 'hist'}
    configure_xgboost(data, params)
    elapsed, metric = run_xgboost(data, params, args)
    add_data(df, 'xgb-cpu-hist', data, elapsed, metric)


def train_xgboost_gpu(data, df, args):
    params = {'tree_method': 'gpu_hist'}
    configure_xgboost(data, params)
    elapsed, metric = run_xgboost(data, params, args)
    add_data(df, 'xgb-gpu-hist', data, elapsed, metric)


class Experiment:
    def __init__(self, data_func, name, task, metric):
        self.data_func = data_func
        self.name = name
        self.task = task
        self.metric = metric

    def run(self, df, args):
        X, y = self.data_func(num_rows=args.rows)
        data = Data(X, y, self.name, self.task, self.metric)
        train_xgboost_cpu(data, df, args)
        train_xgboost_gpu(data, df, args)


experiments = [
    Experiment(data_loader.get_year, "YearPredictionMSD", "Regression", "RMSE"),
    Experiment(data_loader.get_synthetic_regression, "Synthetic", "Regression", "RMSE"),
    Experiment(data_loader.get_higgs, "Higgs", "Classification", "Accuracy"),
    Experiment(data_loader.get_cover_type, "Cover Type", "Multiclass classification", "Accuracy"),
    Experiment(data_loader.get_bosch, "Bosch", "Classification", "Accuracy"),
    Experiment(data_loader.get_airline, "Airline", "Classification", "Accuracy"),
]


def main():
    all_dataset_names = ''
    for exp in experiments:
        all_dataset_names+=exp.name + ','
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=None)
    parser.add_argument('--num_rounds', type=int, default=500)
    parser.add_argument('--datasets', default=all_dataset_names)
    args = parser.parse_args()
    df = pd.DataFrame()
    for exp in experiments:
        if exp.name in args.datasets:
            exp.run(df, args)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    print(df)
    filename = "table.txt"
    with open(filename, "w") as file:
        file.write(df.to_latex())
    print("Results written to: "+filename)

if __name__== "__main__":
  main()
