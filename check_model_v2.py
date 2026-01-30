import spacy
import os

model_path = os.path.expanduser("~/CommonCrawlNewsDataSet/models/LLAMA_fast_geotag/spacy_lg_geo")
print(f"Testing model at: {model_path}")

if not os.path.exists(model_path):
    print("❌ Model directory not found!")
    exit(1)

nlp = spacy.load(model_path)
print("✅ Model loaded successfully!")

# Quick test
text = "Berlin is the capital of Germany."
doc = nlp(text)
print(f"\nTest: {text}")
print(f"Entities: {[(ent.text, ent.label_) for ent in doc.ents]}")
