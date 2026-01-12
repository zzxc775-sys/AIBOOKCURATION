import pickle

with open("backend/models/faiss_index/index.pkl", "rb") as f:
    obj = pickle.load(f)

print("TYPE:", type(obj))

if hasattr(obj, "__len__"):
    print("LEN:", len(obj))

if isinstance(obj, dict):
    print("KEY SAMPLE:", list(obj.keys())[:5])
