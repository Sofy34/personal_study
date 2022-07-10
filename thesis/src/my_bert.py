from sklearn.base import BaseEstimator, TransformerMixin
import torch.nn.functional as F
import random
import model_utils
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import transformers
from transformers import AutoModel, BertTokenizerFast
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from transformers import AdamW
import sys
sys.path.append('./src/')

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.utils.validation import check_X_y, check_array, check_is_fitted
from sklearn.utils.multiclass import unique_labels
from sklearn.metrics import euclidean_distances
import common_utils
from sklearn_crfsuite.utils import flatten

# specify GPU
# device = torch.device("cuda")


def train_test_split_doc(doc_indices, test_percent, random_state=42):
    doc_count = len(doc_indices)
    test_count = int(test_percent * doc_count)
    random.seed(random_state)
    test_docs = set(random.sample(doc_indices, test_count))
    train_docs = doc_indices - test_docs
    return train_docs, test_docs


def get_text_label_by_doc(df, doc_indices):
    if isinstance(df, pd.DataFrame):
        selected_docs = df[df['doc_idx'].isin(doc_indices)]
    return selected_docs['text'], selected_docs['is_nar']


def split_train_val_test(df):
    train_text, temp_text, train_labels, temp_labels = train_test_split(df['text'], df['is_nar'],
                                                                        random_state=2018,
                                                                        test_size=0.3,
                                                                        stratify=df['is_nar'])

    val_text, test_text, val_labels, test_labels = train_test_split(temp_text, temp_labels,
                                                                    random_state=2018,
                                                                    test_size=0.5,
                                                                    stratify=temp_labels)
    return train_text, train_labels, val_text, test_text, val_labels, test_labels


def split_train_val_test_per_doc(df):
    doc_indices = set(df['doc_idx'].unique())
    train_docs, temp_docs = train_test_split_doc(doc_indices, 0.3)
    train_text, train_labels = get_text_label_by_doc(df, train_docs)

    val_docs, test_docs = train_test_split_doc(temp_docs, 0.5)
    val_text,  val_labels = get_text_label_by_doc(df, val_docs)
    test_text, test_labels = get_text_label_by_doc(df, test_docs)
    return train_text, train_labels, val_text, test_text, val_labels, test_labels, test_docs


def get_test_tokens(my_tokenizer, test_text, my_max_len=30):
    if not isinstance(test_text,list):
        test_text = test_text.tolist()
    tokens_test = my_tokenizer.batch_encode_plus(
        test_text,
        max_length=my_max_len,
        pad_to_max_length=True,
        truncation=True
    )
    return tokens_test


def get_train_val_test_tokens(my_tokenizer, train_text, val_text, test_text, my_max_len=30):
    tokens_train = my_tokenizer.batch_encode_plus(
        train_text.tolist(),
        max_length=my_max_len,
        pad_to_max_length=True,
        truncation=True
    )

    # tokenize and encode sequences in the validation set
    tokens_val = my_tokenizer.batch_encode_plus(
        val_text.tolist(),
        max_length=my_max_len,
        pad_to_max_length=True,
        truncation=True
    )

    # tokenize and encode sequences in the test set
    tokens_test = my_tokenizer.batch_encode_plus(
        test_text.tolist(),
        max_length=my_max_len,
        pad_to_max_length=True,
        truncation=True
    )
    return tokens_train, tokens_val, tokens_test

# convert lists to tensors


