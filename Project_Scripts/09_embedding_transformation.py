import pandas as pd
import sqlite3
from sentence_transformers import SentenceTransformer
import torch
from sentence_transformers import quantize_embeddings
import numpy as np

conn=sqlite3.connect(DB_PATH)
data=pd.read_sql("SELECT id, text FROM articles",conn)

embedding_model=SentenceTransformer("antoinelouis/biencoder-camembert-base-mmarcoFR",device="cuda",model_kwargs={"torch_dtype": "float16"})

embeddings=embedding_model.encode(list(data["text"]),normalize_embeddings=True,prompt="passage: ")

embedding_min = embeddings.min(axis=0)
embedding_max = embeddings.max(axis=0)
calibration_ranges = np.vstack([embedding_min, embedding_max])

int8_embeddings=quantize_embeddings(embeddings, precision="int8",ranges=calibration_ranges)

binary_embeddings=quantize_embeddings(embeddings, precision="binary")

data["embeddings"]=list(embeddings)

data["int8_embeddings"]=list(int8_embeddings)

data["binary_embeddings"]=list(binary_embeddings)

data.to_feather(output_filepath)

np.save(calibration_ranges,"calibration_ranges.npy")
