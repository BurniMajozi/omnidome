"""Churn prediction model — scikit-learn GradientBoostingClassifier with heuristic fallback.

Split out from main.py so both main.py (API routes) and batch_churn.py
(batch prediction + persistence) can import the model without a circular
dependency: main.py used to import batch_churn, and batch_churn imported
the model classes back from main.py.
"""

import logging
import os
import pickle
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger("retention.churn_model")

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "churn_model.pkl"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOYAL = "loyal"


class ChurnReason(str, Enum):
    PRICE_SENSITIVITY = "price_sensitivity"
    SERVICE_ISSUES = "service_issues"
    COMPETITOR_OFFER = "competitor_offer"
    RELOCATION = "relocation"
    NO_LONGER_NEEDED = "no_longer_needed"
    PAYMENT_ISSUES = "payment_issues"


class ChurnModel:
    """Scikit-learn churn prediction model with feature engineering.

    Features used:
    - tenure_months: How long the customer has been active
    - monthly_spend_zar: Average monthly revenue
    - support_tickets_30d: Number of support tickets in last 30 days
    - payment_failures_90d: Failed payment attempts in last 90 days
    - contract_days_remaining: Days until contract expiry
    - usage_trend: Ratio of last month usage to average (declining = risk)
    - nps_score: Net Promoter Score (-100 to 100)
    - competitor_mentions: Times competitor mentioned in support calls
    - days_since_last_login: Recency feature
    - num_products: How many products the customer has
    """

    FEATURE_NAMES = [
        "tenure_months",
        "monthly_spend_zar",
        "support_tickets_30d",
        "payment_failures_90d",
        "contract_days_remaining",
        "usage_trend",
        "nps_score",
        "competitor_mentions",
        "days_since_last_login",
        "num_products",
    ]

    def __init__(self):
        self.model = None
        self.is_trained = False
        self.trained_at = None
        self.training_samples = 0
        self.accuracy = 0.0
        self.auc_roc = 0.0
        self._try_load()

    def _try_load(self):
        """Load a previously trained model from disk."""
        try:
            if MODEL_PATH.exists():
                with open(MODEL_PATH, "rb") as f:
                    saved = pickle.load(f)
                self.model = saved["model"]
                self.trained_at = saved.get("trained_at")
                self.training_samples = saved.get("training_samples", 0)
                self.accuracy = saved.get("accuracy", 0.0)
                self.auc_roc = saved.get("auc_roc", 0.0)
                self.is_trained = True
                logger.info(f"Loaded trained model (accuracy={self.accuracy:.2%}, trained_at={self.trained_at})")
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
            self.model = None
            self.is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> dict:
        """Train the churn prediction model."""
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.model_selection import cross_val_score

            self.model = GradientBoostingClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42,
            )
            self.model.fit(X, y)

            # Cross-validated accuracy
            cv_scores = cross_val_score(self.model, X, y, cv=5, scoring="accuracy")
            self.accuracy = float(cv_scores.mean())

            # AUC-ROC
            try:
                from sklearn.metrics import roc_auc_score
                y_proba = self.model.predict_proba(X)[:, 1]
                self.auc_roc = float(roc_auc_score(y, y_proba))
            except Exception:
                self.auc_roc = 0.0

            self.training_samples = len(y)
            self.trained_at = datetime.utcnow().isoformat()
            self.is_trained = True

            # Save
            with open(MODEL_PATH, "wb") as f:
                pickle.dump({
                    "model": self.model,
                    "trained_at": self.trained_at,
                    "training_samples": self.training_samples,
                    "accuracy": self.accuracy,
                    "auc_roc": self.auc_roc,
                }, f)

            logger.info(f"Model trained: accuracy={self.accuracy:.2%}, n={self.training_samples}")
            return {
                "accuracy": self.accuracy,
                "auc_roc": self.auc_roc,
                "training_samples": self.training_samples,
            }
        except ImportError:
            logger.warning("scikit-learn not installed, falling back to heuristic model")
            self.is_trained = False
            return {"accuracy": 0.0, "auc_roc": 0.0, "training_samples": 0}

    def predict(self, features: dict) -> dict:
        """Predict churn probability for a single customer.
        Returns dict with probability, risk_level, top_factors.
        """
        feature_vec = np.array([[features.get(name, 0.0) for name in self.FEATURE_NAMES]])

        if self.is_trained and self.model is not None:
            probability = float(self.model.predict_proba(feature_vec)[0][1])
            # Feature importance-based explanations
            importances = self.model.feature_importances_
            factor_contrib = []
            for i, name in enumerate(self.FEATURE_NAMES):
                factor_contrib.append({
                    "feature": name,
                    "importance": float(importances[i]),
                    "value": features.get(name, 0),
                })
            factor_contrib.sort(key=lambda x: x["importance"], reverse=True)
        else:
            # Heuristic fallback when no model is trained
            probability = self._heuristic_predict(features)
            factor_contrib = self._heuristic_factors(features)

        # Clamp
        probability = max(0.0, min(1.0, probability))
        risk_score = probability * 100

        if risk_score >= 90:
            risk_level = RiskLevel.CRITICAL
        elif risk_score >= 70:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 50:
            risk_level = RiskLevel.MEDIUM
        elif risk_score >= 30:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.LOYAL

        # Determine primary churn reason from top factors
        primary_reason = self._infer_reason(features, factor_contrib)

        return {
            "probability": probability,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "top_factors": factor_contrib[:5],
            "primary_reason": primary_reason,
            "confidence": self.accuracy if self.is_trained else 0.65,
        }

    def _heuristic_predict(self, features: dict) -> float:
        """Fallback heuristic when sklearn model is not available."""
        score = 0.3  # base churn probability

        # High support tickets → high risk
        tickets = features.get("support_tickets_30d", 0)
        if tickets > 5:
            score += 0.25
        elif tickets > 2:
            score += 0.12

        # Payment failures
        failures = features.get("payment_failures_90d", 0)
        if failures > 2:
            score += 0.15
        elif failures > 0:
            score += 0.07

        # Declining usage
        usage = features.get("usage_trend", 1.0)
        if usage < 0.7:
            score += 0.15
        elif usage < 0.85:
            score += 0.07

        # Low NPS
        nps = features.get("nps_score", 50)
        if nps < 0:
            score += 0.12
        elif nps < 30:
            score += 0.06

        # Competitor mentions
        comp = features.get("competitor_mentions", 0)
        if comp > 2:
            score += 0.15
        elif comp > 0:
            score += 0.08

        # Contract expiring soon
        contract = features.get("contract_days_remaining", 365)
        if contract < 30:
            score += 0.1
        elif contract < 90:
            score += 0.05

        # Long time since login
        days_login = features.get("days_since_last_login", 0)
        if days_login > 30:
            score += 0.08

        # Short tenure + any risk factor
        tenure = features.get("tenure_months", 12)
        if tenure < 3 and score > 0.4:
            score += 0.1

        return min(0.98, score)

    def _heuristic_factors(self, features: dict) -> List[Dict[str, Any]]:
        """Generate top factors for heuristic mode."""
        factors = []
        if features.get("support_tickets_30d", 0) > 2:
            factors.append({"feature": "support_tickets_30d", "importance": 0.25, "value": features["support_tickets_30d"]})
        if features.get("payment_failures_90d", 0) > 0:
            factors.append({"feature": "payment_failures_90d", "importance": 0.20, "value": features["payment_failures_90d"]})
        if features.get("usage_trend", 1.0) < 0.85:
            factors.append({"feature": "usage_trend", "importance": 0.18, "value": features["usage_trend"]})
        if features.get("competitor_mentions", 0) > 0:
            factors.append({"feature": "competitor_mentions", "importance": 0.15, "value": features["competitor_mentions"]})
        if features.get("nps_score", 50) < 30:
            factors.append({"feature": "nps_score", "importance": 0.12, "value": features["nps_score"]})
        factors.sort(key=lambda x: x["importance"], reverse=True)
        return factors[:5]

    def _infer_reason(self, features: dict, factors: list) -> ChurnReason:
        """Infer primary churn reason from feature values."""
        top = {f["feature"] for f in factors[:3]}
        if "support_tickets_30d" in top or "usage_trend" in top:
            return ChurnReason.SERVICE_ISSUES
        if "competitor_mentions" in top:
            return ChurnReason.COMPETITOR_OFFER
        if "payment_failures_90d" in top:
            return ChurnReason.PAYMENT_ISSUES
        if "nps_score" in top and features.get("nps_score", 50) < 20:
            return ChurnReason.PRICE_SENSITIVITY
        if features.get("tenure_months", 12) > 36:
            return ChurnReason.NO_LONGER_NEEDED
        return ChurnReason.PRICE_SENSITIVITY

    def get_info(self) -> dict:
        importance = {}
        if self.is_trained and self.model is not None:
            for i, name in enumerate(self.FEATURE_NAMES):
                importance[name] = float(self.model.feature_importances_[i])
        return {
            "model_type": "GradientBoostingClassifier" if self.is_trained else "heuristic",
            "trained_at": self.trained_at,
            "training_samples": self.training_samples,
            "accuracy": self.accuracy,
            "auc_roc": self.auc_roc,
            "feature_importance": importance,
            "is_trained": self.is_trained,
        }