def covert_token2tensor(tokens_train, train_labels, tokens_val, val_labels, tokens_test, test_labels):
    tensor_map = {}
    tensor_map['train'] = {}
    tensor_map['train']['seq'] = torch.tensor(tokens_train['input_ids'])
    tensor_map['train']['mask'] = torch.tensor(tokens_train['attention_mask'])
    # train_y = torch.tensor(train_labels.tolist())
    tensor_map['train']['y'] = torch.tensor(
        train_labels.tolist(), dtype=torch.long)

    tensor_map['val'] = {}
    tensor_map['val']['seq'] = torch.tensor(tokens_val['input_ids'])
    tensor_map['val']['mask'] = torch.tensor(tokens_val['attention_mask'])
    # val_y = torch.tensor(val_labels.tolist())
    tensor_map['val']['y'] = torch.tensor(
        val_labels.tolist(), dtype=torch.long)

    tensor_map['test'] = {}
    tensor_map['test']['seq'] = torch.tensor(tokens_test['input_ids'])
    tensor_map['test']['mask'] = torch.tensor(tokens_test['attention_mask'])
    # test_y = torch.tensor(test_labels.tolist())
    tensor_map['test']['y'] = torch.tensor(
        test_labels.tolist(), dtype=torch.long)
    return tensor_map


def convert_single_token2tensor(tokens_test):
    tensor_map = {}
    tensor_map['seq'] = torch.tensor(tokens_test['input_ids'])
    tensor_map['mask'] = torch.tensor(tokens_test['attention_mask'])
    return tensor_map

def convert_y_tokens2tensor(test_labels):
    if not isinstance(test_labels,list):
        test_labels=test_labels.tolist()
    return torch.tensor(test_labels, dtype=torch.long)

# freeze all the parameters


def freeze_model_params(pretrained):
    for param in pretrained.parameters():
        param.requires_grad = False
    return pretrained


def get_single_loader(tensor_map, batch_size=32):  # define a batch size

    # wrap tensors
    data = TensorDataset(
        tensor_map['seq'], tensor_map['mask'], tensor_map['y'])

    # sampler for sampling the data during training
    sampler = SequentialSampler(data)

    # dataLoader for train set
    dataloader = DataLoader(data, sampler=sampler, batch_size=batch_size)

    return dataloader


def get_data_loader(tensor_map, batch_size=32):  # define a batch size

    # wrap tensors
    train_data = TensorDataset(
        tensor_map['train']['seq'], tensor_map['train']['mask'], tensor_map['train']['y'])

    # sampler for sampling the data during training
    train_sampler = RandomSampler(train_data)

    # dataLoader for train set
    train_dataloader = DataLoader(
        train_data, sampler=train_sampler, batch_size=batch_size)

    # wrap tensors
    val_data = TensorDataset(
        tensor_map['val']['seq'], tensor_map['val']['mask'], tensor_map['val']['y'])

    # sampler for sampling the data during training
    val_sampler = SequentialSampler(val_data)

    # dataLoader for validation set
    val_dataloader = DataLoader(
        val_data, sampler=val_sampler, batch_size=batch_size)

    return train_dataloader, val_dataloader


def wrap_pretained_model(pretrained):
    # pass the pre-trained BERT to our define architecture
    return BERT_Arch(pretrained)


class BERT_Arch(nn.Module):

    def __init__(self, bert):

        super(BERT_Arch, self).__init__()

        self.bert = bert

        # dropout layer
        self.dropout = nn.Dropout(0.1)

        # relu activation function
        self.relu = nn.ReLU()

        # dense layer 1
        self.fc1 = nn.Linear(768, 512)

        # dense layer 2 (Output layer)
        self.fc2 = nn.Linear(512, 2)

        # softmax activation function
        self.softmax = nn.LogSoftmax(dim=1)

    # define the forward pass
    def forward(self, sent_id, mask):

        # pass the inputs to the model
        #       _, cls_hs = self.bert(sent_id, attention_mask=mask)
        _, cls_hs = self.bert(sent_id, attention_mask=mask, return_dict=False)

        x = self.fc1(cls_hs)

        x = self.relu(x)

        x = self.dropout(x)

        # output layer
        x = self.fc2(x)

        # apply softmax activation
        x = self.softmax(x)

        return x


def get_optimizer(wrapped_model):
    # define the optimizer
    optimizer = AdamW(wrapped_model.parameters(),
                      lr=1e-5)          # learning rat
    return optimizer


