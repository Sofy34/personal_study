import matplotlib.pyplot as plt

import seaborn as sns
from scipy.sparse import hstack, vstack
import classes
import pickle
import os
import pandas as pd
import glob
import defines
import numpy as np
from sklearn.metrics import f1_score, recall_score, average_precision_score, precision_recall_fscore_support
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import classification_report
import json
import feature_utils
from itertools import islice
from datetime import datetime
from scipy import sparse
import model_utils


def save_sparse(dir_name, file_name, sparse_matrix):
    path = os.path.join(os.path.join(
        os.getcwd(), defines.PATH_TO_DFS, dir_name, file_name))
    # print("saving sparse: {} of size ".format(os.path.basename(path)), sparse_matrix.get_shape())
    sparse.save_npz(path, sparse_matrix)


def open_sparse(path, file_name=''):
    if file_name:
        path_ = os.path.join(path, file_name)
    else:
        path_ = path
    sparse_matrix = sparse.load_npz(path_)
    # print("opening sparse: {} of size ".format(os.path.basename(path)), sparse_matrix.get_shape())
    return sparse_matrix


def get_doc_idx_from_name(file_name):
    base_name = os.path.basename(file_name)
    return int(base_name.split("_")[0])


def concat_dbs_by_idx(dir_name, db_name, indices, cols=[], index_name=""):
    df_list = []
    # print('concatinating {} for {} docs'.format(os.path.join(os.getcwd(), defines.PATH_TO_DFS,
    #                    dir_name, "*_{}.csv".format(db_name)),len(indices)))
    for idx in indices:
        df_list.append(os.path.join(os.getcwd(), defines.PATH_TO_DFS,
                       dir_name, "{:02d}_{}.csv".format(idx, db_name)))
    df_list.sort()
    df_map = {}
    for df in df_list:
        df_map[get_doc_idx_from_name(df)] = df
    if len(cols) > 0:
        db = pd.concat([pd.read_csv(i, usecols=cols)
                       for i in df_map.values()], keys=df_map.keys())
    else:
        db = pd.concat([pd.read_csv(i)
                       for i in df_map.values()], keys=df_map.keys())
    db.reset_index(inplace=True)
    new_idx_name = index_name if len(
        index_name) > 0 else "{}_idx".format(db_name.split('_')[0])
    db.rename(columns={'level_0': 'doc_idx',
              'level_1': new_idx_name}, inplace=True)
    return db


def concat_npz_by_idx(dir_name, split_idx, tf_type, doc_indices):
    df_list = []
    for idx in doc_indices:
        file = glob.glob(os.path.join(os.getcwd(), defines.PATH_TO_DFS,
                                      dir_name, "{:02d}_{}_tfidf_{}*".format(idx, split_idx, tf_type)))
        if file:
            df_list.append(file[0])
    df_list.sort()
    # print(df_list)
    npz_opened = [open_sparse(doc) for doc in df_list]
    db = vstack(npz_opened).tocsr()
    del npz_opened
    return db


def concat_dbs(dir_name, db_name, cols=[], index_name=""):
    df_list = glob.glob(os.path.join(os.path.join(
        os.getcwd(), defines.PATH_TO_DFS, dir_name, "*_{}.csv".format(db_name))))
    df_list.sort()
    df_map = {}
    for df in df_list:
        df_map[get_doc_idx_from_name(df)] = df
    if len(cols) > 0:
        db = pd.concat([pd.read_csv(i, usecols=cols)
                       for i in df_map.values()], keys=df_map.keys())
    else:
        db = pd.concat([pd.read_csv(i)
                       for i in df_map.values()], keys=df_map.keys())
    db.reset_index(inplace=True)
    new_idx_name = index_name if len(
        index_name) > 0 else "{}_idx".format(db_name.split('_')[0])
    if 'doc_idx' in db.columns:
        doc_idx_str = 'file_idx'
    else:
        doc_idx_str = 'doc_idx'
    db.rename(columns={'level_0': doc_idx_str,
              'level_1': new_idx_name}, inplace=True)
    return db