# Singleton model instance
churn_model = ChurnModel()

# ── Feature extraction from customer snapshot ──────────────────────────

def extract_features(snapshot: dict) -> dict:
    """Extract model features from a customer snapshot (as synced from CRM)."""
    now = datetime.utcnow()
    created_at = None
    if snapshot.get("created_at"):
        try:
            created_at = datetime.fromisoformat(snapshot["created_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    tenure_months = 0
    if created_at:
        tenure_months = max(0, (now - created_at.replace(tzinfo=None)).days // 30)

    # snapshots store tenure_days, convert
    if not tenure_months and snapshot.get("tenure_days"):
        tenure_months = snapshot["tenure_days"] // 30

    return {
        "tenure_months": float(tenure_months),
        "monthly_spend_zar": float(snapshot.get("monthly_spend_zar", 0)),
        "support_tickets_30d": float(snapshot.get("num_support_tickets_30d", 0)),
        "payment_failures_90d": float(snapshot.get("payment_failures_90d", 0)),
        "contract_days_remaining": float(snapshot.get("contract_days_remaining", 365)),
        "usage_trend": float(snapshot.get("usage_trend", 1.0)),
        "nps_score": float(snapshot.get("nps_score", 50)),
        "competitor_mentions": float(snapshot.get("competitor_mentions", 0)),
        "days_since_last_login": float(snapshot.get("days_since_last_login", 0)),
        "num_products": float(snapshot.get("num_products", 1)),
    }
