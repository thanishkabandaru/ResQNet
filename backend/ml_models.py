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
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC


ML_MODELS_DIR = Path(__file__).resolve().parent / "ml_models"
ML_MODELS_DIR.mkdir(exist_ok=True)

CATEGORY_MODEL_PATH = ML_MODELS_DIR / "category_model.pkl"
PRIORITY_MODEL_PATH = ML_MODELS_DIR / "priority_model.pkl"
CATEGORY_DATASET_PATH = (
    Path(__file__).resolve().parent / "resqnet_category_training_data_2400.csv"
)
PRIORITY_DATASET_PATH = Path(__file__).resolve().parent / "priority_training_data.csv"
CATEGORY_MODEL_VERSION = 3
PRIORITY_MODEL_VERSION = 2
CATEGORY_LABELS = (
    "Medical Emergency",
    "Accident",
    "Fire",
    "Road Hazard",
    "Crime",
    "Theft",
    "Missing Person",
    "Natural Disaster",
    "Building Collapse",
    "Electrical Emergency",
    "Gas Leak",
    "Other Emergency",
)
PRIORITY_LABELS = ("Low", "Medium", "High")

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


def _read_category_dataset():
    descriptions = []
    categories = []
    with CATEGORY_DATASET_PATH.open(encoding="utf-8", newline="") as dataset_file:
        for row in csv.DictReader(dataset_file):
            description = row["description"].strip()
            category = row["category"].strip()
            if not description or category not in CATEGORY_LABELS:
                raise ValueError("Category dataset contains an empty description or invalid label")
            descriptions.append(description)
            categories.append(category)

    counts = Counter(categories)
    if len(descriptions) < len(CATEGORY_LABELS) * 5 or any(
        counts[label] < 5 for label in CATEGORY_LABELS
    ):
        raise ValueError("Category dataset needs at least five examples for every category")
    return descriptions, categories


def _category_dataset_digest():
    return hashlib.sha256(CATEGORY_DATASET_PATH.read_bytes()).hexdigest()


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
    descriptions, categories = _read_category_dataset()
    model = Pipeline(
        [
            (
                "tfidf",
                FeatureUnion(
                    [
                        (
                            "word",
                            TfidfVectorizer(
                                lowercase=True,
                                stop_words="english",
                                ngram_range=(1, 2),
                                max_features=10000,
                                sublinear_tf=True,
                            ),
                        ),
                        (
                            "character",
                            TfidfVectorizer(
                                analyzer="char_wb",
                                ngram_range=(3, 5),
                                min_df=2,
                                max_features=20000,
                                sublinear_tf=True,
                            ),
                        ),
                    ]
                ),
            ),
            (
                "classifier",
                LinearSVC(
                    C=1.0,
                    class_weight="balanced",
                    random_state=42,
                    max_iter=3000,
                ),
            ),
        ]
    )
    model.fit(descriptions, categories)
    with CATEGORY_MODEL_PATH.open("wb") as model_file:
        pickle.dump(
            {
                "version": CATEGORY_MODEL_VERSION,
                "dataset_digest": _category_dataset_digest(),
                "model": model,
            },
            model_file,
        )
    return model


def load_models():
    """Load cached models once; train missing or outdated models."""
    global _category_model, _priority_model

    if _category_model is None:
        try:
            with CATEGORY_MODEL_PATH.open("rb") as model_file:
                saved_category_model = pickle.load(model_file)
        except FileNotFoundError:
            saved_category_model = None

        if (
            not isinstance(saved_category_model, dict)
            or saved_category_model.get("version") != CATEGORY_MODEL_VERSION
            or saved_category_model.get("dataset_digest")
            != _category_dataset_digest()
        ):
            _category_model = train_category_model()
        else:
            _category_model = saved_category_model["model"]

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
        category_text, category_labels = _read_category_dataset()
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
