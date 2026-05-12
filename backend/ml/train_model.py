import os, json, logging
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
import tensorflow as tf
from tensorflow.keras import layers, Model

logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRAINER] %(message)s")
logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "saved_models")
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURES = ["packet_size","frequency","bytes_sent","bytes_recv",
            "latency_ms","rssi_dbm","cpu_percent","memory_percent","port"]
SEQUENCE_LEN = 10

def generate_data(n=12000):
    rng = np.random.default_rng(42)
    n_norm = int(n*0.85)
    normal = pd.DataFrame({
        "packet_size": rng.normal(300,150,n_norm).clip(1),
        "frequency":   rng.normal(5,3,n_norm).clip(0.01),
        "bytes_sent":  rng.normal(2000,800,n_norm).clip(1),
        "bytes_recv":  rng.normal(1000,400,n_norm).clip(1),
        "latency_ms":  rng.normal(20,8,n_norm).clip(1),
        "rssi_dbm":    rng.uniform(-70,-40,n_norm),
        "cpu_percent": rng.normal(15,8,n_norm).clip(0,100),
        "memory_percent": rng.normal(40,12,n_norm).clip(0,100),
        "port":        rng.choice([1883,443,8883,554,502],n_norm),
        "label": 0,
    })
    n_anom = n - n_norm
    anom = pd.DataFrame({
        "packet_size": rng.normal(1400,100,n_anom).clip(1),
        "frequency":   rng.normal(150,50,n_anom).clip(1),
        "bytes_sent":  rng.normal(1000000,200000,n_anom).clip(1),
        "bytes_recv":  rng.normal(500,100,n_anom).clip(1),
        "latency_ms":  rng.normal(500,200,n_anom).clip(1),
        "rssi_dbm":    rng.uniform(-100,-80,n_anom),
        "cpu_percent": rng.normal(85,10,n_anom).clip(0,100),
        "memory_percent": rng.normal(90,8,n_anom).clip(0,100),
        "port":        rng.integers(1,65535,n_anom),
        "label": 1,
    })
    df = pd.concat([normal,anom],ignore_index=True).sample(frac=1,random_state=42)
    logger.info(f"Dataset: {len(df)} rows | {df['label'].value_counts().to_dict()}")
    return df

def build_lstm(n_feat, seq_len):
    inp = layers.Input(shape=(seq_len, n_feat))
    x = layers.LSTM(64, return_sequences=True)(inp)
    x = layers.LSTM(32, return_sequences=False)(x)
    x = layers.RepeatVector(seq_len)(x)
    x = layers.LSTM(32, return_sequences=True)(x)
    x = layers.LSTM(64, return_sequences=True)(x)
    out = layers.TimeDistributed(layers.Dense(n_feat))(x)
    m = Model(inp, out)
    m.compile(optimizer="adam", loss="mse")
    return m

def main():
    df = generate_data()
    X = df[FEATURES].values; y = df["label"].values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    split = int(0.8*len(Xs))
    X_tr, X_te = Xs[:split], Xs[split:]
    y_tr, y_te = y[:split], y[split:]

    logger.info("Training Isolation Forest...")
    clf = IsolationForest(n_estimators=200, contamination=0.15, random_state=42, n_jobs=-1)
    clf.fit(X_tr)
    joblib.dump(clf, os.path.join(MODEL_DIR,"isolation_forest.joblib"))
    joblib.dump(scaler, os.path.join(MODEL_DIR,"scaler.joblib"))
    preds = (clf.predict(X_te)==-1).astype(int)
    logger.info("\n"+classification_report(y_te,preds,target_names=["normal","anomaly"]))

    logger.info("Training LSTM Autoencoder...")
    X_norm = Xs[y==0]
    seqs = np.array([X_norm[i:i+SEQUENCE_LEN] for i in range(len(X_norm)-SEQUENCE_LEN)])
    model = build_lstm(len(FEATURES), SEQUENCE_LEN)
    model.fit(seqs, seqs, epochs=20, batch_size=64, validation_split=0.1,
              callbacks=[tf.keras.callbacks.EarlyStopping(patience=3)], verbose=1)
    model.save(os.path.join(MODEL_DIR,"lstm_autoencoder.keras"))
    recon = model.predict(seqs, verbose=0)
    mse = np.mean(np.power(seqs-recon,2), axis=(1,2))
    thresh = float(np.percentile(mse,95))
    with open(os.path.join(MODEL_DIR,"lstm_meta.json"),"w") as f:
        json.dump({"threshold":thresh,"sequence_len":SEQUENCE_LEN},f)
    logger.info(f"✅ All models saved! LSTM threshold: {thresh:.6f}")

if __name__ == "__main__":
    main()