def get_cross_entropy(train_labels):
    class_weights = common_utils.get_class_weights(train_labels)
    print("Class Weights:", class_weights)
    # converting list of class weights to a tensor
    weights = torch.tensor(class_weights, dtype=torch.float)

    # push to GPU
    # weights = weights.to(device)

    # define the loss function
    cross_entropy = nn.NLLLoss(weight=weights)
    return cross_entropy


# function to train the model
def train(model, optimizer, train_dataloader, cross_entropy):

    model.train()

    total_loss, total_accuracy = 0, 0

    # empty list to save model predictions
    total_preds = []

    # iterate over batches
    for step, batch in enumerate(train_dataloader):

        # progress update after every 50 batches.
        if step % 50 == 0 and not step == 0:
            print("  Batch {:>5,}  of  {:>5,}.".format(
                step, len(train_dataloader)))

        # push the batch to gpu
        #     batch = [r.to(device) for r in batch]

        sent_id, mask, labels = batch

        # clear previously calculated gradients
        model.zero_grad()

        # get model predictions for the current batch
        preds = model(sent_id, mask)

        # compute the loss between actual and predicted values
        loss = cross_entropy(preds, labels)

        # add on to the total loss
        total_loss = total_loss + loss.item()

        # backward pass to calculate the gradients
        loss.backward()

        # clip the the gradients to 1.0. It helps in preventing the exploding gradient problem
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)

        # update parameters
        optimizer.step()

        # model predictions are stored on GPU. So, push it to CPU
        preds = preds.detach().cpu().numpy()

        # append the model predictions
        total_preds.append(preds)

    # compute the training loss of the epoch
    avg_loss = total_loss / len(train_dataloader)

    # predictions are in the form of (no. of batches, size of batch, no. of classes).
    # reshape the predictions in form of (number of samples, no. of classes)
    total_preds = np.concatenate(total_preds, axis=0)

    # returns the loss and predictions
    return avg_loss, total_preds


# function for evaluating the model
def evaluate(model, val_dataloader, cross_entropy):

    print("\nEvaluating...")

    # deactivate dropout layers
    model.eval()

    total_loss, total_accuracy = 0, 0

    # empty list to save the model predictions
    total_preds = []

    # iterate over batches
    for step, batch in enumerate(val_dataloader):

        # Progress update every 50 batches.
        #         if step % 50 == 0 and not step == 0:

        # Calculate elapsed time in minutes.
        #             elapsed = format_time(time.time() - t0)

        # Report progress.
        #       print('  Batch {:>5,}  of  {:>5,}.'.format(step, len(val_dataloader)))

        # push the batch to gpu
        #     batch = [t.to(device) for t in batch]

        sent_id, mask, labels = batch

        # deactivate autograd
        with torch.no_grad():

            # model predictions
            preds = model(sent_id, mask)

            # compute the validation loss between actual and predicted values
            loss = cross_entropy(preds, labels)

            total_loss = total_loss + loss.item()

            preds = preds.detach().cpu().numpy()

            total_preds.append(preds)

    # compute the validation loss of the epoch
    avg_loss = total_loss / len(val_dataloader)

    # reshape the predictions in form of (number of samples, no. of classes)
    total_preds = np.concatenate(total_preds, axis=0)

    return avg_loss, total_preds


def train_validate(model_name, model, optimizer, train_dataloader, val_dataloader, cross_entropy, epochs=10):
    # set initial loss to infinite

    best_valid_loss = float('inf')

    # empty lists to store training and validation loss of each epoch
    train_losses = []
    valid_losses = []

    best_dict = {}

    # for each epoch
    for epoch in range(epochs):

        print('\n Epoch {:} / {:}'.format(epoch + 1, epochs))

        # train model
        train_loss, _ = train(
            model, optimizer, train_dataloader, cross_entropy)

        # evaluate model
        valid_loss, _ = evaluate(model, val_dataloader, cross_entropy)

        # save the best model
        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss
            print("Saving best model {}".format(model_name))
            torch.save(model.state_dict(), model_name)
            best_dict = model.state_dict()

        # append training and validation loss
        train_losses.append(train_loss)
        valid_losses.append(valid_loss)

        print(f'\nTraining Loss: {train_loss:.3f}')
        print(f'Validation Loss: {valid_loss:.3f}')

    return best_dict


