"""Optional local model export; no training or arbitrary pickle loading.

A JSON export supports trained logistic regression directly. A Keras .keras/.h5
export can be used when tensorflow is installed separately. Preprocessing and
validation metadata always accompany the model; see docs/weather.md.
"""
import json
import math
from pathlib import Path
from .rules import VARIABLES, numeric

UNITS = {"temperature_2m": "celsius", "precipitation_probability": "percent", "rain": "mm/h",
         "snowfall": "cm/h", "weather_code": "wmo", "visibility": "m",
         "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h"}


def predict(values, manifest_path=None):
    unavailable = lambda reason: {"status": "unavailable", "reason": reason}
    if not manifest_path:
        return unavailable("No compatible trained model has been configured.")
    try:
        path = Path(manifest_path).resolve()
        manifest = json.loads(path.read_text())
        features = manifest["features"]
        evaluation = manifest["evaluation"]
        if (manifest.get("schema_version") != 1 or manifest.get("target") != "weather_disruption"
                or manifest.get("resolution") != "hourly" or not features or len(features) > 32
                or len(set(features)) != len(features) or any(f not in VARIABLES for f in features)
                or any(manifest["units"].get(f) != UNITS[f] for f in features)
                or evaluation.get("input_kind") != "forecast" or not evaluation.get("held_out")
                or not numeric(evaluation.get("brier_score")) or not numeric(evaluation.get("baseline_brier_score"))
                or not 0 <= evaluation["brier_score"] < evaluation["baseline_brier_score"] <= 1):
            return unavailable("Model features, units, target, or held-out forecast validation are incompatible.")
        if any(not numeric(values.get(f)) for f in features):
            return unavailable("Required model inputs are missing.")
        preprocessing = manifest["preprocessing"]
        means, scales = preprocessing["means"], preprocessing["scales"]
        if (len(means) != len(features) or len(scales) != len(features)
                or not all(numeric(m) for m in means) or not all(numeric(s) and s > 0 for s in scales)):
            return unavailable("Model preprocessing is incompatible.")
        x = [(values[f] - means[i]) / scales[i] for i, f in enumerate(features)]
        if manifest.get("format") == "logistic-json":
            coefficients, intercept = manifest["coefficients"], manifest["intercept"]
            if len(coefficients) != len(x) or not all(numeric(c) for c in coefficients) or not numeric(intercept):
                return unavailable("Model coefficients are incompatible.")
            logit = intercept + sum(a * b for a, b in zip(x, coefficients))
            probability = 1 / (1 + math.exp(-max(-700, min(700, logit))))
        elif manifest.get("format") == "keras":
            import tensorflow as tf
            model_path = (path.parent / manifest["model_file"]).resolve()
            if model_path.parent != path.parent or model_path.suffix not in (".keras", ".h5"):
                return unavailable("Model file must be a local Keras export beside its manifest.")
            model = tf.keras.models.load_model(model_path, compile=False)
            probability = float(model.predict(tf.constant([x], dtype=tf.float32), verbose=0)[0][0])
        else:
            return unavailable("Unsupported model export format.")
        if not numeric(probability) or not 0 <= probability <= 1:
            return unavailable("Model returned an invalid probability.")
        return {"status": "available", "probability": probability, "model_version": str(manifest["model_version"]),
                "label": "Experimental weather disruption estimate", "evaluation": evaluation}
    except (OSError, ValueError, TypeError, KeyError, ImportError, IndexError, OverflowError, AttributeError, RuntimeError):
        return unavailable("Model export could not be loaded or validated.")