def convert_to_list(_dic):
    dic = {}
    for key, item in _dic.items():
        dic[key] = item.tolist()
    return dic


def convert_to_python_types(_dic):
    dic = {}
    if isinstance(_dic, dict):
        for key, val in _dic.items():
            if isinstance(val, dict):
                dic[key] = {}
                for subkey, subval in val.items():
                    dic[key][subkey] = convert_item_to_python_types(subval)
            else:
                dic[key] = convert_item_to_python_types(val)
    return dic


def convert_item_to_python_types(val):
    new_val = val
    if not isinstance(val, str):
        if isinstance(val, np.ndarray):
            new_val = val.tolist()
        else:
            new_val = val.item()
    return new_val


def get_random_sample(docs_map, seed=None):
    if not seed is None:
        random.seed(seed)
    doc_idx = np.random.randint(1, len(docs_map.keys())+1)
    if map_key_is_str(docs_map):
        doc_idx = str(doc_idx)
    if 'X' in docs_map[doc_idx]:
        key = 'X'
    else:
        key = 'X_3_3'
    seq_idx = np.random.randint(0, len(docs_map[doc_idx][key]))
    return docs_map[doc_idx][key][seq_idx]


def map_key_is_str(docs_map):
    return isinstance(list(docs_map.keys())[0], str)


def convert_str_keys_to_int(docs_map):
    return {int(k): v for k, v in docs_map.items()}


def get_score(y_true, y_pred, labels, sample_weight=None):
    output_dict = get_report(y_true, y_pred, labels, sample_weight)
    return output_dict['weighted avg']['f1-score']


def get_report(y_true, y_pred, labels, score_type='weighted avg', sample_weight=None, n_t=2, segeval=False):
    output_dict = classification_report(
        y_true=y_true,
        y_pred=y_pred,
        labels=labels,
        output_dict=True)
    if segeval:
        my_se = classes.MySegEval(n_t=n_t)
        output_dict['segeval'] = my_se.get_scores(y_true, y_pred)
        # tbd temporary remove statistic form report to shorten prints
        del output_dict['segeval']['b_stat']
    score = output_dict[score_type]['f1-score']
    return score, output_dict


def get_mean_score(dict_):
    scores = pd.DataFrame()
    for spl, v in dict_.items():
        df = pd.DataFrame(v)
        for l in df.columns[:2]:
            scores.loc[spl, 'recall_{}'.format(l)] = df.loc['recall', l]
            scores.loc[spl, 'f1_{}'.format(l)] = df.loc['f1-score', l]
            scores.loc[spl, 'precision_{}'.format(l)] = df.loc['precision', l]
        scores.loc[spl, 'weighted avg'] = df.loc['f1-score', 'weighted avg']
    scores.loc['mean'] = scores.mean()
    return scores


def get_df_scores_per_label(scores):
    for_plot = pd.DataFrame()
    for t in ['recall', 'precision', 'f1']:
        for l in ['0', '1']:
            idx = for_plot.shape[0]
            for_plot.loc[idx, 'metric'] = t
            for_plot.loc[idx, 'label'] = l
            for_plot.loc[idx, 'val'] = scores.loc['mean', '{}_{}'.format(t, l)]
    return for_plot


def plot_mean_scores(dict_):
    scores = get_mean_score(dict_)
    for_plot = get_df_scores_per_label(scores)
    ax = sns.barplot(x='metric', y='val', hue='label',
                     data=for_plot, errwidth=0)
    for container in ax.containers:
        ax.bar_label(container)

# gets a dataframe with colums
# f1_as.is	f1_usampl	prec_as.is	prec_usampl	recall_as.is	recall_usampl


