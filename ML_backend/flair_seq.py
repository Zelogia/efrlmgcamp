import os
import json
import pandas as pd
import datetime
from difflib import SequenceMatcher
from typing import List
import torch
import flair.embeddings
import flair.models
from flair.trainers import ModelTrainer
from flair.data import Sentence, Corpus
from flair.datasets import ColumnCorpus
from sklearn.model_selection import train_test_split
from label_studio_ml.model import LabelStudioMLBase
import numpy as np
from torch.optim import Adam, AdamW
from flair.embeddings import TransformerWordEmbeddings
import logging
logging.basicConfig(level = logging.DEBUG)

if torch.cuda.is_available():
    print("CUDA")
    flair.device = torch.device('cuda') 
else:
    flair.device = torch.device('cpu') 

def load_data(data=None):
    """
    Load your labeled data exported using Label Studio in json-min format
    Convert the Label Studio JSON format to Spacy format so that
    the same can be fed into Spacy / Flair NER models
    """
#     with open(JSON_PATH, 'r') as j:
#         data = json.loads(j.read())
    TRAIN_DATA_formulaire = []
    for item in data:
#     for i in range(len(data)):
        text = item['data']['text']
        entities = []
#         if 'label' in data[i]:
#         print(data[i]['annotations'][0])
        for t in item['annotations'][0]['result']:
            if t['from_name']=='label': #ner only config part
                start = t['value']['start']
                end = t['value']['end']
                ent = t['value']['labels'][0]
                entities.append((start, end, ent))
        TRAIN_DATA_formulaire.append((text, {'entities': entities}))
    return TRAIN_DATA_formulaire

def create_df_from_data(TRAIN_DATA=None):
    """
    """
    TEXT = []
    ANNOTATION = []
    logging.info("TRAIN_DATA",TRAIN_DATA)
    for LINE_TRAIN_DATA in TRAIN_DATA:
        text = LINE_TRAIN_DATA[0]
        text_Annotation = []
        for entity in LINE_TRAIN_DATA[1]["entities"]:
            entity_text = text[entity[0]:entity[1]]
            entity_value = entity[2]
            text_Annotation.append((entity_text, entity_value))
        TEXT.append(text)
        ANNOTATION.append(text_Annotation)
    df = pd.DataFrame({'text': TEXT, 'annotation': ANNOTATION})

    return df

def matcher(string, pattern):
    '''
    Return the start and end index of any pattern present in the text.
    '''
    match_list = []
    pattern = pattern.strip()
    seqMatch = SequenceMatcher(None, string, pattern, autojunk=False)
    match = seqMatch.find_longest_match(0, len(string), 0, len(pattern))
    if (match.size == len(pattern)):
        start = match.a
        end = match.a + match.size
        match_tup = (start, end)
        string = string.replace(pattern, "X" * len(pattern), 1)
        match_list.append(match_tup)
    return match_list, string

def mark_sentence(s, match_list):
    '''
    Marks all the entities in the sentence as per the BIO scheme. 
    '''
    word_dict = {}
    for word in s.split():
        word_dict[word] = 'O'
    for start, end, e_type in match_list:
        temp_str = s[start:end]
        tmp_list = temp_str.split()
        if len(tmp_list) > 1:
            word_dict[tmp_list[0]] = 'B-' + e_type
            for w in tmp_list[1:]:
                word_dict[w] = 'I-' + e_type
        else:
            word_dict[temp_str] = 'B-' + e_type
    return word_dict


def create_data(df=None, filepath=None):
    '''
    The function responsible for the creation of data in the said format.
    '''
    with open(filepath, 'w') as f:
        for text, annotation in zip(df.text, df.annotation):
            text_ = text
            match_list = []
            for i in annotation:
                a, text_ = matcher(text, i[0])
                match_list.append((a[0][0], a[0][1], i[1]))
            d = mark_sentence(text, match_list)
            for i in d.keys():
                f.writelines(i + ' ' + d[i] + '\n')
            f.writelines('\n')


def transform_df_textfile(df=None, filepath=None):
    create_data(df, filepath)
    
def initialize_tagger(embeddings=None, tag_type=None,
                      tag_dictionary=None, cbrt=False,
                      hidden_size=256):
    """
    """
    if cbrt:
        tagger : SequenceTagger = flair.models.SequenceTagger(hidden_size=hidden_size,
                                           embeddings=embeddings,
                                           tag_dictionary=tag_dictionary,
                                           tag_type=tag_type,
                                           use_crf=False,
                                            use_rnn=False)
    else:    
        tagger : SequenceTagger = flair.models.SequenceTagger(hidden_size=hidden_size,
                                           embeddings=embeddings,
                                           tag_dictionary=tag_dictionary,
                                           tag_type=tag_type,
                                           use_crf=True)
    return tagger

def predict_flair(model, TEXT_test):
    """
    """
    sentence = Sentence(TEXT_test)
    # predict the tags
    model.predict(sentence)
    result_dict = sentence.to_dict("ner")
    return result_dict


