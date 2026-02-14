from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from joblib import dump, load
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


@dataclass(frozen=True)
class ResaleModelMetrics:
    mae: float
    r2: float
    n_rows: int


def _build_pipeline(X: pd.DataFrame) -> Pipeline:
    cat_cols = [c for c in X.columns if X[c].dtype == "object" or str(X[c].dtype).startswith("category")]
    num_cols = [c for c in X.columns if c not in cat_cols]

    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    pre = ColumnTransformer(
        transformers=[
            ("num", numeric, num_cols),
            ("cat", categorical, cat_cols),
        ],
        remainder="drop",
    )

    model = Ridge(alpha=1.0, random_state=0)

    return Pipeline(steps=[("pre", pre), ("model", model)])


def train_resale_model(
    df: pd.DataFrame,
    target_col: str,
    *,
    test_frac: float = 0.2,
    random_state: int = 0,
) -> tuple[Pipeline, ResaleModelMetrics]:
    if target_col not in df.columns:
        raise ValueError(f"target_col '{target_col}' not found in dataframe columns")

    df = df.copy()
    df = df.dropna(subset=[target_col])
    if len(df) < 50:
        raise ValueError(f"need at least 50 rows after dropping NA target; got {len(df)}")

    y = df[target_col].astype(float)
    X = df.drop(columns=[target_col])

    rng = np.random.default_rng(random_state)
    idx = np.arange(len(df))
    rng.shuffle(idx)
    split = int(len(df) * (1 - test_frac))
    train_idx = idx[:split]
    test_idx = idx[split:]

    X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
    X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]

    pipe = _build_pipeline(X_train)
    pipe.fit(X_train, y_train)

    y_pred = pipe.predict(X_test)
    metrics = ResaleModelMetrics(
        mae=float(mean_absolute_error(y_test, y_pred)),
        r2=float(r2_score(y_test, y_pred)),
        n_rows=int(len(df)),
    )
    return pipe, metrics


def save_resale_model(pipe: Pipeline, path: str) -> None:
    dump(pipe, path)


def load_resale_model(path: str) -> Any:
    return load(path)


def predict_resale(pipe: Any, X: pd.DataFrame) -> np.ndarray:
    return np.asarray(pipe.predict(X), dtype=float)

