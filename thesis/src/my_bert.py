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
from sklearn.utils.class_weight import compute_class_weight

# specify GPU
# device = torch.device("cuda")
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

def get_train_val_test_tokens(my_tokenizer,train_text,val_text,test_text,my_max_len = 30):
    tokens_train = my_tokenizer.batch_encode_plus(
        train_text.tolist(),
        max_length = my_max_len,
        pad_to_max_length=True,
        truncation=True
    )

    # tokenize and encode sequences in the validation set
    tokens_val = my_tokenizer.batch_encode_plus(
        val_text.tolist(),
        max_length = my_max_len,
        pad_to_max_length=True,
        truncation=True
    )

    # tokenize and encode sequences in the test set
    tokens_test = my_tokenizer.batch_encode_plus(
        test_text.tolist(),
        max_length = my_max_len,
        pad_to_max_length=True,
        truncation=True
    )
    return tokens_train,tokens_val,tokens_test

## convert lists to tensors
def covert_token2tensor(tokens_train,train_labels,tokens_val,val_labels,tokens_test,test_labels):
    tensor_map = {}
    tensor_map['train'] = {}
    tensor_map['train']['seq'] = torch.tensor(tokens_train['input_ids'])
    tensor_map['train']['mask'] = torch.tensor(tokens_train['attention_mask'])
    # train_y = torch.tensor(train_labels.tolist())
    tensor_map['train']['y'] = torch.tensor(train_labels.tolist(),dtype=torch.long )

    tensor_map['val'] = {}
    tensor_map['val']['seq'] = torch.tensor(tokens_val['input_ids'])
    tensor_map['val']['mask'] = torch.tensor(tokens_val['attention_mask'])
    # val_y = torch.tensor(val_labels.tolist())
    tensor_map['val']['y'] = torch.tensor(val_labels.tolist(),dtype=torch.long )

    tensor_map['test'] = {}
    tensor_map['test']['seq'] = torch.tensor(tokens_test['input_ids'])
    tensor_map['test']['mask'] = torch.tensor(tokens_test['attention_mask'])
    # test_y = torch.tensor(test_labels.tolist())
    tensor_map['test']['y'] = torch.tensor(test_labels.tolist(),dtype=torch.long )
    return tensor_map

# freeze all the parameters
def freeze_model_params(pretrained):
    for param in pretrained.parameters():
        param.requires_grad = False
    return pretrained


def get_data_loader(tensor_map,batch_size = 32):    #define a batch size

    # wrap tensors
    train_data = TensorDataset(tensor_map['train']['seq'],tensor_map['train']['mask'], tensor_map['train']['y'])

    # sampler for sampling the data during training
    train_sampler = RandomSampler(train_data)

    # dataLoader for train set
    train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=batch_size)

    # wrap tensors
    val_data = TensorDataset(tensor_map['val']['seq'],tensor_map['val']['mask'], tensor_map['val']['y'])

    # sampler for sampling the data during training
    val_sampler = SequentialSampler(val_data)

    # dataLoader for validation set
    val_dataloader = DataLoader(val_data, sampler = val_sampler, batch_size=batch_size)
    
    return train_dataloader,val_dataloader


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
    self.relu =  nn.ReLU()

    # dense layer 1
    self.fc1 = nn.Linear(768,512)

    # dense layer 2 (Output layer)
    self.fc2 = nn.Linear(512,2)

    #softmax activation function
    self.softmax = nn.LogSoftmax(dim=1)

  #define the forward pass
  def forward(self, sent_id, mask):

    #pass the inputs to the model  
    #       _, cls_hs = self.bert(sent_id, attention_mask=mask)
    _, cls_hs = self.bert(sent_id, attention_mask=mask,return_dict=False)

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
                  lr = 1e-5)          # learning rat
    return optimizer

def get_cross_entropy(train_labels):
    class_weights = compute_class_weight('balanced', np.unique(train_labels), train_labels)
    print("Class Weights:",class_weights)
    # converting list of class weights to a tensor
    weights= torch.tensor(class_weights,dtype=torch.float)

    # push to GPU
    # weights = weights.to(device)

    # define the loss function
    cross_entropy  = nn.NLLLoss(weight=weights)
    return cross_entropy


# function to train the model
def train(model,optimizer,train_dataloader,cross_entropy):

    model.train()

    total_loss, total_accuracy = 0, 0

    # empty list to save model predictions
    total_preds = []

    # iterate over batches
    for step, batch in enumerate(train_dataloader):

        # progress update after every 50 batches.
        if step % 50 == 0 and not step == 0:
            print("  Batch {:>5,}  of  {:>5,}.".format(step, len(train_dataloader)))

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
def evaluate(model,val_dataloader,cross_entropy):

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

def train_validate(model_name,model,optimizer,train_dataloader,val_dataloader,cross_entropy,epochs=10):    
    # set initial loss to infinite
    
    best_valid_loss = float('inf')

    # empty lists to store training and validation loss of each epoch
    train_losses=[]
    valid_losses=[]

    #for each epoch
    for epoch in range(epochs):

        print('\n Epoch {:} / {:}'.format(epoch + 1, epochs))

        #train model
        train_loss, _ = train(model,optimizer,train_dataloader,cross_entropy)

        #evaluate model
        valid_loss, _ = evaluate(model,val_dataloader,cross_entropy)

        #save the best model
        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss
            print("Saving best model {}".format(model_name))
            torch.save(model.state_dict(),model_name)

        # append training and validation loss
        train_losses.append(train_loss)
        valid_losses.append(valid_loss)

        print(f'\nTraining Loss: {train_loss:.3f}')
        print(f'Validation Loss: {valid_loss:.3f}')


def load_saved_bert_model(model,path):
    model.load_state_dict(torch.load(path))
    model.eval()
    return model

def get_prediction(model,test_map):
    # get predictions for test data
    with torch.no_grad():
        preds = model(test_map['seq'], test_map['mask'])
        preds = preds.detach().cpu().numpy()
        preds = np.argmax(preds, axis = 1)
    return preds