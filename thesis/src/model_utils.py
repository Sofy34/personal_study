import numpy as np
from sklearn_crfsuite.utils import flatten
import pandas as pd
import defines
import random
from sklearn_crfsuite import scorers, CRF
from sklearn_crfsuite import metrics
from sklearn_crfsuite.metrics import flat_classification_report
import os





def get_info_on_pred(y_pred, y_pred_proba, y_test, groups_test):
    pred_df = pd.DataFrame()
    y_test_flat = flatten(y_test)
    y_pred_flat, pred_df = flatten_sequence(y_pred, groups_test, pred_df)
    y_pred_proba_flat = flatten(y_pred_proba)
    y_pred_proba_max = get_max_predicted_prob(y_pred_proba_flat)
    pred_df["label"] = y_test_flat
    pred_df["pred"] = y_pred_flat
    pred_df["pred_proba"] = y_pred_proba_max
    pred_df['correct'] = np.where( pred_df['label'] == pred_df['pred'] , 1, 0)
    err_df = get_sub_pred_db(pred_df, "label != pred")
    corr_df = get_sub_pred_db(pred_df, "label == pred")

    return pred_df,err_df, corr_df


def get_sub_pred_db(pred_df, query):
    sub_df = pred_df.query(query)
    sub_df = sub_df.sort_values(by="pred_proba", ascending=False)
    sub_df.reset_index(drop=True, inplace=True)
    return sub_df


def flatten_sequence(samples, groups_test, pred_df):
    for i, sample in enumerate(samples):
        for j, seq_item in enumerate(sample):
            idx = pred_df.shape[0]
            pred_df.loc[idx, "seq_idx"] = i
            pred_df.loc[idx, "idx_in_seq"] = j
            pred_df.loc[idx, "doc_idx"] = groups_test[i]
            pred_df.loc[idx, "seq_len"] = len(sample)
    y_pred_flat = flatten(samples)
    return y_pred_flat, pred_df


def get_max_predicted_prob(y_pred_proba_flat):
    return [max(sample.values()) for sample in (y_pred_proba_flat)]


def get_sample_info(X_test, _pred_df):
    """[summary]

    Args:
        X_test ([list of lists]): [Test samples: sequences of sentences]
        _pred_df ([DataFrame]): [predicted and actual labels]

    Returns:
        [DataFrame]: [extended dataframe with sample features]
    """
    pred_df = _pred_df.copy()
    for idx, row in _pred_df.iterrows():
        err_sent = X_test[int(row["seq_idx"])][int(row["idx_in_seq"])]
        for key in defines.SAMPLE_FEATURES:
            pred_df.loc[idx, key] = err_sent[key]
    return pred_df


def retrive_predicted_sent(dir_name,pred_df, groups_test, X_test):
    # """[summary]

    # Parameters
    # ----------
    # pred_df : [DataFrame]
    #     [predicted and tru label per sample with confidence score]
    # groups_test : [list of lists]
    #     [doc index for each item in sequences]
    # X_test : [list of list]
    #     [samples features]

    # Returns
    # -------
    # [DataFrame]
    #     [predicted df with addition of sentense info]
    # """
    sent_features = defines.SENT_FEATURES
    sent_features.extend(["text"])
    pred_df_data = pred_df.copy()
    test_docs = pred_df_data["doc_idx"].unique()
    for doc_idx in test_docs:
        doc_samples = pred_df.query("doc_idx == @doc_idx")
        sent_db = pd.read_csv(os.path.join(os.getcwd(),defines.PATH_TO_DFS,dir_name,"{:02d}_sent_db.csv".format(int(doc_idx))))
        for index, row in doc_samples.iterrows():
            err_sent = X_test[int(row["seq_idx"])][int(row["idx_in_seq"])]
            sent_info = sent_db.query(
                "par_idx_in_doc == @err_sent['par_idx_in_doc'] & sent_idx_in_par == @err_sent['sent_idx_in_par']"
            )
            if len(sent_info.index) != 1:
                print("ERROR! Got {} sentenses matching".format(len(sent_info.index)))
            for feature in sent_features:
                pred_df_data.loc[index, feature] = sent_info[feature].values
            pred_df_data.loc[index, "TOKEN"] = err_sent["TOKEN"]
        del sent_db
    return pred_df_data



def get_test_train_idx(docs_map,test_percent,seed=None):
    if not seed is None:
        random.seed(seed)
    doc_indices = set(docs_map.keys())
    doc_count = len(docs_map.keys())
    test_count = int(test_percent*doc_count)
    test_idx = set(random.sample(doc_indices, test_count))
    train_idx = doc_indices - test_idx
#     print("train {}\ntest {}".format(train_idx,test_idx))
    return train_idx,test_idx

def split_test_train_docs(docs_map,test_percent,seq_len,step,seed=None):
    train_idx,test_idx = get_test_train_idx(docs_map,test_percent,seed)
    X_train = []
    y_train = []
    X_test = []
    y_test = []
    groups_train = []
    groups_test = []
    for idx in train_idx:
        X_train.extend(docs_map[idx]['X_{}_{}'.format(seq_len,step)])
        y_train.extend(docs_map[idx]['y_{}_{}'.format(seq_len,step)])
        groups_train.extend([idx for i in range(len(docs_map[idx]['y_{}_{}'.format(seq_len,step)]))])
    for idx in test_idx:
        X_test.extend(docs_map[idx]['X_{}_{}'.format(seq_len,step)])
        y_test.extend(docs_map[idx]['y_{}_{}'.format(seq_len,step)])
        groups_test.extend([idx for i in range (len(docs_map[idx]['y_{}_{}'.format(seq_len,step)]))])
    return X_train,y_train,X_test,y_test,test_idx,groups_train,groups_test
    
    
def manual_groups_validate(docs_map,test_percent,seq_len,step,num_splits=10):
    score_list = []
    for i in range(num_splits):
        X_train,y_train,X_test,y_test,test_idx,groups_train,groups_test =  split_test_train_docs(docs_map,test_percent,seq_len,step)
        score_list.append(manual_get_prediction(X_train,y_train,X_test,y_test))
    return np.array(score_list)

def manual_get_prediction(X_train,y_train,X_test,y_test):
    crf = CRF(
    min_freq = 5,
    algorithm='lbfgs',
    c1=0.1,
    c2=0.1,
    max_iterations=100,
    all_possible_transitions=True,
    )
    crf.fit(X_train, y_train)
    y_pred  =  crf.predict(X_test)
    labels = list(crf.classes_)
    f1 = metrics.flat_f1_score(y_test, y_pred,average='weighted', labels=labels)
    recall = metrics.flat_recall_score(y_test, y_pred,average='weighted', labels=labels)
    precision = metrics.flat_precision_score(y_test, y_pred,average='weighted', labels=labels)
    return [f1,recall,precision]