def accumulate_compare(db):
    accumulate_db = pd.DataFrame()
    db_cols = db.columns
    db_metrics = set()
    db_kinds = set()
    for c in db_cols:
        spl = c.split('_')
        db_metrics.add(spl[0])
        db_kinds.add(spl[1])
    db_metrics, db_kinds
    for label in db.index:
        for metric in db_metrics:
            for kind in db_kinds:
                idx = accumulate_db.shape[0]
                accumulate_db.loc[idx, 'label'] = label
                accumulate_db.loc[idx, 'metric'] = metric
                accumulate_db.loc[idx, 'kind'] = kind
                accumulate_db.loc[idx, 'val'] = db.loc[label, metric+'_'+kind]
    return accumulate_db


def plot_accumulated_db(df):
    ax = {}
    for l in df.label.unique():
        plt.figure(figsize=(10, 6))
        ax[l] = sns.barplot(x='metric', y='val', hue='kind',
                            data=df[df['label'] == l], errwidth=0)
        for container in ax[l].containers:
            ax[l].bar_label(container)
        title = 'is_nar' if l == '1' else 'not_nar' if l == '0' else l
        ax[l].set_title(title)
        plt.legend(loc='lower center')
        plt.show()


def show_comparison(db):
    accum_db = accumulate_compare(db)
    plot_accumulated_db(accum_db)
    return accum_db


def get_class_weights(y):
    return compute_class_weight(
        class_weight='balanced', classes=np.unique(y), y=y)


def get_y_labels(docs_map, indices, seq_len=3, step=3):
    y_l = []

    for doc in indices:
        y_l.extend(docs_map[doc]["y_{}_{}".format(seq_len, step)])
    return y_l


def get_groups_labels(docs_map, indices, seq_len=3, step=3):
    groups = []
    for doc in indices:
        len_y = len(docs_map[doc]["y_{}_{}".format(seq_len, step)])
        groups.extend([doc for i in range(len_y)])
    return groups


def select_dic_keys(docs_map, keys):
    return {key: docs_map[key] for key in keys}


def convert_str_label_to_binary(y):
    if isinstance(y[0], str):
        return [0 if i == 'not_nar' else 1 for i in y]
    else:
        return y


def convert_binary_label_to_str(y):
    return ['not_nar' if i == 0 else 'is_nar' for i in y]


def get_x_y_by_index(docs_map, indices):
    return select_dic_keys(docs_map, indices), get_y_labels(docs_map, indices)


def get_x_y_group_by_index(docs_map, indices):
    X, y = get_x_y_by_index(docs_map, indices)
    return X, y, get_groups_labels(docs_map, indices)


def get_docs_map(dir_name, docs_map_name, per_par, seq_len, step):
    docs_map = read_docs_map(dir_name, docs_map_name)
    docs_map = convert_str_keys_to_int(docs_map)
    if not 'X_{}_{}'.format(seq_len, step) in docs_map[1]:
        feature_utils.reshape_docs_map_to_seq(docs_map, per_par, seq_len, step)
    add_sent_to_docs_map(dir_name, docs_map)
    return docs_map


def read_docs_map(dir_name, docs_map_name="docs_map.json"):
    doc_map_path = os.path.join(
        os.getcwd(), defines.PATH_TO_DFS, dir_name, docs_map_name)
    with open(doc_map_path, 'r') as fp:
        docs_map = json.load(fp)
    return docs_map


def add_sent_to_docs_map(dir_name, docs_map):
    for key in docs_map.keys():
        sent_db_path = os.path.join(os.path.join(
            os.getcwd(), defines.PATH_TO_DFS, dir_name, "{:02d}_sent_db.csv".format(int(key))))
        sent_db = pd.read_csv(sent_db_path, usecols=['text', 'is_nar'])
        docs_map[key]['X_bert'] = sent_db['text'].tolist()
        docs_map[key]['y_bert'] = sent_db['is_nar'].tolist()