def doc_to_spans_flair(doc):
    """
    """
    spans = []
    scores = []
    entities = set()
    predictions = doc["entities"]
    for prediction in predictions:
        if not prediction:
            continue
        spans.append({
            'from_name': 'label',
            'to_name': 'text',
            'type': 'labels',
            'value': {
                'start': prediction["start_pos"],
                'end': prediction["end_pos"],
                'text': prediction["text"],
                'labels': [str(prediction["labels"][0]).split()[0]],
#                 'score': [str(prediction["labels"][0]).split()[1].strip("()")]
            }
        })
        scores.append(float(str(prediction["labels"][0]).split()[1].strip("()")))
        entities.add(str(prediction["labels"][0]).split()[0])

    return spans, entities, scores


class MyModel(LabelStudioMLBase):
    def __init__(self, **kwargs):
        # don't forget to initialize base class...
        super(MyModel, self).__init__(**kwargs)
        
        # assert len(self.parsed_label_config) == 1
        self.from_name, self.info = list(self.parsed_label_config.items())[0]
        
        if not self.train_output:
            self.labels = self.info['labels']
        else:
            self.load(self.train_output)
#         self.model = self.load_my_model()
    
    def load(self, train_output):
        """Here you load the model into the memory. resources is a dict returned by training script"""
        self.model_path = train_output["model_path"]
        self.model_type = train_output["model_type"]
        
    def predict(self, tasks, **kwargs):
        
#         timestamp_folder = datetime.datetime.now().strftime('%d%m%Y_%H%M%S')
#         training_path = "./training"
#         flair_trainer_path_seq = os.path.join(training_path, "flair_ner",timestamp_folder)
        flair_trainer_path_seq = self.model_path
        model_path=os.path.join(flair_trainer_path_seq,"best-model.pt")
        ml_flair_seq = flair.models.SequenceTagger.load(model_path)
        
        model_name = "flair_seq"
        texts = [task['data']["text"] for task in tasks]
        predictions = []
        for text in texts:
            
            spans, ents, scores = doc_to_spans_flair(predict_flair(ml_flair_seq, text))
            mean_score = np.mean(scores) if len(scores) > 0 else 0

            predictions.append({'model_version': model_name, 'result': spans, 'score':mean_score})

        return predictions

    
    def fit(self, annotations, working_dir=None, **kwargs):
    
        timestamp_folder = datetime.datetime.now().strftime('%d%m%Y_%H%M%S')
        training_path =  os.path.join(working_dir,"training")
        Tensorboard_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(working_dir))), "runs", os.path.basename(os.path.normpath(working_dir))) #new
        flair_trainer_path_seq = os.path.join(training_path, "flair_ner") #new
        logging.info("completions",annotations)
        TRAIN_DATA = load_data(data=annotations)
        df = create_df_from_data(TRAIN_DATA=TRAIN_DATA)
        
        train, dev = train_test_split(df, test_size=0.2, random_state=0)
        if not os.path.exists(training_path):
            os.makedirs(training_path)
        df.to_csv(os.path.join(training_path, "file.csv"))
        transform_df_textfile(train, filepath=os.path.join(training_path, 'train.txt'))
        transform_df_textfile(dev, filepath=os.path.join(training_path, 'dev.txt'))

        # define columns
        columns = {0 : 'text', 1 : 'ner'}
        # directory where the data resides
        data_folder = training_path

        # 1. initializing the corpus
        corpus: Corpus = ColumnCorpus(data_folder, columns,
                                      train_file = 'train.txt',
                                      dev_file = 'dev.txt')

        print("TRAIN {} DEV {}".format(len(corpus.train),len(corpus.dev)))

        # 2. what tag do we want to predict
        tag_type = 'ner'

        # 3. make the tag dictionary from the corpus
        tag_dictionary = corpus.make_tag_dictionary(tag_type=tag_type)

        # 4. initialize embeddings
        embedding_types = [
            flair.embeddings.WordEmbeddings('glove'),
            # comment in these lines to use flair embeddings
            flair.embeddings.FlairEmbeddings('fr-forward'),
            flair.embeddings.FlairEmbeddings('fr-backward'),
        ]
        embeddings: flair.embeddings.StackedEmbeddings = flair.embeddings.StackedEmbeddings(embeddings=embedding_types)

        # 5. initialize sequence tagger
        tagger_seq = initialize_tagger(embeddings=embeddings, tag_type=tag_type,
                      tag_dictionary=tag_dictionary)

        # 6. train
        trainer : ModelTrainer = ModelTrainer(tagger_seq, corpus)
        trainer.train(flair_trainer_path_seq,
                        use_tensorboard=True,
                        tensorboard_log_dir=Tensorboard_dir,
                        learning_rate=0.1, #TOEDIT
                        mini_batch_size=256, #TOEDIT
                        max_epochs=80, #TOEDIT
                        patience=10, #TOEDIT
                        num_workers=10 #TOEDIT
                    )
        print("Tensorboard_dir",Tensorboard_dir)

        return {
            'model_path': flair_trainer_path_seq,
            'model_type': tag_type
        }