from flair.data import Sentence
from flair.models import SequenceTagger
import os
import logging
import json
from flask import Flask, request, send_file, jsonify
# from flask_cors import CORS
import time
import torch
logging.basicConfig(level=logging.INFO)

def predict_flair(model, TEXT_test):
    """
    Predict NER dict
    Args:
        - model
        - TEXT_test (str)
    output:
        - result_dict(dict): unformatted dict
    """
    sentence = Sentence(TEXT_test)
    # predict the tags
    model.predict(sentence)
    result_dict = sentence.to_dict("ner")
    result_dict["raw_text"] = TEXT_test
    return result_dict


def doc_to_spans_flair(doc):
    """
    format FLAIR prediction dict
    Args:
        - doc(dict): formatted dict
    output:
        - result_dict(dict): formatted dict
    """
    spans = []
    scores = []
    entities = []
    results = []
    zipped = []
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
            }
        })
        scores.append(float(str(prediction["labels"][0]).split()[1].strip("()")))
        entities.append(str(prediction["labels"][0]).split()[0])
        results.append(prediction["text"])
    final_dict = {#"spans":spans,
                 "entities":entities,
                 "scores":scores,
                 "result":results,
                 "zipped":[list(a) for a in zip(results, entities, scores)],
                 "raw_text":doc["raw_text"]}
    return final_dict

# Load models
if torch.cuda.is_available():
    device_type = {"device":"cuda"}
    logging.info("CUDA")
else:
    device_type = {"device":"cpu"}
    

def basic_handler(event=None,MODEL_NAME = ""):
    """
    """
    #json_keys
    Test_TEXT = event['text']
    with torch.no_grad():
        res = doc_to_spans_flair(predict_flair(tagger, Test_TEXT))
    
    return res

# Initialize the Flask application
app = Flask(__name__)
# CORS(app)

# Simple probe.
@app.route('/', methods=['GET'])
def hello():
    return 'Hello SPEECH TIMER !'

# Route http posts to this method
@app.route('/', methods=['POST'])
def run():
    start = time.time()
    data = request.json
    res = basic_handler(event=data, MODEL_NAME = str(data["model_name"]))
    
#     formatted_res = format_result(res["zipped"], res["entities"], Thresh = 0.6)
#     data["result"] = formatted_res
#     data["raw"] = res
    
    logging.info("res {}".format(res))
#     logging.info("formatted_res {}".format(formatted_res))
    data["process_time"] = "{}".format(time.time() - start)
    logging.info(f'Total time {time.time() - start:.2f}s')
    return jsonify(res)

# load the NER tagger
model_path = "model/best-model.pt" #TOEDIT
tagger = SequenceTagger.load(model_path)
logging.info("model is loaded")

if __name__ == '__main__':
    os.environ['FLASK_ENV'] = 'development'
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)