def save_db(db, dir_name, file_name, keep_index=False,  float_format='%.5f'):
    path = os.path.join(os.getcwd(), defines.PATH_TO_DFS,
                        dir_name, "{}.csv".format(file_name))
    print("Saving {}, \nindex {}\nfloat_format {}".format(
        path, keep_index, float_format))
    db.to_csv(path, index=keep_index, float_format=float_format)


def load_db(dir_name, file_name, keep_index=False):
    path = os.path.join(os.getcwd(), defines.PATH_TO_DFS,
                        dir_name, "{}.csv".format(file_name))
    print("Opened {},  index {}".format(path, keep_index))
    return pd.read_csv(path)


def save_best_params(params, score, dir_name):
    now = datetime.now()
    dt_string = now.strftime("%d.%m_%H:%M")
    score_str = "{:.3f}".format(score).lstrip('0')
    file_name = "{}_{}_best_params.json".format(score_str, dt_string)
    save_json(params, dir_name, file_name)


def save_json(dic_, dir_name, file_name, convert=True, indent=4):
    if isinstance(dic_, dict):
        dic = dic_.copy()
        if convert:
            dic = convert_to_python_types(dic)
    else:
        dic = dic_
    path = os.path.join(os.getcwd(), defines.PATH_TO_DFS,
                        dir_name, "{}.json".format(file_name))
    print("Saving {}".format(path))
    with open(path, 'w') as fp:
        json.dump(dic, fp, ensure_ascii=False)  # ,indent=indent)


def write_html(df, path, name):
    html = df.to_html(escape=False, justify="center")
    html = r'<link rel="stylesheet" type="text/css" href="df_style.css" /><br>' + html
    # write html to file
    print_df_path = os.path.join(
        path, "{}.html".format(name)
    )
    text_file = open(print_df_path, "w")
    text_file.write(html)
    text_file.close()


def load_json(dir_name, file_name, convert=True):
    path = os.path.join(os.getcwd(), defines.PATH_TO_DFS,
                        dir_name, "{}.json".format(file_name))
    print("Opened {}".format(path))
    with open(path, 'r') as fp:
        read = json.load(fp)
    return read


def reshape_as_list(lst1, lst2):
    last = 0
    res = []
    for ele in lst1:
        res.append(lst2[last: last + len(ele)])
        last += len(ele)

    return res


def reshape_to_seq(input, seq_len, step):
    return [input[i:i+seq_len] for i in range(0, len(input), step)]


def dump_to_file(_object, dir_name, file_name):
    path = os.path.join(os.getcwd(), defines.PATH_TO_DFS, dir_name,
                        file_name+".p")
    file = open(path, 'wb')
    pickle.dump(_object, file)
    file.close()


def load_pickle(dir_name, file_name):
    path = os.path.join(os.getcwd(), defines.PATH_TO_DFS, dir_name,
                        file_name+".p")
    return pickle.load(open(path, "rb"))


def get_single_unique(group):
    if isinstance(group, list):
        return group[0]
    else:
        return group.unique()[0]


def get_single_hit(group, true_val=1):
    if isinstance(group, list):
        return (true_val in group)
    # else:
    #     return group.unique()[0]


def order_meta_features(_meta):
    meta = _meta.copy()
    meta['prefix'] = meta['attr'].astype(str).str[:3]
    meta.loc[meta['prefix'].str.contains(r"\-3", na=False), 'order'] = -3
    meta.loc[meta['prefix'].str.contains(r"\-2", na=False), 'order'] = 1
    meta.loc[meta['prefix'].str.contains(r"\-1", na=False), 'order'] = 2
    meta.loc[~meta['prefix'].str.contains(r"\+|\-", na=False), 'order'] = 3
    meta.loc[meta['prefix'].str.contains(r"\+1", na=False), 'order'] = 4
    meta.loc[meta['prefix'].str.contains(r"\+2", na=False), 'order'] = 5
    meta.loc[meta['prefix'].str.contains(r"\+3", na=False), 'order'] = 6
    meta.sort_values(by=['order', 'mean'], ascending=False, inplace=True)
    return meta
