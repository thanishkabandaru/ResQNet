"""Text-based emergency classification and priority prediction."""

import csv
import hashlib
import pickle
from collections import Counter
from pathlib import Path

from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


ML_MODELS_DIR = Path(__file__).resolve().parent / "ml_models"
ML_MODELS_DIR.mkdir(exist_ok=True)

CATEGORY_MODEL_PATH = ML_MODELS_DIR / "category_model.pkl"
PRIORITY_MODEL_PATH = ML_MODELS_DIR / "priority_model.pkl"
PRIORITY_DATASET_PATH = Path(__file__).resolve().parent / "priority_training_data.csv"
PRIORITY_MODEL_VERSION = 2
PRIORITY_LABELS = ("Low", "Medium", "High")

TRAINING_DATA = [
    ("chest pain and shortness of breath", "Medical Emergency", "High"),
    ("person collapsed on ground", "Medical Emergency", "High"),
    ("severe bleeding from injury", "Medical Emergency", "High"),
    ("child unable to breathe", "Medical Emergency", "High"),
    ("poison ingestion", "Medical Emergency", "High"),
    ("diabetic patient unconscious", "Medical Emergency", "High"),
    ("severe allergic reaction", "Medical Emergency", "High"),
    ("broken bone from fall", "Medical Emergency", "Medium"),
    ("person complaining of severe headache", "Medical Emergency", "Medium"),
    ("high fever and difficulty breathing", "Medical Emergency", "Medium"),
    ("minor cut on hand", "Medical Emergency", "Low"),
    ("person feeling dizzy", "Medical Emergency", "Low"),
    ("mild fever", "Medical Emergency", "Low"),
    ("car crash on highway", "Accident", "High"),
    ("two vehicle collision", "Accident", "High"),
    ("pedestrian hit by vehicle", "Accident", "High"),
    ("motorcycle accident", "Accident", "High"),
    ("person trapped in vehicle", "Accident", "High"),
    ("truck overturned on road", "Accident", "High"),
    ("minor fender bender", "Accident", "Low"),
    ("vehicle parked improperly", "Accident", "Low"),
    ("traffic jam due to accident", "Accident", "Medium"),
    ("bicycle accident on street", "Accident", "Medium"),
    ("building on fire", "Fire", "High"),
    ("house fire with people inside", "Fire", "High"),
    ("fire in commercial building", "Fire", "High"),
    ("wildfire spreading rapidly", "Fire", "High"),
    ("smoke and flames coming from structure", "Fire", "High"),
    ("fire in apartment complex", "Fire", "High"),
    ("vehicle fire on road", "Fire", "High"),
    ("small fire in kitchen", "Fire", "Medium"),
    ("controlled burn", "Fire", "Low"),
    ("robbery in progress", "Other", "High"),
    ("person acting violently", "Other", "High"),
    ("suspicious package", "Other", "High"),
    ("missing person report", "Other", "High"),
    ("armed individual sighted", "Other", "High"),
    ("theft at store", "Other", "Medium"),
    ("noise complaint", "Other", "Low"),
    ("dog loose in neighborhood", "Other", "Low"),
    ("damaged traffic light", "Other", "Low"),
    ("litter on road", "Other", "Low"),
]

_category_model = None
_priority_model = None
_category_confidence_model = None
_priority_confidence_model = None


def _new_priority_pipeline():
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    stop_words="english",
                    ngram_range=(1, 2),
                    max_features=500,
                ),
            ),
            (
                "classifier",
                LinearSVC(class_weight="balanced", random_state=42, max_iter=2000),
            ),
        ]
    )


def _read_priority_dataset():
    descriptions = []
    priorities = []
    with PRIORITY_DATASET_PATH.open(encoding="utf-8", newline="") as dataset_file:
        for row in csv.DictReader(dataset_file):
            description = row["description"].strip()
            priority = row["priority"].strip()
            if not description or priority not in PRIORITY_LABELS:
                raise ValueError("Priority dataset contains an empty description or invalid label")
            descriptions.append(description)
            priorities.append(priority)

    counts = Counter(priorities)
    if len(descriptions) < 12 or any(counts[label] < 2 for label in PRIORITY_LABELS):
        raise ValueError("Priority dataset needs at least two examples for every priority")
    return descriptions, priorities


def _priority_dataset_digest():
    return hashlib.sha256(PRIORITY_DATASET_PATH.read_bytes()).hexdigest()


def evaluate_priority_model():
    """Evaluate a held-out stratified split and return macro-averaged metrics."""
    descriptions, priorities = _read_priority_dataset()
    train_text, test_text, train_labels, test_labels = train_test_split(
        descriptions,
        priorities,
        test_size=0.25,
        random_state=42,
        stratify=priorities,
    )

    evaluation_model = _new_priority_pipeline()
    evaluation_model.fit(train_text, train_labels)
    predictions = evaluation_model.predict(test_text)
    precision, recall, f1, _ = precision_recall_fscore_support(
        test_labels,
        predictions,
        labels=PRIORITY_LABELS,
        average="macro",
        zero_division=0,
    )
    return {
        "accuracy": accuracy_score(test_labels, predictions),
        "precision_macro": precision,
        "recall_macro": recall,
        "f1_macro": f1,
        "training_examples": len(train_text),
        "test_examples": len(test_text),
    }