def load_saved_bert_model(model, path):
    model.load_state_dict(torch.load(path))
    model.eval()
    return model


def get_prediction(model, test_map):
    # get predictions for test data
    with torch.no_grad():
        preds = model(test_map['seq'], test_map['mask'])
        preds_np = preds.detach().cpu().numpy()
        preds_label = np.argmax(preds_np, axis=1)

        preds_proba = F.softmax(preds, dim=-1).detach().cpu().numpy()
    return preds_label, preds_proba


class BertTransformer(TransformerMixin, BaseEstimator):

    def __init__(self, tokenizer=None,param=None):
        self.tokenizer = tokenizer
        print('\n>>>>>>>init() called.\n')
        self.param = param

    
    def set_params(self, **parameters):
        for parameter, value in parameters.items():
            setattr(self, parameter, value)
        return self
    
    def fit(self, X, indices=None):
        print('\n>>>>>>>fit() called.\n')

        return self
    
  
    def fit_transform(self, X, y=None, **fit_params):
        return self.fit(X, **fit_params).transform(X=X)

    def transform(self, X, y=None):
        print('\n>>>>>>>transform() called.\n')
        X_= []
        indices=X.keys()
        X_tensor_map = {}
        for doc in indices:
            X_.extend(X[doc]["X_bert"])
        X_tokens = get_test_tokens(self.tokenizer, X_)
        X_tensor_map = convert_single_token2tensor(
            X_tokens)

        return X_tensor_map



class BertClassifier(ClassifierMixin, BaseEstimator):

    def __init__(self, pretrained_model=None):
        print('\n>>>>>>>init() called.\n')
        self._estimator_type = "classifier"
        self.pretrained_model = pretrained_model
        self.wrapped_model = wrap_pretained_model(self.pretrained_model)
        self.optimizer = get_optimizer(self.wrapped_model)

    def fit(self, X, y=None,batch_size=1024):
        print('>>>>>>> fit() called')
        y_= common_utils.convert_str_label_to_binary(flatten(y))
        X['y']=convert_y_tokens2tensor(y_)
        self.dataloader = get_single_loader(X,batch_size)
        self.cross_entropy = get_cross_entropy(np.asarray(y_))
        self.classes_ = np.unique(y)
        train(self.wrapped_model,
            self.optimizer,
            self.dataloader,
            self.cross_entropy)
        self.is_fitted_ = True
        return self
    
    def fit_transform(self, X, y=None):
        return self.fit(X=X,y=y)
    
    
    def set_params(self, **parameters):
        for parameter, value in parameters.items():
            setattr(self, parameter, value)
        return self
 
    def predict(self, X):
        check_is_fitted(self, 'is_fitted_')
        preds = self.wrapped_model(X['seq'], X['mask'])
        preds_np=preds.detach().cpu().numpy()
        preds_label=np.argmax(preds_np, axis=1)
        return common_utils.convert_binary_label_to_str(preds_label)


    def predict_proba(self, X):
        check_is_fitted(self, 'is_fitted_')
        preds=self.wrapped_model(X['seq'], X['mask'])
        preds_proba=F.softmax(preds, dim=-1).detach().cpu().numpy()
        return preds_proba
    
    def score(self, X, y, sample_weight=None):
        return common_utils.get_score(flatten(y), self.predict(X), labels=self.classes_)
    
    def set_params(self, **parameters):
        for parameter, value in parameters.items():
            setattr(self, parameter, value)
        return self