def train_priority_model():
    """Evaluate, train on the full labeled dataset, and persist the priority model."""
    descriptions, priorities = _read_priority_dataset()
    metrics = evaluate_priority_model()
    model = _new_priority_pipeline()
    model.fit(descriptions, priorities)
    with PRIORITY_MODEL_PATH.open("wb") as model_file:
        pickle.dump(
            {
                "version": PRIORITY_MODEL_VERSION,
                "dataset_digest": _priority_dataset_digest(),
                "model": model,
                "metrics": metrics,
            },
            model_file,
        )
    return model, metrics


def train_category_model():
    """Train and persist the existing emergency category classifier."""
    descriptions = [item[0] for item in TRAINING_DATA]
    categories = [item[1] for item in TRAINING_DATA]
    model = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=100, lowercase=True, stop_words="english"
                ),
            ),
            (
                "classifier",
                OneVsRestClassifier(LinearSVC(random_state=42, max_iter=1000)),
            ),
        ]
    )
    model.fit(descriptions, categories)
    with CATEGORY_MODEL_PATH.open("wb") as model_file:
        pickle.dump(model, model_file)
    return model


def load_models():
    """Load cached models once; train missing or outdated models."""
    global _category_model, _priority_model

    if _category_model is None:
        try:
            with CATEGORY_MODEL_PATH.open("rb") as model_file:
                _category_model = pickle.load(model_file)
        except FileNotFoundError:
            _category_model = train_category_model()

    if _priority_model is None:
        try:
            with PRIORITY_MODEL_PATH.open("rb") as model_file:
                saved_priority_model = pickle.load(model_file)
        except FileNotFoundError:
            saved_priority_model = None

        if (
            not isinstance(saved_priority_model, dict)
            or saved_priority_model.get("version") != PRIORITY_MODEL_VERSION
            or saved_priority_model.get("dataset_digest")
            != _priority_dataset_digest()
        ):
            _priority_model, metrics = train_priority_model()
            print(
                "Priority model trained and evaluated "
                f"(accuracy={metrics['accuracy']:.3f}, "
                f"macro F1={metrics['f1_macro']:.3f})"
            )
        else:
            _priority_model = saved_priority_model["model"]

    return _category_model, _priority_model


def predict_category(description):
    """Predict an emergency category with the cached Step 12 model."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("A non-empty description is required for classification")
    category_model, _ = load_models()
    return category_model.predict([description.strip()])[0]


def predict_priority(description):
    """Predict a priority level with the cached TF-IDF model."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("A non-empty description is required for priority prediction")
    _, priority_model = load_models()
    return priority_model.predict([description.strip()])[0]


def _load_confidence_models():
    """Fit cached cross-validated probability calibrators without changing predictions."""
    global _category_confidence_model, _priority_confidence_model

    if _category_confidence_model is None or _priority_confidence_model is None:
        category_text = [item[0] for item in TRAINING_DATA]
        category_labels = [item[1] for item in TRAINING_DATA]
        priority_text, priority_labels = _read_priority_dataset()
        category_model, priority_model = load_models()

        if _category_confidence_model is None:
            _category_confidence_model = CalibratedClassifierCV(
                estimator=category_model,
                method="sigmoid",
                cv=5,
            ).fit(category_text, category_labels)
        if _priority_confidence_model is None:
            _priority_confidence_model = CalibratedClassifierCV(
                estimator=priority_model,
                method="sigmoid",
                cv=5,
            ).fit(priority_text, priority_labels)

    return _category_confidence_model, _priority_confidence_model


def _class_confidence(calibrated_model, description, predicted_class):
    classes = list(calibrated_model.classes_)
    if predicted_class not in classes:
        return None
    probabilities = calibrated_model.predict_proba([description.strip()])[0]
    return float(probabilities[classes.index(predicted_class)])


def predict_category_confidence(description, predicted_category=None):
    """Return calibrated probability for the unchanged category prediction."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("A non-empty description is required for classification")
    if predicted_category is None:
        predicted_category = predict_category(description)
    category_calibrator, _ = _load_confidence_models()
    return _class_confidence(category_calibrator, description, predicted_category)


def predict_priority_confidence(description, predicted_priority=None):
    """Return calibrated probability for the unchanged priority prediction."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("A non-empty description is required for priority prediction")
    if predicted_priority is None:
        predicted_priority = predict_priority(description)
    _, priority_calibrator = _load_confidence_models()
    return _class_confidence(priority_calibrator, description, predicted_priority)


load_models()
